# apps/workers/grading

Go 採点ワーカー。**コード実装着手前の skeleton（プロンプトのみ配置済み）**。

## 役割（[ADR 0016](../../../docs/adr/0016-go-for-grading-worker.md) / [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

- Postgres ジョブキューから採点ジョブを取得（`SELECT FOR UPDATE SKIP LOCKED`、[ADR 0004](../../../docs/adr/0004-postgres-as-job-queue.md)）
- Docker SDK で使い捨てサンドボックスを起動・採点（[ADR 0009](../../../docs/adr/0009-disposable-sandbox-container.md)）
- LLM-as-a-Judge（品質評価、[ADR 0008](../../../docs/adr/0008-custom-llm-judge.md)）
- W3C Trace Context でジョブペイロード経由のトレース連携（[ADR 0010](../../../docs/adr/0010-w3c-trace-context-in-job-payload.md)）

## 既配置済み

- [`prompts/judge/`](./prompts/judge/) — LLM-as-a-Judge プロンプト（YAML、本 Worker 専属）

## 実装着手時に揃えるもの

- `go.mod` / `go.sum`（独立 Go module、[ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）
- `cmd/grading/main.go`（エントリポイント）
- `internal/`（DB アクセス / ジョブキュー / OTel / LLM クライアント / Docker SDK ラッパー）
- `internal/jobtypes/`（quicktype 生成物、`apps/api/job-schemas/` 由来（quicktype `--src-lang schema`）、gitignore、[ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- `.golangci.yml`（[ADR 0019](../../../docs/adr/0019-go-code-quality.md)）
- テスト：Go 標準 testing + testify（[ADR 0038](../../../docs/adr/0038-test-frameworks.md)）

## 起動

`mise run worker:grading:dev` 等は実装着手後に有効化される（タスク定義は [mise.toml](../../../mise.toml) に既記載）。
