---
paths:
  - "apps/grading-worker/**/*"
---

# 採点ワーカー開発ルール（Go）

採点ワーカーは Go で実装する独立プロセス。Postgres `jobs` テーブルからジョブを取得し、Docker でサンドボックス採点を実行する。詳細な選定理由は [ADR 0016](../../docs/adr/0016-go-for-grading-worker.md)。

## モジュール構成

```
apps/grading-worker/
├── cmd/
│   └── worker/
│       └── main.go              # エントリポイント
├── internal/
│   ├── job/                     # ジョブ取得・状態遷移
│   │   ├── claim.go             # SELECT ... FOR UPDATE SKIP LOCKED
│   │   ├── listener.go          # LISTEN/NOTIFY
│   │   └── reclaim.go           # スタックジョブ回収
│   ├── sandbox/                 # Docker クライアント、採点コンテナ管理
│   │   ├── runner.go            # コンテナ作成・実行・破棄
│   │   └── result.go            # 結果パース（Vitest 出力）
│   ├── db/                      # Postgres 接続（pgx）
│   ├── schema/                  # JSON Schema から生成された型（gitignore）
│   ├── log/                     # 構造化ログ（log/slog）
│   ├── otel/                    # OpenTelemetry セットアップ
│   └── config/                  # 環境変数読み込み
├── sandbox/                     # 採点用コンテナのイメージ定義
│   ├── Dockerfile
│   └── package.json             # Vitest + tsx
├── go.mod
├── go.sum
├── Dockerfile                   # ワーカー本体のコンテナイメージ
└── package.json                 # Turborepo 統合用（go build 等を script で呼ぶ）
```

## 設計原則

### Web フレームワークは使わない

ヘルスチェック程度の HTTP しか必要ないため、標準 `net/http` のみを使う。Echo / Gin / Chi 等は採用しない。

### 並列処理は goroutine + context

- 1 ワーカープロセス内で複数の goroutine を立て並列にジョブ処理
- `context.Context` でタイムアウト・キャンセルを伝播
- グレースフルシャットダウン：`signal.NotifyContext` で SIGTERM を受けて in-flight ジョブ完了を待つ

### 行ロックを Docker 実行中ずっと握らない

ジョブ取得は短いトランザクションで `state='running'`, `locked_at=now()`, `locked_by` を更新してすぐコミット → 別トランザクションで Docker 実行 → 完了後に結果を UPDATE。詳細は [02-architecture.md: ジョブキュー](../../docs/requirements/2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked)。

### スタックジョブのリクレイム

`locked_at < now() - interval '5 min'` のレコードを定期的に `state='queued'` に戻す（attempts++）。最大試行回数超過で `state='dead'`。

## ライブラリ

| 用途 | ライブラリ |
|---|---|
| HTTP / ヘルスチェック | 標準 `net/http` |
| Docker 操作 | `github.com/docker/docker/client` |
| Postgres 接続 | `github.com/jackc/pgx/v5`（LISTEN/NOTIFY 対応） |
| Redis 接続（必要なら） | `github.com/redis/go-redis/v9` |
| 構造化ログ | 標準 `log/slog` |
| OpenTelemetry | `go.opentelemetry.io/otel` |
| 設定管理 | `github.com/caarlos0/env/v11` |
| テスト | 標準 `testing` + `github.com/stretchr/testify` |
| JSON Schema → Go struct 生成 | `quicktype`（npm 経由で実行） |

## ジョブ取得のパターン

### LISTEN/NOTIFY + 低頻度ポーリングのハイブリッド

```go
// pseudo
func runWorker(ctx context.Context) {
    backoff := time.Second
    maxBackoff := 10 * time.Second
    poll := time.NewTicker(30 * time.Second)
    defer poll.Stop()

    for {
        select {
        case <-ctx.Done():
            return
        case <-listener.Notify():       // NOTIFY 受信
            backoff = time.Second
        case <-poll.C:                  // 30 秒ごとのポーリング（取りこぼし対策）
        }

        job, err := claimNextJob(ctx)
        if err != nil { /* log + sleep + continue */ }
        if job == nil {
            time.Sleep(backoff)
            backoff = min(backoff*2, maxBackoff)
            continue
        }
        backoff = time.Second
        processJob(ctx, job)
    }
}
```

### `SELECT FOR UPDATE SKIP LOCKED` の SQL

```go
// claimNextJob 内
const sqlClaim = `
WITH next AS (
  SELECT id FROM jobs
   WHERE queue = $1 AND state = 'queued' AND run_at <= now()
   ORDER BY run_at
   FOR UPDATE SKIP LOCKED
   LIMIT 1
)
UPDATE jobs SET
  state = 'running',
  locked_at = now(),
  locked_by = $2,
  attempts = attempts + 1,
  updated_at = now()
WHERE id IN (SELECT id FROM next)
RETURNING id, type, payload, attempts;
`
```

## Docker クライアント（DooD）

