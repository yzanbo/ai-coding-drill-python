import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealthCheck(Base):
    """疎通確認用の最小テーブル（R0 段階の SQLAlchemy + Alembic 動作確認）。

    実機能テーブル追加後も残しておき、`POST /health` の往復で
    DB 接続が生きていることを確認する用途で使い続ける。
    """

    __tablename__ = "health_check"

    # __table_args__: テーブルの論理名 info["label"]（/dev/erd が表示）。
    __table_args__ = {"info": {"label": "ヘルスチェック"}}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        info={"label": "ID"},
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        info={"label": "作成日時"},
    )
