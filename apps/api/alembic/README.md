# alembic/

## alembic/ とは何か

DB スキーマの **変更履歴（マイグレーション）** を 1 ファイル 1 変更で積み上げるフォルダ。

[models/](../app/models/) で SQLAlchemy クラスを編集しても、それだけでは Postgres 側のテーブルは変わらない。Alembic が「**前回からの差分**」を Python ファイルとして生成し、それを実行することで初めて DB が新しい形になる。

- **models/ が現在の設計図**（最新の理想形）
- **alembic/versions/ が変更履歴**（過去のすべての差分が時系列で積み重なる）

models/ を直したら必ず alembic/versions/ に新しい revision を 1 本足す、というのが基本サイクル。

## 中身

- `env.py`：Alembic と SQLAlchemy の `Base.metadata` を繋ぐ起動スクリプト。autogenerate がここを起点にモデルを読み取る
- `script.py.mako`：新しい revision を生成する時のテンプレート（`mise run api:db-revision` が読む）
- `versions/`：適用済み・未適用を問わず、すべての差分マイグレーション（`<rev>_<slug>.py`）が並ぶ場所。**適用済みファイルは編集・削除しない**

## 使い方

```bash
mise run api:db-revision -- "<変更内容の要約>"  # models/ の差分から雛形を自動生成
mise run api:db-migrate                          # 未適用 revision を順に流して DB を最新化
```

詳しい手順・autogenerate の限界・コンフリクト解消は [.claude/rules/alembic-sqlalchemy.md](../../../.claude/rules/alembic-sqlalchemy.md)、設計判断は [ADR 0037](../../../docs/adr/0037-sqlalchemy-alembic-for-database.md)。
