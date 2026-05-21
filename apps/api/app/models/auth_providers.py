# auth_providers テーブル：ユーザー × 外部認証プロバイダの紐付け。
#   1 ユーザーが将来複数プロバイダ（GitHub / Google / Email-Password 等）で
#   紐づく構造を最初から確保する（ADR 0011：「実装は最小、拡張は容易に」）。
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.1 / §2.1
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図）

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, text
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
    - UNIQUE (provider, user_id) で「1 user × 1 provider = 1 アカウント」を保証。
      同じユーザーが同じ provider で複数の外部アカウントを紐付けることを禁止する
      （個人 GitHub と会社 GitHub の併用などは要件外）
    - user_id に index を付けて「あるユーザーがどのプロバイダで紐づくか」の逆引きを高速化
      （UNIQUE (provider, user_id) があれば user_id 単独の検索もこの index で賄えるが、
      既存の user_id 単独 index を残しても害は無く、明示性のため両方残す）
    - updated_at は不要：プロバイダ ↔ ユーザーの紐付けは作成後に変更しない
      （変更したくなった = 別人なので新規 INSERT が筋）
    """

    __tablename__ = "auth_providers"

    # provider: "github" / "google" / "email" 等のプロバイダ識別子。
    #   現状は文字列だが、長さは安全側で 32 文字に頭打ち（実値は 10 文字以下）。
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    # provider_id: プロバイダ側のユーザー ID 文字列（GitHub なら数値 id を str 化）。
    #   どのプロバイダでも数値 / 短い文字列のため 255 文字あれば十分。
    provider_id: Mapped[str] = mapped_column(String(255), primary_key=True)
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

    # UNIQUE (provider, user_id): 1 user × 1 provider = 1 アカウントを DB で強制。
    #   同じユーザーが同じ provider で複数の外部アカウントを紐付けることを禁止する。
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "user_id",
            name="uq_auth_providers_provider_user_id",
        ),
    )
