# internal/jobtypes

## とは何か

`apps/api/app/schemas/` の Pydantic モデルから **自動生成された Go 構造体**を置く場所。Backend が enqueue する問題生成ジョブペイロードを Worker が**同じ型**で受け取れるようにするための置き場（[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）。

## なぜ自動生成するか

- Pydantic（Backend）と Go（Worker）で型を**2 回手書き**すると、片方を変えてもう片方を忘れたとき silently 通って事故になる
- Pydantic を SSoT に置き、JSON Schema を中継して quicktype で Go に展開すれば、Backend の `.py` を変えるだけで両側の型が一致する
- 「Job キュー境界」だけが対象（HTTP API 境界は OpenAPI → Hey API で TS に展開、別経路、[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

## 生成パイプライン

```
apps/api/app/schemas/jobs/<job_type>.py   (Pydantic、SSoT)
  ↓ mise run api:job-schemas-export
apps/api/job-schemas/<job_type>.json      (JSON Schema artifact)
  ↓ mise run worker:generation:types-gen
apps/workers/generation/internal/jobtypes/types.go   (Go struct、本ディレクトリ)
```

R0-7（型同期パイプライン基盤）+ R0-11（両 Worker 側合流）で完成。生成パイプラインは grading worker と同じスクリプトを再利用する。

## なぜ生成物を git に commit しないか

- 生成物は `.gitignore` で除外している（[本ディレクトリの .gitignore](./.gitignore)）
- CI で `mise run worker:generation:types-gen` を走らせて毎回再生成 → drift があれば CI 失敗で気づく
- 手で編集しても次の再生成で消える、レビューを通る前に既に古い、という事故を防ぐ
- 例外として本 README と `.gitignore` だけは commit してディレクトリ存在を残す

## やってはいけないこと

- **手書きで型を編集**：`mise run worker:generation:types-gen` で消える（[worker-layers.md §E §4](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- 拡張メソッドを直接ここに足す：再生成で消える。`internal/job/` や `internal/judge/` 側で「生成型を内包する struct」を作って拡張する
- 別 package（`internal/db/` 等）からの import 方向を双方向にする：`jobtypes/` は終端（Layer 0）として保つ（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 型同期方針：[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)
- R0-11 詳細：[worker-types-gen.md](../../../../docs/requirements/5-roadmap/r0-setup/worker-types-gen.md)
