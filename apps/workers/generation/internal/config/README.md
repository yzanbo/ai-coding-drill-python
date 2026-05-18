# internal/config

## とは何か

Worker プロセスが起動時に**環境変数を 1 回だけ読み込む**ための置き場。`caarlos0/env/v11` で `Config` 構造体に tag 経由でマッピングし、`config.Load()` が `*Config` を返す。

## なぜ専用 package を切るか

- 環境変数の一覧と既定値が **1 ファイルに集約**され、何が必須で何が任意か一目で分かる
- テストで「環境変数を上書き」ではなく「fake `*Config` を注入」できる（テストの並列実行で副作用が出ない）
- 業務 package が `os.Getenv` を直接読まなくて済む（読む層を 1 箇所に限定）

## 役割

- 環境変数のマッピング：`DATABASE_URL` / `WORKER_ID` / `WORKER_CONCURRENCY` / `SANDBOX_IMAGE` / `JOB_TIMEOUT_SECONDS` / `RECLAIM_AFTER_MINUTES` / `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` などを `Config` 構造体のフィールドにする
- 既定値の宣言：`envDefault:"..."` タグで設定。generation Worker では問題生成 1 件あたりの実行時間が長いため `JOB_TIMEOUT_SECONDS` は grading より大きい値を既定にする想定
- 必須項目のバリデーション：`env:"...,required"` で起動時に欠落を検出して fail-fast

## やってはいけないこと

- 業務 package（`internal/{job,sandbox,llm,judge,generation}`）が **`os.Getenv` を直接呼ぶ**：必ず `*Config` を引数で受け取る。テストできなくなる（[worker-layers.md §E §8](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- `internal/config/` 内で `internal/{db,llm,...}` を import：`config/` は Layer 0 の終端で、上位 package から参照されるだけ（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- 機密値を `envDefault` に書く：本番秘密は `.env`（gitignore）から読み込む。defaults は開発用の安全な値のみ

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 環境変数一覧：[.claude/rules/worker.md「環境変数」セクション](../../../../.claude/rules/worker.md)
