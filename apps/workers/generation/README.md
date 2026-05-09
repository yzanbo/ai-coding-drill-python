# apps/workers/generation

Go 問題生成ワーカー。**コード実装着手前の skeleton（プロンプトのみ配置済み）**。

## 役割（[ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

- Postgres ジョブキューから問題生成ジョブを取得（`SELECT FOR UPDATE SKIP LOCKED`、[ADR 0004](../../../docs/adr/0004-postgres-as-job-queue.md)）
- LLM 呼び出しによる問題生成（[ADR 0007](../../../docs/adr/0007-llm-provider-abstraction.md)）
- 品質評価（多層防御、必要に応じて grading の判定パイプラインを呼び出し）

## 既配置済み

- [`prompts/generation/`](./prompts/generation/) — 問題生成プロンプト（YAML、本 Worker 専属）

## 実装着手時に揃えるもの

- `go.mod` / `go.sum`（独立 Go module、grading とは別、[ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）
- `cmd/generation/main.go`（エントリポイント）
- `internal/`（DB アクセス / ジョブキュー / OTel / LLM クライアント）
- `internal/jobtypes/`（quicktype 生成物、`apps/api/openapi.json` 由来、gitignore、[ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- `.golangci.yml`（[ADR 0019](../../../docs/adr/0019-go-code-quality.md)）
- テスト：Go 標準 testing + testify（[ADR 0038](../../../docs/adr/0038-test-frameworks.md)）

## 起動

`mise run generation-worker-dev` 等は実装着手後に有効化される（タスク定義は [mise.toml](../../../mise.toml) に既記載）。
