# システム全体構成

NestJS（API）と Go ワーカー（採点）は **物理的に別のマシンで動く**設計。理由は「Docker 操作権限が必要なホストと、ユーザーリクエストを受けるホストを分けたい」ため。

---

## 1. 物理配置の全体図

```mermaid
flowchart TB
    Browser["ユーザーブラウザ<br/>- CodeMirror 6"]
    CDN["Vercel CDN<br/>- Next.js"]

    subgraph aws["AWS"]
        API["NestJS API<br/>★ ECS Fargate<br/>- Auth<br/>- 問題 CRUD<br/>- LLM 呼び出し<br/>- ジョブ INSERT"]
        DB[("Postgres（RDS）<br/>★ マネージド<br/>- users<br/>- problems<br/>- submissions<br/>- jobs（兼ジョブキュー）")]
        Redis[("Redis（Upstash）<br/>★ マネージド<br/>- LLM cache<br/>- sessions")]

        subgraph workerVM["EC2 t4g.small（単一 VM）"]
            Worker["採点ワーカー（Go）<br/>- jobs 取得<br/>- Docker クライアント<br/>- 結果書き戻し"]
            DockerEngine["Docker Engine<br/>（同 VM 内）"]
            Sandbox["採点コンテナ<br/>（使い捨て）<br/>- tsx + Vitest<br/>- --network none<br/>- --memory 256m<br/>- read-only FS<br/>- 非 root<br/>- 5 秒タイムアウト"]
        end
    end

    Browser --> CDN
    CDN --> API
    Browser -.->|"HTTPS API"| API
    API --> DB
    API --> Redis
    DB -.->|"LISTEN/NOTIFY + ポーリング"| Worker
    Worker --> DB
    Worker -->|"Docker API"| DockerEngine
    DockerEngine -->|"Create / Start / Remove"| Sandbox

    classDef store fill:#dbeafe,stroke:#1e40af,color:#1e3a8a
    classDef compute fill:#dcfce7,stroke:#166534,color:#14532d
    classDef edge fill:#fef3c7,stroke:#92400e,color:#78350f
    class DB,Redis store
    class API,Worker,DockerEngine,Sandbox compute
    class Browser,CDN edge
```

**読み方**：
- 実線 = 同期 HTTP / SQL、点線 = 非同期通知（LISTEN/NOTIFY）または最初の HTTPS リクエスト経路
- 青 = ストア、緑 = コンピュート、橙 = エッジ
- `★` 注記は配置種別を示す（マネージドサービス / 単一 VM 等）
- `jobs ★（ジョブキュー兼任）` は Postgres 内のテーブルでありながらジョブキューを兼任（→ [ADR 0001](docs/adr/0001-postgres-as-job-queue.md)）

---

## 2. NestJS と Go ワーカーを別マシンに分ける理由

| 観点 | 理由 |
|---|---|
| セキュリティ | Go ワーカーは `docker.sock` 操作権限が必要 = root 相当。ユーザーリクエストを受ける NestJS と同居させない |
| スケール特性 | NestJS：HTTP リクエスト数で水平スケール。Go ワーカー：CPU 集約的なコンテナ実行 |
| デプロイ環境 | NestJS：Cloud Run / Fargate（マネージド）。Go ワーカー：Docker Engine が必要なので EC2 |
| 障害分離 | 採点が暴走しても API は止まらない、API デプロイ中も採点継続可能 |

---

## 3. 各コンポーネントの責務

### Frontend（Next.js on Vercel）
- ページレンダリング（RSC）
- 認証セッション保持
- NestJS API を `fetch` で呼び出し
- 採点結果ポーリング（TanStack Query）
- CodeMirror 6 でコード入力

### NestJS API（ECS Fargate）
- Module 構成：Auth / Problems / Generation / Grading / Observability
- 認証（GitHub OAuth）、問題 CRUD、LLM 呼び出し、ジョブ INSERT、結果取得 API
- Docker 操作はしない

### Postgres（RDS）
- アプリデータ（users, problems, submissions）
- `jobs` テーブル（ジョブキュー兼任）
- LISTEN/NOTIFY のチャンネル提供

### Redis（Upstash）
- LLM レスポンスキャッシュ、セッション、レート制限
- ジョブキューには使わない

