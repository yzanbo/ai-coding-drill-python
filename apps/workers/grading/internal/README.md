# internal/

## とは何か

Go の言語規約で「**外部 module から import 不可**」と定義されているディレクトリ。`apps/workers/grading/` の中だけから参照でき、リポジトリ外（または別の Go module）からは**ビルドエラー**になる。Worker の実装本体はここに置く。

## なぜ `internal/` を使うか

- 公開 API を持つつもりがないコードを `pkg/` 等に置くと「いずれ誰かが import する」誤解が生じる
- `internal/` ならコンパイラレベルで強制的に閉じた境界を作れる
- `apps/workers/generation/internal/` から `apps/workers/grading/internal/` も**禁止**（別 Go module、`internal/` 二重ガード）

## サブ package 一覧（9 個、両 Worker 共通）

| package | 役割 | Layer |
|---|---|---|
| [config/](./config/) | 環境変数の読み込み | 0（leaf） |
| [observability/](./observability/) | slog + OpenTelemetry + (R4) Prometheus | 0（leaf、context 経由で透過利用） |
| [db/](./db/) | pgx pool + transaction helpers | 0（infrastructure） |
| [job/](./job/) | claim / listener / reclaim / complete | 1（domain、`db` を使う） |
| [sandbox/](./sandbox/) | Docker SDK ラッパ + 隔離設定 | 0（infrastructure） |
| [llm/](./llm/) | LLM プロバイダ抽象化（ADR 0007） | 0（infrastructure） |
| [judge/](./judge/) | LLM-as-a-Judge 整形 + パース | 1（domain、`llm` を使う） |
| [jobtypes/](./jobtypes/) | quicktype 自動生成型（gitignore） | 0（生成物・終端） |
| [grading/](./grading/) | **オーケストレーター** | 2（domain、他を組み合わせる） |

> generation worker では 9 番目が `internal/generation/` になる。他 8 package は同じ。

## import 方向のおおまかなルール

- Layer 2（`grading/`）→ Layer 1（`job` / `judge`）→ Layer 0（`db` / `llm` / その他）
- 同 Layer 内の package を横に呼ばない（`judge → sandbox` 等は禁止、必ず orchestrator 経由）
- `observability` と `config` は main.go から組み立て + DI で配るので、業務 package は context / 引数経由で間接利用

詳細は [worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md) と [.claude/rules/worker.md](../../../../.claude/rules/worker.md) の「package 間の import 方向」を参照。

## 紛らわしい組

- `internal/db/` vs `internal/job/`：前者は pgx 接続管理、後者は queue 操作 SQL
- `internal/llm/` vs `internal/judge/`：前者は provider 抽象、後者は grading 専用の prompt 整形
- `internal/sandbox/` vs `apps/workers/grading/sandbox/`：前者は Go コード（Docker SDK ラッパ）、後者は Dockerfile（image 定義）

## やってはいけないこと

- `apps/workers/<worker>/internal/` を別 module から import：Go 規約違反、コンパイラが拒否
- 同 Layer 横断 import（`judge → sandbox` 等）：orchestrator（`<worker>/`）経由にする
- 業務 package が `internal/observability/` / `internal/config/` を直接 import：context / 引数経由で渡される logger / span / 設定値だけを使う

## 関連

- 構造の SSoT：[worker-layers.md §A](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)
- 実装契約：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
