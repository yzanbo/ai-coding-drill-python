# internal/config

## とは何か

Worker プロセスが起動時に**環境変数 + `llm.yaml` を 1 回だけ読み込む**ための置き場。`caarlos0/env/v11` で環境変数を `Config` 構造体に tag マッピング、`gopkg.in/yaml.v3` で [`apps/workers/grading/llm.yaml`](../../llm.yaml) を読み込む。`config.Load()` が `*Config` を返す。

## なぜ専用 package を切るか

- 環境変数の一覧と既定値が **1 ファイルに集約**され、何が必須で何が任意か一目で分かる
- テストで「環境変数を上書き」ではなく「fake `*Config` を注入」できる（テストの並列実行で副作用が出ない）
- 業務 package が `os.Getenv` を直接読まなくて済む（読む層を 1 箇所に限定）

## 役割

- 環境変数のマッピング：`DATABASE_URL` / `WORKER_ID` / `WORKER_CONCURRENCY` / `SANDBOX_IMAGE` / `JOB_TIMEOUT_SECONDS` / `RECLAIM_AFTER_MINUTES` / `LLM_CONFIG_PATH` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` を `Config` 構造体のフィールドにする
- ローカル開発時は `apps/workers/grading/.env.example` をコピーして `apps/workers/grading/.env` を作り、機密値（API キー等）を埋める。`mise.toml` の `[env] _.file` 設定で `mise run worker:grading:*` 起動時に自動 load される
- LLM プロバイダ・モデル設定の読み込み：`LLM_CONFIG_PATH` (既定 `llm.yaml`) のファイルを yaml.Unmarshal で `Config.LLM` (`LLMProviders`) に詰める。`cmd/grading/main.go` でここから `llm.Config` に詰め直す（本 package は worker.md Layer 0 制約で `llm` を import しないため中立 struct で保持）
- 既定値の宣言：`envDefault:"..."` タグで設定（`grading` worker 既定 `JOB_TIMEOUT_SECONDS=5` など）
- 必須項目のバリデーション：`env:"...,notEmpty"` で起動時に空文字を検出して fail-fast（`required` だけだと空文字を通すため）

## やってはいけないこと

- 業務 package（`internal/{job,sandbox,llm,judge,grading}`）が **`os.Getenv` を直接呼ぶ**：必ず `*Config` を引数で受け取る。テストできなくなる（[worker-layers.md §E §8](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- `internal/config/` 内で `internal/{db,llm,...}` を import：`config/` は Layer 0 の終端で、上位 package から参照されるだけ（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- 機密値を `envDefault` に書く：本番秘密は `.env`（gitignore）から読み込む。defaults は開発用の安全な値のみ

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 環境変数一覧：[.claude/rules/worker.md「環境変数」セクション](../../../../.claude/rules/worker.md)
