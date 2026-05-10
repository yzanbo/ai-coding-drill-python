---
paths:
  - "apps/workers/**/*"
---

# Worker 開発ルール（Go）

Worker 群は Go で実装する独立プロセス。Postgres `jobs` テーブルからジョブを取得し、種別ごとの処理（採点・問題生成）を実行する。詳細な選定理由は [ADR 0016](../../docs/adr/0016-go-for-grading-worker.md)、Worker のグルーピングと LLM の所在は [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)。

## ディレクトリ構成

Worker は `apps/workers/<name>/` グループ配下に **1 Worker = 1 独立 Go module** で配置（→ [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）：

```
apps/workers/
├── grading/                    # 採点 Worker（独立 Go module）
│   ├── cmd/
│   │   └── grading/
│   │       └── main.go         # エントリポイント
│   ├── internal/
│   │   ├── job/                # ジョブ取得・状態遷移
│   │   │   ├── claim.go        # SELECT ... FOR UPDATE SKIP LOCKED
│   │   │   ├── listener.go     # LISTEN/NOTIFY
│   │   │   └── reclaim.go      # スタックジョブ回収
│   │   ├── sandbox/            # Docker クライアント、採点コンテナ管理
│   │   │   ├── runner.go       # コンテナ作成・実行・破棄
│   │   │   └── result.go       # 結果パース（Vitest JSON 出力。将来多言語対応時は言語別 adapter で切替、ADR 0009）
│   │   ├── judge/              # judge LLM 呼び出し（ADR 0040）
│   │   ├── db/                 # Postgres 接続（pgx）
│   │   ├── jobtypes/           # JSON Schema → quicktype で生成された Go struct（gitignore）
│   │   ├── log/                # 構造化ログ（log/slog）
│   │   ├── otel/               # OpenTelemetry セットアップ
│   │   └── config/             # 環境変数読み込み
│   ├── prompts/                # judge プロンプト YAML（ADR 0040）
│   ├── sandbox/                # 採点用コンテナのイメージ定義
│   │   └── Dockerfile
│   ├── go.mod
│   ├── go.sum
│   └── Dockerfile              # Worker 本体のコンテナイメージ
│
└── generation/                 # 問題生成 Worker（独立 Go module、将来追加）
    ├── cmd/generation/main.go
    ├── internal/
    │   ├── job/
    │   ├── llm/                # 生成 LLM 呼び出し
    │   └── ...
    ├── prompts/                # generation プロンプト YAML
    ├── go.mod
    └── go.sum
```

## 設計原則

### Web フレームワークは使わない

ヘルスチェック程度の HTTP しか必要ないため、標準 `net/http` のみを使う。Echo / Gin / Chi 等は採用しない。

### 並列処理は goroutine + context

- 1 Worker プロセス内で複数の goroutine を立て並列にジョブ処理
- `context.Context` でタイムアウト・キャンセルを伝播
- グレースフルシャットダウン：`signal.NotifyContext` で SIGTERM を受けて in-flight ジョブ完了を待つ

### 行ロックを長時間握らない

ジョブ取得は短いトランザクションで `state='running'`, `locked_at=now()`, `locked_by` を更新してすぐコミット → 別トランザクションで処理（Docker 実行 / LLM 呼び出し）→ 完了後に結果を UPDATE。詳細は [02-architecture.md: ジョブキュー](../../docs/requirements/2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked)。

### スタックジョブのリクレイム

`locked_at < now() - interval '5 min'` のレコードを定期的に `state='queued'` に戻す（attempts++）。最大試行回数超過で `state='dead'`。

### LLM 呼び出しは Worker 内に閉じる

採点 LLM（judge）も問題生成 LLM も Worker 内で呼び出す（→ [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。Backend は呼ばない。

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
| LLM SDK | プロバイダ別の Go SDK or `net/http` 直叩き（→ [ADR 0007](../../docs/adr/0007-llm-provider-abstraction.md) の抽象化） |
| テスト | 標準 `testing` + `github.com/stretchr/testify` |
| JSON Schema → Go struct 生成 | `quicktype --src-lang schema`（npm 経由で実行、→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)） |

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

## Docker クライアント（DooD）— 採点 Worker のみ

採点 Worker はホストの Docker Engine を `/var/run/docker.sock` 経由で操作する。**Docker in Docker（DinD）は使わない**（→ [SYSTEM_OVERVIEW.md](../../SYSTEM_OVERVIEW.md)）。

```go
import "github.com/docker/docker/client"

cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
defer cli.Close()

// コンテナ作成
resp, err := cli.ContainerCreate(ctx, &container.Config{
    Image: "ai-coding-drill-sandbox:latest",
    // 初期 TS（tsx + Vitest）。将来多言語対応時は言語別 image / Cmd を adapter で切替（ADR 0009 / 01-overview.md）
    Cmd:   []string{"vitest", "run", "--reporter=json"},
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
- パニックは `recover()` で吸収しジョブを `failed` 状態に遷移、Worker 本体は継続稼働

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
- Docker 実行レイテンシ・LLM 呼び出しレイテンシ・採点結果メトリクスを出力

## OpenTelemetry

> 観測性スタック（OTLP 送信先：Loki / Tempo / Prometheus + Sentry）の選定根拠は [ADR 0041](../../docs/adr/0041-observability-stack-grafana-and-sentry.md) を参照。

採点 1 件あたりのスパン構成（grading Worker の例）：

```
[grade_job]
  ├─ [job.claim]                # ジョブ取得 SQL
  ├─ [sandbox.create]           # ContainerCreate
  ├─ [sandbox.run]              # ContainerStart + Wait
  ├─ [sandbox.collect]          # Logs 取得
  ├─ [sandbox.cleanup]          # Remove
  ├─ [judge.invoke]             # judge LLM 呼び出し（ADR 0040）
  └─ [job.complete]             # state='done' 更新
```

問題生成 1 件あたりのスパン構成（generation Worker、R7 以降。R1〜R6 は grading Worker が兼務）：

```
[generate_problem_job]
  ├─ [job.claim]                # ジョブ取得 SQL
  ├─ [generation.invoke]        # 生成 LLM 呼び出し（ADR 0040）
  ├─ [schema.validate]          # JSON Schema → quicktype 生成 Go struct でバリデーション
  ├─ [sandbox.run]              # 模範解答をサンドボックス検証
  ├─ [judge.invoke]             # 別プロバイダ Judge 評価
  └─ [job.complete]             # problems INSERT + state='done'
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

    var wg sync.WaitGroup
    for i := 0; i < concurrency; i++ {
        wg.Add(1)
        go func() { defer wg.Done(); runWorker(ctx) }()
    }
    <-ctx.Done()
    wg.Wait()  // in-flight ジョブの完了を待つ
}
```

## コマンド（mise）

タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（→ [ADR 0039](../../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）：

```bash
# 採点 Worker
mise run worker:grading:dev          # apps/workers/grading の go run
mise run worker:grading:test         # go test ./...
mise run worker:grading:lint         # golangci-lint run
mise run worker:grading:audit        # govulncheck ./...
mise run worker:grading:deps-check   # go mod tidy 後の差分チェック
mise run worker:grading:types-gen    # quicktype で Go struct 生成