### Go 採点ワーカー（EC2）
- 常駐プロセス、ループで動く
- Postgres `jobs` を LISTEN/NOTIFY + ポーリングで監視
- ジョブ取得 → Docker API でサンドボックス起動 → 結果回収 → 書き戻し
- Docker Engine と同じ VM に住み、`/var/run/docker.sock` を直接使う

### 採点コンテナ（使い捨て）
- ジョブごとに 1 つ作って 1 つ捨てる
- Node.js + tsx + Vitest
- ネットワーク遮断、メモリ制限、読み取り専用 FS、非 root、5 秒タイムアウト

---

## 4. 1 ジョブが流れる経路

```mermaid
sequenceDiagram
    participant Browser as ブラウザ
    participant API as NestJS API
    participant DB as Postgres
    participant Worker as Go 採点ワーカー
    participant Sandbox as 採点コンテナ

    Note over API: GradingController から GradingService 経由で呼び出し
    Note over Worker: 別 VM、LISTEN 中

    Browser->>API: POST /api/submissions（code 本文を含む）
    activate API
    Note over API,DB: 同一トランザクション（BEGIN）
    API->>DB: INSERT INTO submissions（カラム省略）RETURNING id
    API->>DB: INSERT INTO jobs（type, payload, state, queued 等）RETURNING id
    API->>DB: NOTIFY new_job, jobId
    Note over API,DB: COMMIT
    API-->>Browser: 202 Accepted（submissionId を返す）
    deactivate API

    Note over Browser: TanStack Query で submissionId をポーリング開始

    DB-->>Worker: NOTIFY 受信
    activate Worker
    Worker->>DB: SELECT FOR UPDATE SKIP LOCKED LIMIT 1
    Worker->>DB: UPDATE jobs SET state=running, locked_by=worker-1
    Note over Worker,DB: COMMIT（行ロック解放）

    Worker->>Sandbox: cli.ContainerCreate / Start
    activate Sandbox
    Note over Sandbox: tsx + Vitest 実行
    Note over Sandbox: 5 秒タイムアウト
    Note over Sandbox: --network none / --memory 256m
    Worker->>Sandbox: cli.Wait / Logs
    Sandbox-->>Worker: 標準出力 / 終了コード
    Worker->>Sandbox: cli.Remove
    deactivate Sandbox

    Worker->>DB: UPDATE jobs SET state=done, result（結果データ） WHERE id=jobId
    Worker->>DB: UPDATE submissions SET status=graded, score WHERE id=submissionId
    deactivate Worker

    Browser->>API: ポーリング継続
    API->>DB: SELECT submission
    API-->>Browser: status=graded を受信、結果表示
```

**読み方**：
- 実線矢印 = 同期呼び出し（HTTP / SQL）、点線矢印 = 非同期通知（NOTIFY）または HTTP レスポンス
- `activate` / `deactivate` は処理が走っている期間を示す
- 上から下に時系列。`Note over X,Y` はトランザクション境界・処理内容の補足
- SQL リテラルのシングルクォートと `→` 矢印・`...` 省略記号は Mermaid パーサ事故回避のため平文に置換（実装時は `'queued'` 等の正しい SQL リテラルを使う）

---

## 5. ローカル開発（Docker Compose）

本番と違って 1 マシンで動かす：

```yaml
services:
  postgres:
    image: postgres:16
  redis:
    image: redis:7
  nestjs:
    build: ./apps/api
    depends_on: [postgres, redis]
  worker:
    build: ./apps/grading-worker
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # DooD でホスト Docker を使う
    depends_on: [postgres]
  next:
    build: ./apps/web
    depends_on: [nestjs]
```

`docker compose up` で全体起動。

---

## 6. デプロイ環境

| コンポーネント | デプロイ先 | 形態 |
|---|---|---|
| Next.js | Vercel | サーバレス |
| NestJS API | ECS Fargate | コンテナ |
| Postgres | RDS | マネージド |
| Redis | Upstash | サーバレス |
| Go ワーカー | EC2 t4g.small | VM 直（Docker Engine 必要） |

コスト目安：月 $10〜30。

---

## 7. 一行まとめ

> NestJS は「ジョブを Postgres に登録するだけ」、Go ワーカーは別 VM で「Postgres を見張りながら、Docker Engine に採点コンテナを作らせる」、Postgres が両者をつなぐ仲介役。
