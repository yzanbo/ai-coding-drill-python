# cmd/grading

## とは何か

採点 Worker の**エントリポイント**。`go run ./cmd/grading` や `go install ./cmd/grading` で `grading` という名前のバイナリが作られる。中身は `main.go` 1 ファイルだけで、`internal/*` の package を組み立ててジョブループを起動するのが仕事。

## なぜ `cmd/grading/` という path か

- Go コミュニティの慣習で、エントリポイントは `cmd/<binary-name>/main.go` に置く
- バイナリ名 = `grading` にすることで、将来 `apps/workers/generation/cmd/generation/main.go` と対称になる（`cmd/worker/` という共通名にすると 2 module で同一バイナリ名となり判別不可）
- `docker ps` / `go install` の出力で grading / generation が一目で区別できる（[worker-layers.md §B](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）

## main.go の責務

- `signal.NotifyContext` で SIGINT / SIGTERM を受け取り、ctx で全 goroutine に伝える
- `internal/config/`：環境変数を読み込み `*Config` を取得
- `internal/observability/`：slog + OTel を 1 回だけ初期化、shutdown を defer 登録
- `internal/db/`：pgx pool を生成
- `internal/job/` / `internal/sandbox/` / `internal/llm/` / `internal/judge/`：依存を組み立て、`internal/grading/` の Deps 構造体に詰める
- `internal/grading.Run(ctx, deps, concurrency)`：goroutine pool でジョブループを起動
- `<-ctx.Done()` で受信後、in-flight ジョブの完了を待つ（グレースフルシャットダウン）

## やってはいけないこと

- main.go にビジネスロジック（採点フロー本体）を書く：それは `internal/grading/` の仕事（[internal/grading/README.md](../../internal/grading/README.md)）
- 環境変数を `os.Getenv` で直接読む：`internal/config/` の `Config.Load()` 経由に統一（[worker-layers.md §E §8](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- グローバル変数で依存を渡す：必ず引数（DI）で `internal/grading/` に渡す（テスト容易性のため）
- `panic` を recover せず外に出す：1 ジョブのパニックで Worker プロセス全体が落ちないよう、`internal/grading/` 内で `recover` する

## 起動コマンド

```bash
mise run worker:grading:dev          # 開発時のローカル起動
go run ./cmd/grading                 # mise を介さない直接起動（同等）
go build -o grading ./cmd/grading    # バイナリ化
```

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 配置論点：[worker-layers.md §B](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)（`cmd/<binary-name>/` の選択理由）
- 親 README：[apps/workers/grading/README.md](../../README.md)
