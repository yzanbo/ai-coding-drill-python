# auth_providers テーブル：ユーザー × 外部認証プロバイダの紐付け。
#   1 ユーザーが将来複数プロバイダ（GitHub / Google / Email-Password 等）で
#   紐づく構造を最初から確保する（ADR 0011：「実装は最小、拡張は容易に」）。
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.1 / §2.1
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図）

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthProvider(Base):
    """ユーザーと外部認証プロバイダの紐付け。

    ## カラム
    - provider    : "github" 等のプロバイダ識別子（複合主キーの片方）
    - provider_id : プロバイダ側のユーザー ID 文字列（GitHub なら id を str 化、
                    複合主キーのもう片方）
    - user_id     : 対応する users.id への外部キー。CASCADE 削除でユーザー削除時に
                    一緒に消える（ハードデリート方針、backend.md）
    - created_at  : 紐付けが作成された時刻（UTC）

    ## 設計メモ
    - 複合主キー (provider, provider_id) で「同じプロバイダの同一外部 ID = 同一ユーザー」を
      DB レベルで保証（authentication.md §1.1）
    - user_id に index を付けて「あるユーザーがどのプロバイダで紐づくか」の逆引きを高速化
    - updated_at は不要：プロバイダ ↔ ユーザーの紐付けは作成後に変更しない
      （変更したくなった = 別人なので新規 INSERT が筋）
    """

    __tablename__ = "auth_providers"

    provider: Mapped[str] = mapped_column(String, primary_key=True)
    provider_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
