# routers/

## routers/ とは何か

FastAPI には `APIRouter` という仕組みがあり、**URL ごとに「どの関数で受けるか」を宣言**できます。
`routers/` はその宣言を集めるフォルダです。1 機能 1 ファイル（例：`problems.py` / `submissions.py`）。

router の関数は **「受付係」** に近い役割で、ここに書くのは：

- URL とメソッド（GET / POST / PUT / DELETE）の対応付け
- 入力（パスパラメータ / クエリ / リクエストボディ）の型と検証ルール
- 返す JSON の形（`response_model`）の指定
- 認証や DB セッションの取り出しは [deps/](../deps/) に任せて、`Depends(...)` で受け取るだけ
- 業務処理本体は [services/](../services/) に丸投げ

## 役目

- URL とメソッドを受け取り、入力の形を確認して [services/](../services/) に処理を渡す
- 返す JSON の形は [schemas/](../schemas/) のクラスで指定する
- 業務ロジック（計算・分岐・DB クエリ）は書かない。書くのは services 側

詳しい規約は [.claude/rules/backend.md](../../../../.claude/rules/backend.md) の Router セクション。