# 問題生成 Worker（apps/workers/generation 着手時に有効化）
mise run worker:generation:dev
mise run worker:generation:test
mise run worker:generation:lint

# 横断（全 Worker）
mise run worker:test                 # 全 Worker の go test
mise run worker:lint                 # 全 Worker の golangci-lint
mise run worker:types-gen            # 全 Worker の Go struct 生成

# Go 直接（mise を介さない場合）
cd apps/workers/grading
go run ./cmd/grading
go test ./...
golangci-lint run

# サンドボックスイメージ
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

## 環境変数

- `DATABASE_URL` — Postgres 接続文字列
- `REDIS_URL` — LLM キャッシュ参照時のみ
- `WORKER_ID` — `locked_by` に書く識別子（既定はホスト名）
- `WORKER_CONCURRENCY` — 並列 goroutine 数（既定 4）
- `SANDBOX_IMAGE` — 採点コンテナのイメージタグ（採点 Worker のみ、既定 `ai-coding-drill-sandbox:latest`）
- `JOB_TIMEOUT_SECONDS` — タイムアウト秒（採点 Worker 既定 5）
- `RECLAIM_AFTER_MINUTES` — スタックジョブとみなす経過時間（既定 5）
- `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` — LLM 呼び出し設定（→ [ADR 0007](../../docs/adr/0007-llm-provider-abstraction.md)）
