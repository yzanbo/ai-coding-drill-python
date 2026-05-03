# 04. アーキテクチャ・インフラ構成

> **このドキュメントの守備範囲**：システム全体の論理構造、コンポーネントの責務、データ・ジョブの流れ。
> **使うフレームワーク・ライブラリ・サービスの具体名や選定理由**は [07_tech_stack.md](./07_tech_stack.md) を参照。

---

## 全体構成（概念図）

```
[User Browser]
     |
     v
[Frontend (Next.js / TS)] --- [CDN]
     |
     v
[Backend API (NestJS / TS)]
     |
     +--> [Auth]
     |
     +--> [Problems] --------> [PostgreSQL]
     |
     +--> [LLM Client] -------> [LLM API (Claude)]
     |
     +--> [Job Queue (Postgres: jobs table, SKIP LOCKED)]
               |
               +--> [採点ワーカー (Go)]
                       |
                       +--> [Sandbox Runner (Docker → gVisor → Firecracker)]
     |
     +--> [Observability]
              |
              +--> [Logs / Traces / Metrics]
              +--> [Error tracking]
```

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

→ 採用技術・ライブラリは [07: フロントエンド](./07_tech_stack.md#フロントエンド)

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

→ 採用フレームワーク・ライブラリ・選定理由は [07: バックエンド API](./07_tech_stack.md#バックエンド-api-nestjs--typescript)

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

→ テーブル設計・採用ライブラリ・選定理由は [07: ジョブキュー](./07_tech_stack.md#ジョブキューpostgres-select-for-update-skip-locked)

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

→ 採用言語・ライブラリ・選定理由は [07: 採点ワーカー](./07_tech_stack.md#採点ワーカーgo)

### サンドボックスランナー（Go ワーカー内で実行）

#### 使い捨てコンテナ方式
ジョブごとに採点コンテナを生成 → 実行 → 破棄。
- 起動オーバーヘッドは約 200ms（採点本体の 5〜15%、許容範囲）
- 前回実行の影響が原理的に残らない強い隔離保証を優先
- スループットが問題化した場合は Phase 2 以降でウォームプール / Firecracker への移行を検討

#### 段階的な隔離強化
- 初期実装：Docker + 制限付き（`--network none`, `--memory`, `--cpus`, `--read-only`, 非 root, tmpfs `/tmp`）
- 発展：gVisor で追加のシステムコール隔離
- さらに発展：Firecracker microVM で起動速度・隔離強度向上
- 各方式の比較を README にベンチマーク付きで記載

→ 実行対象・テストランナー等の詳細は [07: サンドボックス](./07_tech_stack.md#サンドボックス)

### データストア
- **PostgreSQL**：ユーザー、問題、解答履歴、ジョブキュー（`jobs` テーブル）
- **Redis**：LLM レスポンスキャッシュ、セッション、レート制限（**ジョブキュー用途では使わない**）

→ 採用バージョン・ORM・ホスティング先は [07: データベース / キャッシュ](./07_tech_stack.md#データベース)

---

## 1 ジョブが流れる完全な経路

ユーザーが解答を送信した瞬間からの流れ：

```
[1] ブラウザ
    POST /api/submissions { code: "..." } → NestJS

[2] NestJS（GradingController → GradingService）
    BEGIN;
      INSERT INTO submissions (...) RETURNING id;
      INSERT INTO jobs (type, payload, state) VALUES ('grade', ..., 'queued') RETURNING id;
      NOTIFY new_job, '<jobId>';
    COMMIT;
    レスポンス: 202 Accepted { submissionId, jobId }

[3] ブラウザ
    レスポンス受信、TanStack Query で submissionId をポーリング開始

[4] Go ワーカー（別 VM、ずっと LISTEN 中）
    NOTIFY を受信 → 即 SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1
    → ジョブ取得 → state='running', locked_by='worker-1' に更新
    → COMMIT（行ロック解放）

[5] Go ワーカー
    ContainerCreate → ContainerStart
    [採点コンテナで Vitest 実行]
    ContainerWait（タイムアウト 5 秒）→ ContainerLogs → ContainerRemove

[6] Go ワーカー
    UPDATE jobs SET state='done', result=... WHERE id=<jobId>;
    UPDATE submissions SET status='graded', score=... WHERE id=<submissionId>;

[7] ブラウザ
    次のポーリングで status='graded' を受信 → 結果表示
```

---

## インフラの論理配置

### クラウド：AWS に確定
- 求人需要・情報量・エコシステムを最重視
- マルチクラウド（GCP 併用等）はメリットより複雑度のコストが上回るため不採用
- AWS 内で IAM・ネットワーク・観測性を綺麗に設計することにフォーカス

### 物理配置（責務分離）

| コンポーネント | 配置 | 理由 |
|---|---|---|
| Frontend | エッジ CDN | 静的配信・SSR、グローバル分散 |
| Backend API | マネージドコンテナ | 軽量・水平スケール、Docker 操作不要 |
| 採点ワーカー | 専用 VM | Docker Engine が必要、`docker.sock` 操作権限を分離 |
| DB（兼ジョブキュー） | マネージド DB | 永続化、バックアップ、PITR |
| キャッシュ | サーバレス Redis | 消えても OK な高頻度アクセス |

→ 具体的な AWS サービス名・無料枠・コスト試算は [07: インフラ](./07_tech_stack.md#インフラ)