ワーカーはホストの Docker Engine を `/var/run/docker.sock` 経由で操作する。**Docker in Docker（DinD）は使わない**（→ [SYSTEM_OVERVIEW.md](../../SYSTEM_OVERVIEW.md)）。

```go
import "github.com/docker/docker/client"

cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
defer cli.Close()

// コンテナ作成
resp, err := cli.ContainerCreate(ctx, &container.Config{
    Image: "ai-coding-drill-sandbox:latest",
    Cmd:   []string{"vitest", "run"},
}, &container.HostConfig{
    NetworkMode: "none",
    Resources: container.Resources{
        Memory:    256 * 1024 * 1024,
        NanoCPUs:  500_000_000,         // 0.5 CPU
    },
    ReadonlyRootfs: true,
    Tmpfs:          map[string]string{"/tmp": ""},
}, nil, nil, "")
```

## 採点コンテナの制約

すべてのコンテナで以下を強制する：

- `--network none`：ネットワーク完全遮断
- `--memory 256m`：メモリ上限
- `--cpus 0.5`：CPU 上限
- `--read-only`：ルート FS 読み取り専用
- `--tmpfs /tmp:rw,size=64m`：書き込みは /tmp のみ
- `--user 1000:1000`：非 root 実行
- 実行タイムアウト：5 秒

## エラーハンドリング

- Go の流儀：`error` 戻り値を必ずチェック、`%w` で wrap
- ジョブ実行エラーは `last_error` カラムに記録
- リトライ可能なエラー（DB 接続エラー等）と不可（コードのコンパイルエラー等）を区別
- パニックは `recover()` で吸収しジョブを `failed` 状態に遷移、ワーカー本体は継続稼働

## 構造化ログ

```go
slog.InfoContext(ctx, "job claimed",
    "job_id", job.ID,
    "type", job.Type,
    "attempts", job.Attempts,
)
```

- 全ログに JSON 形式
- `trace_id` / `span_id` を OTel から自動付与
- LLM 呼び出しは行わないが、Docker 実行レイテンシ・採点結果メトリクスは出力する

## OpenTelemetry

採点 1 件あたりのスパン構成：

```
[grade_job]
  ├─ [job.claim]                # ジョブ取得 SQL
  ├─ [sandbox.create]           # ContainerCreate
  ├─ [sandbox.run]              # ContainerStart + Wait
  ├─ [sandbox.collect]          # Logs 取得
  ├─ [sandbox.cleanup]          # Remove
  └─ [job.complete]              # state='done' 更新
```

## コーディング規約

### コードスタイル

- `gofmt` でフォーマット、`golangci-lint` でリント（→ [ADR 0019](../../docs/adr/0019-go-code-quality.md)）
- `golangci-lint` の有効リンター：`errcheck`, `govet`, `staticcheck`, `ineffassign`, `unused`, `gofumpt`, `gosec`
- 命名：パッケージは小文字 1 単語、エクスポートは `PascalCase`、内部は `camelCase`
- インターフェースは小さく分割、`io.Reader` 級の単一メソッドが理想

### パッケージ構成

- `cmd/<name>/main.go` — エントリポイント
- `internal/` — 外部から import されない実装
- 公開 API はパッケージ単位で最小化

### テスト

- 標準 `testing` + `testify`（`assert`, `require`）
- テストファイルは対象と同じ階層に `*_test.go`
- テーブル駆動テストを推奨
- 統合テスト：testcontainers-go で Postgres / Docker を起動してから検証

### グレースフルシャットダウン

```go
func main() {
    ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
    defer stop()

    // ワーカー起動
    var wg sync.WaitGroup
    for i := 0; i < concurrency; i++ {
        wg.Add(1)
        go func() { defer wg.Done(); runWorker(ctx) }()
    }
    <-ctx.Done()
    wg.Wait()  // in-flight ジョブの完了を待つ
}
```

## コマンド

```bash
# Turborepo 経由
pnpm --filter @ai-coding-drill/grading-worker dev      # ローカル実行
pnpm --filter @ai-coding-drill/grading-worker build    # バイナリビルド
pnpm --filter @ai-coding-drill/grading-worker test     # テスト

# Go 直接
cd apps/grading-worker
go run ./cmd/worker
go test ./...
golangci-lint run

# サンドボックスイメージ
pnpm sandbox:build      # ai-coding-drill-sandbox イメージビルド
```

## 環境変数

- `DATABASE_URL` — Postgres 接続文字列
- `REDIS_URL` — LLM キャッシュ参照時のみ（採点本体では使わない）
- `WORKER_ID` — `locked_by` に書く識別子（既定はホスト名）
- `WORKER_CONCURRENCY` — 並列 goroutine 数（既定 4）
- `SANDBOX_IMAGE` — 採点コンテナのイメージタグ（既定 `ai-coding-drill-sandbox:latest`）
- `JOB_TIMEOUT_SECONDS` — 採点タイムアウト（既定 5）
- `RECLAIM_AFTER_MINUTES` — スタックジョブとみなす経過時間（既定 5）
