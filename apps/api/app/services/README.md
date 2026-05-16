# services/

## services/ とは何か

1 機能の「**業務上やりたいこと**」を関数・クラスにまとめるフォルダ。
1 機能 1 ファイル（例：`problems.py` / `submissions.py`）。

services の関数は **「実務担当」** に近い役割で、ここに書くのは：

- DB クエリの組み立てと実行（[models/](../models/) を使う）
- 計算・分岐・バリデーション（HTTP 文脈に依らないもの）
- 認可チェック（「自分のリソースか？」）
- 別の service を組み合わせた処理
- 結果を [schemas/](../schemas/) の形に詰め替えて返す

HTTP リクエスト本体（`Request` / `Response` オブジェクト）には触らない。それは [routers/](../routers/) の仕事。
ログイン中ユーザーは引数で受け取る（自分で `Cookie` を見ない）。

## 役目

- [routers/](../routers/) から呼ばれて、DB へのクエリ（[models/](../models/) を使う）や計算・分岐を行う
- 返す値は [schemas/](../schemas/) の形に詰め替えてから routers に返す
- 「自分のリソースか」のチェックなど、認可ルールもここで書く

DB の取り出し方や規約は [.claude/rules/backend.md](../../../../.claude/rules/backend.md) の Service セクション。
