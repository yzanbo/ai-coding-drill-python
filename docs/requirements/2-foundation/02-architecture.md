# 02. アーキテクチャ・インフラ構成

> **このドキュメントの守備範囲**：システム全体の論理構造、コンポーネントの責務、データ・ジョブの流れ。
> **使うフレームワーク・ライブラリ・サービスの具体名や選定理由**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。

---

## 全体構成（概念図）

```mermaid
flowchart TB
    User([ユーザー])

    User --> FE[Frontend<br/>Next.js / RSC<br/>CodeMirror エディタ]

    FE --> API

    subgraph API[Backend API: NestJS]
        direction TB
        AuthMod[AuthModule]
        ProbMod[ProblemsModule]
        GenMod[GenerationModule]
        GradMod[GradingModule]
        ObsMod[ObservabilityModule]
    end

    GenMod -- 抽象化レイヤ経由 --> LLM[(LLM API<br/>Anthropic / Gemini /<br/>OpenAI / OpenRouter)]
    GenMod -. レスポンスキャッシュ .-> Redis
    AuthMod --> Redis[(Redis<br/>セッション・キャッシュ・<br/>レート制限)]
    AuthMod --> PG
    ProbMod --> PG[(PostgreSQL<br/>users / problems / submissions /<br/>jobs テーブル)]
    GradMod -- "INSERT jobs<br/>+ NOTIFY" --> PG

    PG -. LISTEN/NOTIFY .-> Worker

    Worker[Go 採点ワーカー<br/>別 VM 常駐<br/>goroutine 並列] --> Sandbox
    Sandbox[使い捨てサンドボックス<br/>Docker → gVisor → Firecracker<br/>Vitest 実行]
    Worker -- 結果書き戻し --> PG

    ObsMod --> Otel[(観測基盤<br/>OTel: Logs/Traces/Metrics<br/>+ Sentry エラー追跡)]
    Worker --> Otel

    classDef store fill:#e8f4ff,stroke:#4a90e2;
    classDef external fill:#fff7e6,stroke:#ff9800;
    classDef worker fill:#f0fff0,stroke:#4caf50;
    class PG,Redis store;
    class LLM,Otel external;
    class Worker,Sandbox worker;
```

**読み方**：

- 実線（`-->`）：同期的な呼び出し
- 点線（`-.->`）：非同期 / 通知（LISTEN/NOTIFY）/ オプショナル経路（キャッシュヒット時）
- ストア（青）：永続データ層
- 外部サービス（橙）：自前ホスティング以外
- ワーカー層（緑）：別 VM で動く非同期処理

---

## 言語構成ロードマップ

| フェーズ | 言語構成 | 目的 |
|---|---|---|
| MVP | TypeScript（Web/API/LLM）+ Go（採点ワーカー） | 最短で動かす。Go はワーカーの軽量・高速性と Docker 操作の強みを活かす |
| 次期 | 上記 + Python（評価・分析パイプライン） | 生成済み問題のオフライン再評価・重複検出・分布分析、人間評価との相関分析、学習履歴バッチ |
| 将来 | 採点対象言語の多言語化（Python、Next.js 等） | 言語アダプタ層を通じて追加 |

---

## コンポーネントの責務

### Frontend
- ページレンダリング（RSC 中心）
- 認証セッション保持
- NestJS API 呼び出し（一覧・詳細取得は RSC 直 fetch、ジョブ進捗ポーリングはクライアント側）
- コードエディタ UI（TypeScript の即時型診断つき）
- 採点結果ポーリング

