---
paths:
  - "apps/workers/**/*"
---

# Worker 開発ルール（Go）

Worker 群は Go で実装する独立プロセス。Postgres `jobs` テーブルからジョブを取得し、種別ごとの処理（採点・問題生成）を実行する。詳細な選定理由は [ADR 0016](../../docs/adr/0016-go-for-grading-worker.md)、Worker のグルーピングと LLM の所在は [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)。

## ディレクトリ構成（両 Worker 共有 9 package パターン）

Worker は `apps/workers/<name>/` グループ配下に **1 Worker = 1 独立 Go module** で配置し、**両 Worker で同一の 9 package パターン**を使う（[ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)、配置決定の根拠と手順は [worker-layers.md §B](../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）。

**テンプレートツリー**（`<worker>` = `grading` / `generation`）：

```
apps/workers/<worker>/
├── go.mod / go.sum
├── .golangci.yml / .gitignore
├── README.md                       # 全体図 + 呼び出し方向 ASCII + やってはいけないこと
├── cmd/
│   └── <worker>/                   # binary 名 = <worker>（cmd/worker/ 共通名は不採用、対称性のため）
│       ├── README.md
│       └── main.go                 # エントリポイント、internal を組み立て + signal handling のみ
├── internal/                       # private packages（他 module から import 不可、Go 規約）
│   ├── README.md
│   ├── config/                     # 環境変数読み込み（caarlos0/env/v11）
│   ├── observability/              # slog + OpenTelemetry + (R4) Prometheus（lump、log/otel は分割しない）
│   ├── db/                         # pgx pool + transaction helpers（純 infrastructure）
│   ├── job/                        # claim / listener / reclaim / complete（queue domain logic、db を使う）
│   │   ├── claim.go                # SELECT ... FOR UPDATE SKIP LOCKED
│   │   ├── listener.go             # LISTEN/NOTIFY
│   │   └── reclaim.go              # スタックジョブ回収
│   ├── sandbox/                    # Docker SDK ラッパ + 隔離設定（両 Worker が同 image を起動）
│   │   ├── runner.go               # コンテナ作成・実行・破棄
│   │   └── result.go               # 結果パース（Vitest JSON 出力、ADR 0009）
│   ├── llm/                        # LLM プロバイダ抽象化（ADR 0007）。実装は internal/llm/<provider>/
│   ├── judge/                      # LLM-as-a-Judge prompt 整形 + response パース（grading: 解答評価 / generation: 問題評価）
│   ├── jobtypes/                   # JSON Schema → quicktype で生成された Go struct（gitignore、ADR 0006）
│   └── <worker>/                   # オーケストレーター（採点 / 生成フロー本体、main.go から呼ばれる）
└── prompts/                        # LLM プロンプト YAML（ADR 0040）
    └── <worker専用 subdir>/        # grading: judge/、generation: generation/ + judge/
```

**Worker 固有の差分**（テンプレートからの逸脱はこれだけ）：

| 差分項目 | grading | generation |
|---|---|---|
| `cmd/<worker>/` | `cmd/grading/` | `cmd/generation/` |
| orchestrator package | `internal/grading/`（採点フロー：job → sandbox + judge → db） | `internal/generation/`（生成フロー：job → llm + sandbox + judge → db） |
| sandbox Dockerfile 所有 | **所有**：`apps/workers/grading/sandbox/{Dockerfile,.dockerignore}` | **所有しない**：grading の `ai-coding-drill-sandbox:latest` image を Docker SDK で起動 |
| `prompts/` subdir | `prompts/judge/` | `prompts/generation/` + `prompts/judge/` |
| go module 名 | `github.com/yzanbo/.../apps/workers/grading` | `github.com/yzanbo/.../apps/workers/generation` |

## package 間の import 方向（両 Worker 共通、layer-based）

```
Layer 3（entrypoint）
  cmd/<worker>/                 → 全 internal/* を組み立て

Layer 2（orchestration）
  internal/<worker>/            → job, sandbox, judge, db, jobtypes
                                   ※ generation は llm も直接使う（問題生成本体は judge 経由しない）

Layer 1（domain）
  internal/job/                 → db, jobtypes
  internal/judge/               → llm, jobtypes

Layer 0（leaf / infrastructure）
  internal/config/              → caarlos0/env のみ
  internal/observability/       → slog + OTel SDK のみ
  internal/db/                  → pgx のみ
  internal/sandbox/             → Docker SDK のみ
  internal/llm/                 → HTTP client + provider SDK のみ
  internal/jobtypes/            → 生成物、標準ライブラリのみ
```

**import 可否表**（両 Worker で同じ表が対称適用される、`<worker>` を grading / generation に置換）：

| package | import してよい（internal） | import 禁止 |
|---|---|---|
| `cmd/<worker>/` | 全 `internal/*` | （上位なし） |
| `internal/<worker>/` | `job` / `sandbox` / `judge` / `db` / `jobtypes`（generation はさらに `llm`） | `cmd/` / `config`（main で組み立てて DI で受け取る） |
| `internal/job/` | `db` / `jobtypes` | `cmd/` / `<worker>` / `judge` / `llm` / `sandbox` |
| `internal/judge/` | `llm` / `jobtypes` | `cmd/` / `<worker>` / `job` / `db` / `sandbox` |
| `internal/db/` | （pgx のみ）| `cmd/` / 全 `internal/*` |
| `internal/sandbox/` | （Docker SDK のみ）| `cmd/` / 全 `internal/*` |
| `internal/llm/` | （HTTP / provider SDK のみ）| `cmd/` / 全 `internal/*` |
| `internal/config/` | （caarlos0/env のみ）| `cmd/` / 全 `internal/*` |
| `internal/observability/` | （slog + OTel SDK のみ）| 業務 package 全て |
| `internal/jobtypes/` | （標準ライブラリのみ、生成物のため終端）| 全て |

**補足ルール**：

- **依存は一方向**：A → B かつ B → A を作らない
- **両 Worker module 跨ぎの import は禁止**：`apps/workers/grading/internal/llm/` を `apps/workers/generation/` から import 不可（Go の `internal/` 規約 + 独立 module）。LLM 抽象化を再利用する時は同名 package を両 Worker に複製する（[ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) は当面コード重複を許容）
- **`internal/observability/` は context 経由で透過利用**：初期化は `cmd/<worker>/main.go` で 1 回だけ、業務 package は `slog.InfoContext(ctx, ...)` / `otel.Tracer("name").Start(ctx, ...)` を直接使う
- **`internal/config/` は entrypoint でのみ読む**：業務 package は `*Config` を引数で受け取る、`os.Getenv` を直接呼ばない
- **`internal/<worker>/` を集約点に**：ジョブ処理本体は orchestrator が `job` + `sandbox` + `judge` + `db`（generation は + `llm`）を組み合わせる

### OK / NG コード例

✅ **OK**：`cmd/grading/main.go` が全 `internal/*` を組み立てる
```go
package main

import (
    "github.com/yzanbo/.../apps/workers/grading/internal/config"
    "github.com/yzanbo/.../apps/workers/grading/internal/db"
    "github.com/yzanbo/.../apps/workers/grading/internal/grading"
    "github.com/yzanbo/.../apps/workers/grading/internal/judge"
    "github.com/yzanbo/.../apps/workers/grading/internal/llm"
    "github.com/yzanbo/.../apps/workers/grading/internal/llm/google"
    "github.com/yzanbo/.../apps/workers/grading/internal/observability"
    "github.com/yzanbo/.../apps/workers/grading/internal/sandbox"
)

func main() {
    cfg, _ := config.Load()
    logger, shutdown, _ := observability.Init(ctx, cfg)
    defer shutdown(ctx)
    pool, _ := db.NewPool(ctx, cfg)
    // LLM プロバイダ抽象化レイヤは registration pattern で循環インポートを回避する
    // (database/sql / image/png と同じ方式)。詳細は internal/llm/new.go。
    llm.Register(google.Name, google.New)
    // buildLLMConfig: cmd 層ローカルの helper (main.go に定義)。
    // config.Config (中立 struct) を llm.Config に詰め直す。
    // internal/config が llm を import 不可な Layer 0 制約のため cmd 層で変換する。
    llmProvider, _ := llm.New(buildLLMConfig(cfg))
    grading.Run(ctx, grading.Deps{Pool: pool, Sandbox: sandbox.New(...), Judge: judge.New(llmProvider, ...)})
}
```

❌ **NG**：`internal/llm/` が `internal/grading/` を import（逆流、Layer 0 → Layer 2）
```go
package llm

import "github.com/yzanbo/.../apps/workers/grading/internal/grading" // ← 禁止、依存方向は逆
```

❌ **NG**：`internal/jobtypes/` を手書きで拡張（quicktype 再生成で消える）
```go
package jobtypes
// types.go は quicktype 生成物。手書きの追加は再生成で消える
func (g *GradingJob) Custom() error { ... } // ← 禁止、wrapper struct を別 package で作る
```

❌ **NG**：別 Worker module から `internal/` を import（Go の `internal/` 規約違反）
```go
package generation_internal

import "github.com/yzanbo/.../apps/workers/grading/internal/llm" // ← コンパイルエラー
```

❌ **NG**：業務 package が `os.Getenv` を直接呼ぶ（`internal/config/` で集約すべき）
```go
package judge

import "os"

func New() *Judge {
    apiKey := os.Getenv("LLM_API_KEY") // ← 禁止、main で config.Load() → DI で受け取る
    ...
}
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

配送保証契約（at-least-once / 可視性タイムアウト 5 分 / 指数バックオフ 10s → 60s → `state='dead'` / handler 冪等性は Worker 責務）は [ADR 0046](../../docs/adr/0046-job-queue-delivery-guarantees.md) を SSoT として参照。本セクションは実装コード片に絞る。

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

採点 Worker はホストの Docker Engine を `/var/run/docker.sock` 経由で操作する。**Docker in Docker（DinD）は使わない**（採用根拠・代替案・セキュリティモデルの議論は → [ADR 0045](../../docs/adr/0045-sandbox-container-runtime-dood.md)、システム全体俯瞰は → [SYSTEM_OVERVIEW.md](../../SYSTEM_OVERVIEW.md)）。

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
  ├─ [judge.invoke]             # 別プロバイダ Judge 評価（MVP は Gemini 単独で例外保留、R2 で切替 / ADR 0049）
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

## 新規機能の追加パターン

新しいジョブ種別を追加する時の標準手順（`<job_type>` 例：`grade_problem` / `generate_problem`）：

1. `apps/api/app/schemas/jobs/<job_type>.py` に Pydantic で payload 定義
2. `mise run api:job-schemas-export` で `apps/api/job-schemas/<job_type>.json` を出力
3. `mise run worker:<worker>:types-gen` で対象 Worker の `internal/jobtypes/types.go` を quicktype で再生成（両 Worker に必要なら両方で実行）
4. `apps/workers/<worker>/internal/<worker>/`（orchestrator）に dispatch を追加：`switch job.Type { case "<job_type>": ... }`
5. 必要な package を拡張（`judge` のプロンプト追加 / `sandbox` の adapter 追加 等）。新たに package を切る必要があるなら **§ディレクトリ構成** の Layer ルールに従って配置
6. 単体テスト（`*_test.go`）と integration テスト（testcontainers-go）を追加
7. `mise run worker:<worker>:lint` / `worker:<worker>:test` を通してから commit

## コマンド（mise、両 Worker 対称）

タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（→ [ADR 0039](../../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。**両 Worker で同じ 6 タスクが対称に揃う**（grading のみ追加で `sandbox-build`）。

```bash
# 採点 Worker
mise run worker:grading:dev          # apps/workers/grading の go run ./cmd/grading
mise run worker:grading:test         # go test ./...
mise run worker:grading:lint         # golangci-lint run
mise run worker:grading:audit        # govulncheck ./...
mise run worker:grading:deps-check   # go mod tidy -diff（Go 1.23+）
mise run worker:grading:types-gen    # quicktype で internal/jobtypes/ 生成
mise run worker:grading:sandbox-build  # ai-coding-drill-sandbox:latest（両 Worker で共有）

# 問題生成 Worker（R0-8 で grading と対称にスキャフォールド済み）
mise run worker:generation:dev          # apps/workers/generation の go run ./cmd/generation
mise run worker:generation:test
mise run worker:generation:lint
mise run worker:generation:audit
mise run worker:generation:deps-check
mise run worker:generation:types-gen

# 横断（両 Worker 並列）
mise run worker:test                 # 両 Worker の go test
mise run worker:lint                 # 両 Worker の golangci-lint
mise run worker:types-gen            # 両 Worker の Go struct 生成

# Go 直接（mise を介さない場合）
cd apps/workers/grading              # または apps/workers/generation
go run ./cmd/grading                 # または ./cmd/generation
go test ./...
golangci-lint run

# サンドボックスイメージ（grading が所有、generation も同 image を共有起動）
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

## 環境変数（両 Worker 共通、`internal/config/` で集約）

> ローカル開発では `apps/workers/grading/.env.example` をコピーして `apps/workers/grading/.env` を作る。`mise.toml` の `[env] _.file` 設定により `mise run worker:grading:*` 経由のタスク起動時に自動 load される（ADR 0039）。`.env` は gitignore 済み。

- `DATABASE_URL` — Postgres 接続文字列
- `REDIS_URL` — LLM キャッシュ参照時のみ
- `WORKER_ID` — `locked_by` に書く識別子（既定はホスト名、`os.Hostname()` 失敗時はプレースホルダ `unknown-host`）
- `WORKER_CONCURRENCY` — 並列 goroutine 数（既定 4、**> 0 必須**）
- `SANDBOX_IMAGE` — サンドボックスのイメージタグ（両 Worker で同じ image を起動、既定 `ai-coding-drill-sandbox:latest`）
- `JOB_TIMEOUT_SECONDS` — タイムアウト秒（grading 既定 5、generation は LLM 呼び出しが長いため大きめが望ましい、`config/` 既定で個別調整、**> 0 必須**）
- `RECLAIM_AFTER_MINUTES` — スタックジョブとみなす経過時間（既定 5、**> 0 必須**）

> 数値項目の **「> 0 必須」** は `internal/config/config.go` の `validateRanges` が SSoT。違反時は `ErrInvalidRange` を wrap して `Load()` が起動を fail-fast させる（後段の goroutine spawn 0 個 / context.WithTimeout(0) で undefined behavior になるのを防ぐ）。
- `LLM_CONFIG_PATH` — LLM プロバイダ・モデル割り当て YAML のパス（既定 `llm.yaml`、apps/workers/grading/llm.yaml が SSoT。Worker 再ビルド不要で切替可能、→ [ADR 0007](../../docs/adr/0007-llm-provider-abstraction.md) / [ADR 0049](../../docs/adr/0049-initial-llm-model-selection.md)）
- `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — provider 別 API キー（YAML に書かず環境変数経由で渡す。Worker は使う provider 分だけ設定すれば足りる）
