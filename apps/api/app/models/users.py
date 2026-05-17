# users テーブル：認証済みユーザーの最小情報を保持する。
#   プロバイダ（GitHub 等）の生 ID はここに持たず、auth_providers 側で紐づける
#   （複数プロバイダ対応を構造的に確保、ADR 0011）。
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.1 / §2.1
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図）

import uuid
from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """認証済みユーザー。

    ## カラム
    - id           : UUID（DB 側で gen_random_uuid() 自動生成、Postgres 13+ コア関数）
    - email        : 表示用 / 将来の通知用。プロバイダ側で非公開設定のユーザーが
                     存在し得るため **UNIQUE を付けない / nullable**（authentication.md §1.1）
    - display_name : ヘッダー等で表示する名前。GitHub の name → login の順で
                     フォールバックして保存（authentication.md §2.1）
    - created_at   : 作成時刻（UTC、TIMESTAMP(timezone=True)）
    - updated_at   : 最終更新時刻。再ログイン時に display_name / email を
                     最新値で上書きする方針のため updated_at を持つ（authentication.md §2.1）
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # email: RFC 5321 で SMTP 経路の上限は 320 文字（local 64 + @ + domain 255）。
    #   それ以上は受信側で拒否されるので保存しても無駄になるため上限を 320 にする。
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # display_name: 表示用名前。極端に長い値（数 KB）を弾くために 255 で頭打ち。
    #   GitHub の name は 255 を超えないため実害なし。
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
