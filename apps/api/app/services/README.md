# services/

## services/ とは何か

1 機能の「**業務上やりたいこと**」を関数・クラスにまとめるフォルダ。
1 機能 1 ファイル（例：`problems.py` / `submissions.py`）。

services の関数は **「実務担当」** に近い役割で、ここに書くのは：

- 計算・分岐・バリデーション（HTTP 文脈に依らないもの）
- 認可チェック（「自分のリソースか？」）
- 別の service を組み合わせた処理
- トランザクション境界（`async with session.begin():`）
- DB から取り出した結果（ORM オブジェクト）を [schemas/](../schemas/) の形に詰め替えて返す

ここに書かないもの：

- **SQLAlchemy クエリの実装** — [repositories/](../repositories/) に委譲する。Service は `self.repo = <Feature>Repository(session)` で Repository を保持し、Repository のメソッドを呼ぶ（→ [ADR 0044](../../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- HTTP リクエスト本体（`Request` / `Response` オブジェクト） — それは [routers/](../routers/) の仕事
- ログイン中ユーザーの取得（自分で `Cookie` を見ない） — routers の引数で受け取る

## 役目

- [routers/](../routers/) から呼ばれて、ビジネスロジック（計算・分岐・認可）を実行する
- DB アクセスは [repositories/](../repositories/) に委譲する。Service は Repository を保持して呼び出すだけ
- Repository から受け取った ORM オブジェクトを [schemas/](../schemas/) の形に詰め替えてから routers に返す

DB の取り出し方や規約は [.claude/rules/backend.md](../../../../.claude/rules/backend.md) の Service / Repository セクション。
