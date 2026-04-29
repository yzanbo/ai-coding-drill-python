# システム全体構成

NestJS（API）と Go ワーカー（採点）は **物理的に別のマシンで動く**設計。理由は「Docker 操作権限が必要なホストと、ユーザーリクエストを受けるホストを分けたい」ため。

---

## 1. 物理配置の全体図

```
┌───────────────────────────────────────────────────────────────────────┐
│                         インターネット                                  │
└────────────────────────┬─────────────────────┬────────────────────────┘
                         │                     │
                         ▼                     ▼
              ┌──────────────────┐    ┌──────────────────┐
              │  Vercel (CDN)    │    │  ユーザーブラウザ  │
              │  - Next.js       │    │  - CodeMirror 6  │
              └────────┬─────────┘    └─────────┬────────┘
                       │                        │
                       └─────────┬──────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  NestJS API             │  ★ ECS Fargate
                    │  - Auth                 │
                    │  - 問題CRUD             │
                    │  - LLM 呼び出し         │
                    │  - ジョブ INSERT        │
                    └──┬───────────────┬──────┘
                       │               │
              ┌────────▼─────┐  ┌──────▼──────┐
              │ Postgres     │  │ Redis       │  ★ マネージド
              │ (RDS)        │  │ (Upstash)   │
              │ - users      │  │ - LLM cache │
              │ - problems   │  │ - sessions  │
              │ - submissions│  └─────────────┘
              │ - jobs ★    │
              └──┬───────────┘
                 │ LISTEN/NOTIFY + 低頻度ポーリング
                 ▼
       ┌────────────────────────────────┐
       │  採点ワーカー（Go）             │  ★ EC2 t4g.small
       │  - jobs 取得                    │
       │  - Docker クライアント          │
       │  - 結果書き戻し                 │
       └────┬───────────────────────────┘
            │ Docker API
            ▼
       ┌────────────────────────────────┐
       │  Docker Engine（同 VM）         │
       └────┬───────────────────────────┘
            │ ContainerCreate / Start / Remove
            ▼
       ┌────────────────────────────────┐
       │  採点コンテナ（使い捨て）        │
       │  - tsx + Vitest                 │
       │  - --network none               │
       │  - --memory 256m                │
       └────────────────────────────────┘
```

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

```
[1] ブラウザ
    POST /api/submissions { code: "..." } → NestJS

[2] NestJS（GradingController → GradingService）
    BEGIN;
      INSERT INTO submissions (...) RETURNING id;
      INSERT INTO jobs (type, payload, state) VALUES ('grade', ..., 'queued') RETURNING id;
      NOTIFY new_job, '<jobId>';
    COMMIT;
    レスポンス: 202 Accepted

[3] ブラウザ
    TanStack Query で submissionId をポーリング開始

[4] Go ワーカー（別 VM、LISTEN 中）
    NOTIFY 受信 → SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1
    → state='running', locked_by='worker-1' に UPDATE
    → COMMIT（行ロック解放）

[5] Go ワーカー
    cli.ContainerCreate / Start / Wait / Logs / Remove
    [採点コンテナで Vitest 実行、5 秒タイムアウト]

[6] Go ワーカー
    UPDATE jobs SET state='done', result=... WHERE id=<jobId>;
    UPDATE submissions SET status='graded', score=... WHERE id=<submissionId>;

[7] ブラウザ
    次のポーリングで status='graded' を受信 → 結果表示
```

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
