# models/

## models/ とは何か

DB テーブルの「**形**」を **SQLAlchemy クラス**として書くフォルダ。
1 テーブル 1 ファイル。

SQLAlchemy は「Python のクラス定義 ↔ Postgres のテーブル」を相互変換してくれる ORM。
ここに置いたクラスは：

- DB のカラム・型・制約・デフォルト値・関連（外部キー）を Python の `Mapped[T]` で書く設計図
- Alembic がこのクラスを見て **マイグレーション SQL を自動生成**する元データ
- services が DB レコードを Python オブジェクトとして扱うための型

> JSON の形（API の入出力）とは別物。それは [schemas/](../schemas/) に書く。
> 「DB テーブルの形」と「JSON の形」を分けることで、内部実装と外部公開を独立に変えられる。

## 役目

- テーブルのカラム・型・制約・関連を Python のクラスで表す
- ここを直に使うのは [services/](../services/) と Alembic マイグレーション
- JSON の形（API の入出力）は別物。それは [schemas/](../schemas/) に書く

書き方の規約は [.claude/rules/alembic-sqlalchemy.md](../../../../.claude/rules/alembic-sqlalchemy.md)。
