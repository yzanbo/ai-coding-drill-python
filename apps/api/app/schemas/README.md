# schemas/

## schemas/ とは何か

API が受け取る / 返す JSON の「**形**」を **Pydantic クラス**として書くフォルダ。

Pydantic は「Python のクラス定義 → JSON のスキーマ + 型検証コード」を自動で組み立ててくれるライブラリ。
ここに置いたクラスは：

- リクエストの JSON ボディを Python オブジェクトに変換する時の「型と検証ルール」
- レスポンスを返す時の「公開して良いフィールドの絞り込み」
- FastAPI が自動生成する OpenAPI スキーマの元データ
- ジョブキューに投げる JSON ペイロードの型

> このプロジェクトでは **schemas/ が型の正本（SSoT）** で、TypeScript（Frontend）/ Go（Worker）側の型もここから自動生成される（[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）。
> 「DB テーブルの形（[models/](../models/)）」とは別物。DB の中身と JSON の公開フィールドを独立に変えられる。

## 役目

- HTTP の入出力の形を 1 箇所に集める。ここが「形の正本」で、TS 側の型もここから自動生成される
- 1 機能 1 ファイル（例：`problems.py`）。同じ機能で `<Model>Create` / `<Model>Update` / `<Model>Response` / `<Model>Query` を並べる
- ジョブキューに渡す JSON の形もここに置く（`schemas/jobs/<job_type>.py`）

命名や使い方は [.claude/rules/backend.md](../../../../.claude/rules/backend.md) の Pydantic スキーマセクション。