→ 採用技術・ライブラリは [05-runtime-stack: フロントエンド](./05-runtime-stack.md#フロントエンド)

### Backend API（NestJS）
ユーザーリクエストを受け、認証・問題管理・LLM 呼び出し・ジョブ投入を担当する中核アプリ。

#### 主要 Module 構成
- `AuthModule`：認証・セッション
- `ProblemsModule`：問題 CRUD
- `GenerationModule`：LLM 呼び出し（生成・Judge）
- `GradingModule`：採点ジョブの投入と結果取得
- `ObservabilityModule`：OTel による計装（ログ・メトリクス・トレース）+ エラー追跡

#### 設計スタイル
機能別モジュール + シンプルレイヤード（Controller / Service）で統一。データアクセスは Service から Drizzle ORM を直接呼び出し、Repository レイヤは設けない。過剰な抽象化は避け、MVP の実装速度を優先する。

→ 採用フレームワーク・ライブラリ・選定理由は [05-runtime-stack: バックエンド API](./05-runtime-stack.md#バックエンド-apinestjs--typescript)

### ジョブキュー（Postgres `SELECT FOR UPDATE SKIP LOCKED`）

#### 方式
専用キューミドルウェアを使わず、Postgres に `jobs` テーブルを置いて行ロックでキュー化する。

#### 役割
NestJS から採点・問題生成の仕事を登録し、Go ワーカーがそれを取り出して処理する。
- NestJS（Producer）：`INSERT INTO jobs ...` で登録
- Go ワーカー（Consumer）：`SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` で取り出し

#### 運用作法
- 行ロックを Docker 実行中ずっと握らない。`locked_at`/`locked_by` を更新してコミット → 別トランザクションで実行 → 完了後に `state='done'`
- スタックジョブは `locked_at < now() - interval '5 min'` のレコードを定期的にリクレイム
- リトライは `run_at = now() + exponential_backoff`、最大試行回数超過で `state='dead'`（DLQ）

#### ペイロード
JSONB 形式。ジョブスキーマは JSON Schema で管理し TS / Go 両方に型生成。

#### 取得方式
Postgres `LISTEN/NOTIFY` によるプッシュ通知 + 低頻度ポーリング（30 秒）のハイブリッド。
- INSERT 時に `NOTIFY new_job` を発火し、ワーカーは `LISTEN` で即応答
- NOTIFY 取りこぼし対策として低頻度ポーリングを併用

#### スケール時の移行先
ファンアウトや Pub/Sub が必要になった場合は NATS JetStream に移行する方針（README に明記）。

→ テーブル設計・採用ライブラリ・選定理由は [05-runtime-stack: ジョブキュー](./05-runtime-stack.md#ジョブキューpostgres-select-for-update-skip-locked)

### 採点ワーカー（Go）

#### 役割
- Postgres `jobs` テーブルから `FOR UPDATE SKIP LOCKED` でジョブ取得
- Docker API で隔離コンテナ起動
- TypeScript コードを Vitest で実行
- 実行結果（成否・失敗ケース・stdout/stderr・所要時間）を Postgres に書き戻し、ジョブの `state` を更新

#### 設計の特徴
- 常駐プロセス、`LISTEN/NOTIFY` + ポーリングのハイブリッドでジョブ取得
- goroutine による並列採点
- Docker Engine と同じ VM に住み、`/var/run/docker.sock` 経由で Docker 操作

→ 採用言語・ライブラリ・選定理由は [05-runtime-stack: 採点ワーカー](./05-runtime-stack.md#採点ワーカーgo)

### サンドボックスランナー（Go ワーカー内で実行）

#### 使い捨てコンテナ方式
ジョブごとに採点コンテナを生成 → 実行 → 破棄。
- 起動オーバーヘッドは約 200ms（段階 1 / Docker での想定実測、採点本体の 5〜15%、許容範囲）。隔離強化段階 2 以降でも上限 500ms を維持する目標 → SSoT は [01-non-functional.md: パフォーマンス](./01-non-functional.md#パフォーマンス)
- 前回実行の影響が原理的に残らない強い隔離保証を優先
- スループットが問題化した場合は R3（gVisor）でウォームプール、R9（Firecracker）への移行を検討

#### 段階的な隔離強化
- 初期実装：Docker + 制限付き（`--network none`, `--memory`, `--cpus`, `--read-only`, 非 root, tmpfs `/tmp`）
- 発展：gVisor で追加のシステムコール隔離
- さらに発展：Firecracker microVM で起動速度・隔離強度向上
- 各方式の比較を README にベンチマーク付きで記載

→ 実行対象・テストランナー等の詳細は [05-runtime-stack: サンドボックス](./05-runtime-stack.md#サンドボックス)

### データストア
- **PostgreSQL**：ユーザー、問題、解答履歴、ジョブキュー（`jobs` テーブル）
- **Redis**：LLM レスポンスキャッシュ、セッション、レート制限（**ジョブキュー用途では使わない**）

→ 採用バージョン・ORM・ホスティング先は [05-runtime-stack: データベース / キャッシュ](./05-runtime-stack.md#データベース)

---

## 1 ジョブが流れる完全な経路

ユーザーが解答を送信した瞬間からの流れ：

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant Browser as ブラウザ
    participant API as NestJS API
    participant DB as Postgres
    participant Worker as Go ワーカー
    participant Sandbox as 採点コンテナ

    User->>Browser: 解答送信
    Browser->>+API: POST /submissions { code }

    rect rgb(232, 244, 255)
    note over API,DB: ① 解答受付（同一トランザクション）
    API->>DB: BEGIN
    API->>DB: INSERT submissions
    API->>DB: INSERT jobs state=queued
    API->>DB: NOTIFY new_job
    API->>DB: COMMIT
    end

    API-->>-Browser: 202 Accepted (submissionId, jobId)

    Browser->>Browser: TanStack Query でポーリング開始 (1〜2 秒)

    rect rgb(240, 255, 240)
    note over DB,Worker: ② ジョブ取得（LISTEN 受信、行ロック短時間）
    DB->>Worker: NOTIFY new_job
    Worker->>DB: SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1
    Worker->>DB: UPDATE state=running, locked_by=worker-1
    Worker->>DB: COMMIT (行ロック解放)
    end

    rect rgb(255, 247, 230)
    note over Worker,Sandbox: ③ サンドボックス採点（使い捨て）
    Worker->>Sandbox: ContainerCreate + Start
    activate Sandbox
    Sandbox->>Sandbox: Vitest 実行 (タイムアウト 5 秒)
    Sandbox-->>Worker: ContainerLogs (stdout, stderr, exit code)
    Worker->>Sandbox: ContainerRemove
    deactivate Sandbox
    end

    rect rgb(232, 244, 255)
    note over Worker,DB: ④ 結果書き戻し
    Worker->>DB: UPDATE jobs SET state=done, result=...
    Worker->>DB: UPDATE submissions SET status=graded, score=...
    end

    Browser->>+API: GET /submissions/:id (ポーリング)
    API->>DB: SELECT
    DB-->>API: status=graded
    API-->>-Browser: 採点結果
    Browser->>User: 結果表示
```

**重要な設計ポイント**：

| 段階 | キーポイント |
|---|---|
| ① 解答受付 | INSERT submissions + INSERT jobs + NOTIFY を **同一トランザクション**で実行 → Outbox パターン不要、二重書き込み問題なし（[ADR 0004](../../adr/0004-postgres-as-job-queue.md)） |
| ② ジョブ取得 | 行ロックは **短時間で COMMIT**。Docker 実行中はロックを握らない（スタックジョブ防止） |
| ③ サンドボックス採点 | **使い捨てコンテナ**：1 ジョブ 1 コンテナ、実行後即破棄。前回実行の影響が残らない（[ADR 0009](../../adr/0009-disposable-sandbox-container.md)） |
| ④ 結果書き戻し | jobs.state='done' と submissions.status='graded' を別トランザクションで更新。冪等性のため UPDATE は ID 指定で安全 |

**`trace_id` の連結**：①〜④ の全段階を単一トレースで可視化するため、ジョブペイロードに W3C Trace Context を埋め込む（[ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）。

---

## インフラの論理配置

### クラウド：AWS に確定
- 求人需要・情報量・エコシステムを最重視
- マルチクラウド（GCP 併用等）はメリットより複雑度のコストが上回るため不採用
- AWS 内で IAM・ネットワーク・観測性を綺麗に設計することにフォーカス

### 物理配置（責務分離）

```mermaid
flowchart LR
    User([ユーザー]) --> R53

    subgraph CDN[Vercel エッジ CDN]
        FE[Next.js<br/>SSR + 静的配信]
    end

    R53[Route 53 + ACM<br/>DNS / SSL] --> FE
    R53 --> ALB

    subgraph AWS[AWS]
        direction TB

        subgraph Fargate[ECS Fargate<br/>マネージドコンテナ]
            ALB[NestJS API<br/>最小 1 タスク常駐<br/>cold start 回避]
        end

        subgraph EC2[EC2 専用 VM<br/>t4g.small]
            GoWorker[Go 採点ワーカー]
            DockerEngine[Docker Engine]
            Containers[使い捨てサンドボックス<br/>コンテナ群]
            GoWorker -.->|"docker.sock"| DockerEngine
            DockerEngine --> Containers
        end

        subgraph RDS[RDS PostgreSQL<br/>db.t4g.micro]
            PG[(users / problems / submissions /<br/>jobs テーブル兼任)]
        end

        ECR[ECR<br/>コンテナレジストリ]
        Secrets[Secrets Manager /<br/>Parameter Store]
        Budget[AWS Budgets<br/>月額上限アラート]
    end

    subgraph Upstash[Upstash<br/>サーバレス Redis]
        Redis[(キャッシュ /<br/>セッション /<br/>レート制限)]
    end

    ALB --> PG
    ALB --> Redis
    PG -. LISTEN/NOTIFY .-> GoWorker
    GoWorker --> PG
    GoWorker -. キャッシュ参照 .- Redis
    Fargate -.イメージ pull.- ECR
    EC2 -.イメージ pull.- ECR
    Fargate -.シークレット取得.- Secrets
    EC2 -.シークレット取得.- Secrets

    classDef store fill:#e8f4ff,stroke:#4a90e2;
    classDef external fill:#fff7e6,stroke:#ff9800;
    classDef compute fill:#f0fff0,stroke:#4caf50;
    class PG,Redis store;
    class CDN,Upstash external;
    class Fargate,EC2 compute;
```

**配置の責務分離（責務 → 配置 → 採用理由）**：

| コンポーネント | 配置 | 採用理由 |
|---|---|---|
| Frontend | Vercel（エッジ CDN） | Next.js とのファーストパーティ統合、無料枠、SSR + 静的配信のグローバル分散（→ [ADR 0013](../../adr/0013-vercel-for-frontend-hosting.md)） |
| Backend API | ECS Fargate（マネージドコンテナ） | 軽量・水平スケール、Docker 操作不要、最小タスク 1 で cold start 回避 |
| 採点ワーカー | EC2 専用 VM | **Docker Engine が必要**、`docker.sock` 操作権限を API から分離（最小権限原則） |
| DB（兼ジョブキュー） | RDS PostgreSQL | 永続化、バックアップ、PITR、無料枠活用 |
| キャッシュ | Upstash Redis（サーバレス） | 消えても OK な高頻度アクセス、無料枠、ElastiCache よりコスト効率 |
| シークレット | Secrets Manager / Parameter Store | API キー・OAuth Secret・SESSION_SECRET の集中管理 |
| コンテナレジストリ | ECR | サンドボックスイメージ・API イメージのバージョニング |
| コスト管理 | AWS Budgets | 月額上限アラート（[01 非機能要件: コスト](./01-non-functional.md#コスト) と連動） |

**API と採点ワーカーを別計算リソースに分けている設計上の意図**：

- **権限の最小化**：API 側に `docker.sock` を持たせない（脱獄リスク低減）
- **スケール特性の違い**：API は Fargate で水平スケール、ワーカーは EC2 で goroutine 並列
- **failure isolation**：ワーカークラッシュが API 可用性に波及しない

→ 具体的な AWS サービス名・無料枠・コスト試算は [05-runtime-stack: インフラ](./05-runtime-stack.md#インフラ)
