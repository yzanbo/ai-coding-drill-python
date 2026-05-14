from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """全 SQLAlchemy モデルの共通親クラス。

    Alembic の autogenerate はこのクラスの `metadata` を参照するため、
    新規モデル追加時は `app.models.__init__` で必ず import すること。
    """
