# apps/workers/generation

問題生成（generation）Worker — 独立 Go module。Postgres ジョブキューから問題生成ジョブを取得し、LLM で TS の練習問題（題意 + テストコード + 模範解答）を生成し、模範解答を使い捨て Docker サンドボックスで実行検証して、judge LLM で品質を評価したうえで `problems` テーブルに INSERT する。

詳細な選定理由・配置決定は [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)（Worker グルーピング、両 Worker 並立）/ [worker.md](../../../docs/requirements/5-roadmap/r0-setup/worker.md)（環境構築）/ [worker-layers.md](../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)（ディレクトリ構成）を参照。

## ディレクトリ一覧

| パス | これは何か |
|---|---|
| [cmd/generation/](./cmd/generation/) | エントリポイント（`main.go`、internal を組み立てるだけ） |
| [internal/](./internal/) | 9 サブ package（Go の `internal/` 規約で外部 import 不可） |
| [internal/config/](./internal/config/) | 環境変数読み込み |
| [internal/observability/](./internal/observability/) | slog + OTel + (R4) Prometheus |
| [internal/db/](./internal/db/) | pgx pool + transaction helpers |
| [internal/job/](./internal/job/) | claim / listener / reclaim / complete |
| [internal/sandbox/](./internal/sandbox/) | Docker SDK ラッパ + 隔離設定（grading の image を共有起動、自前 Dockerfile なし） |
| [internal/llm/](./internal/llm/) | LLM プロバイダ抽象化（ADR 0007）。生成本体で直接呼ぶ + judge 経由でも使う |
| [internal/judge/](./internal/judge/) | LLM-as-a-Judge 整形 + パース（問題品質評価） |
| [internal/jobtypes/](./internal/jobtypes/) | quicktype 自動生成型（gitignore） |
| [internal/generation/](./internal/generation/) | **オーケストレーター**（問題生成フロー本体） |
| [prompts/generation/](./prompts/generation/) | 問題生成プロンプト YAML（ADR 0040） |

> サンドボックスイメージの Dockerfile は grading worker 側が所有（[apps/workers/grading/sandbox/Dockerfile](../grading/sandbox/Dockerfile)）。generation worker は同 image `ai-coding-drill-sandbox:latest` を Docker SDK で起動するだけで、自前の Dockerfile を持たない（[ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。

## package 間の呼び出しの向き

```text
                       [jobs テーブル]
                            │
                            ▼
                      ┌────────────────┐
                      │ cmd/generation │  main: 全 internal を組み立て
                      └─────┬──────────┘
                            │
                ┌───────────┴────────────┐
                ▼                        ▼
          ┌──────────────┐         ┌──────────────────┐
          │ internal     │         │ observability    │  起動時 1 回だけ初期化
          │ /generation  │         │ + config         │
          └──┬───────────┘         └──────────────────┘
             │ 生成フローのオーケストレーター
     ┌───────┼─────────┬────────────┬─────────┐
     ▼       ▼         ▼            ▼         ▼
 ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐  ┌────────┐
 │ job │ │ db  │ │judge│ │ sandbox │  │jobtypes│  生成物・終端
 └──┬──┘ └─────┘ └──┬──┘ └─────────┘  └────────┘
    │               │
    ▼               ▼
  ┌────┐          ┌─────┐
  │ db │          │ llm │   provider 抽象化
  └────┘          └─────┘
```

**読み方**：

- `cmd/generation` が起動 → `internal/generation` が `job.Claim` でジョブ取得 → `llm`（生成 LLM）で問題作成 → `sandbox`（模範解答実行で検証）→ `judge`（問題品質評価、別 provider 推奨）→ `problems` テーブルに INSERT
- `jobtypes/` は **生成物のため終端**（手書きしない、終端を壊さない）
- `observability/` + `config/` は起動時 1 回だけ初期化
- 矢印の向きは [.claude/rules/worker.md](../../../.claude/rules/worker.md) の import 方向表と一致
- grading worker と図の構造は同じ（orchestrator 名と内部のステップだけが違う）

## 問題生成 1 件のスパン構成（OpenTelemetry 計測）

```
[generate_problem_job]
  ├─ [job.claim]                ジョブ取得 SQL
  ├─ [generation.invoke]        生成 LLM 呼び出し（ADR 0040）
  ├─ [schema.validate]          JSON Schema → quicktype 生成 Go struct でバリデーション
  ├─ [sandbox.run]              模範解答を sandbox で実行して動作確認
  ├─ [judge.invoke]             別プロバイダ judge で問題品質を評価
  └─ [job.complete]             problems INSERT + state='done'
```

## やってはいけないこと

1. **`internal/llm/` → `internal/generation/` を import**（逆流、`§C`）
2. **`internal/judge/` → `internal/sandbox/` を import**（同 Layer 横断、orchestrator 経由にする）
3. **`internal/jobtypes/` を手書きで編集**（quicktype 再生成で消える、[ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
4. **`internal/` を別 Go module から import**（Go 規約違反 + grading worker から generation の `internal/` 不可）
5. **業務 package が `os.Getenv` を直接呼ぶ**（`internal/config/` に集約、main で DI）
6. **サンドボックスでホスト volume を生 mount**（tmpfs / read-only mount を使う、[ADR 0009](../../../docs/adr/0009-disposable-sandbox-container.md)）
7. **`SELECT ... FOR UPDATE` を `SKIP LOCKED` なしで書く**（[ADR 0004](../../../docs/adr/0004-postgres-as-job-queue.md)）
8. **LLM プロバイダを直接 import**（必ず `internal/llm.Provider` interface 経由、[ADR 0007](../../../docs/adr/0007-llm-provider-abstraction.md)）
9. **自前の `apps/workers/generation/sandbox/Dockerfile` を作る**（grading の image を共有起動、image 二重所有しない、[worker-layers.md §E §9](../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）

## 起動

```bash
mise run worker:generation:dev          # 開発時のローカル起動
mise run worker:generation:test         # go test ./...
mise run worker:generation:lint         # golangci-lint run
mise run worker:generation:audit        # govulncheck ./...
mise run worker:generation:deps-check   # go mod tidy -diff
mise run worker:generation:types-gen    # quicktype で jobtypes/ 生成（R0-11 で使用）
```

> `sandbox-build` タスクは grading worker のみ（generation は image を共有起動するため）：
> `mise run worker:grading:sandbox-build` で `ai-coding-drill-sandbox:latest` をビルド

## 関連

- 規約 SSoT（実装契約）：[.claude/rules/worker.md](../../../.claude/rules/worker.md)
- 構造 SSoT（手順 + 設計判断）：[worker-layers.md](../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)
- 機能要件：[problem-generation.md](../../../docs/requirements/4-features/problem-generation.md)
- 関連 ADR：[0016](../../../docs/adr/0016-go-for-grading-worker.md) / [0019](../../../docs/adr/0019-go-code-quality.md) / [0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) / [0009](../../../docs/adr/0009-disposable-sandbox-container.md) / [0007](../../../docs/adr/0007-llm-provider-abstraction.md) / [0008](../../../docs/adr/0008-custom-llm-judge.md) / [0004](../../../docs/adr/0004-postgres-as-job-queue.md) / [0010](../../../docs/adr/0010-w3c-trace-context-in-job-payload.md) / [0046](../../../docs/adr/0046-job-queue-delivery-guarantees.md)
