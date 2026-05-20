# generation_requests テーブル：問題生成リクエストの受付台帳。
#   1 リクエスト = 1 行。Worker がジョブを処理する過程で status / produced_problem_id
#   を書き換える（pending → completed / failed）。
#   Backend は INSERT（POST /problems/generate）と SELECT（GET /problems/generate/:requestId）
#   を担当する。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図 + ハードデリート方針）

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenerationRequest(Base):
    """問題生成リクエストの受付台帳。

    ## カラム
    - id                  : UUID（gen_random_uuid()）。クライアントへ requestId として返す
    - user_id             : リクエスト発行ユーザー（CASCADE：ユーザー削除で履歴も消える）
    - category            : 要望カテゴリ（バリデーションは schemas/problems.py で Literal 縛り）
    - difficulty          : 要望難易度（同上）
    - status              : "pending" / "completed" / "failed"
                            （マシン的というよりユーザー視点の遷移なので status を採用、
                            data-model.md「状態カラム」と整合）
    - produced_problem_id : 完成時に問題テーブルへの FK を書く。Worker が SET ONLY
    - created_at          : 作成時刻
    - updated_at          : 最終更新時刻（status 遷移で書き換わる）

    ## 設計メモ
    - 本テーブルはハードデリート対象（TTL バッチで物理削除、data-model.md）
      → deleted_at は持たない
    - status を CHECK 制約で縛ると将来の状態追加（rate_limited 等）で書き換えコストが
      高くなるため、CHECK を張らず Pydantic 側で Literal で縛る方針
    - インデックス：(user_id, created_at DESC) で「自分の最近のリクエスト一覧」を効率化
    """

    __tablename__ = "generation_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )
    produced_problem_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
    )
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

    # 自分の最近のリクエストを並べる用。
    # `created_at DESC` は SQLAlchemy 側で desc() 指定すると Alembic 出力に乗らないため、
    # 通常 index で済ませる（プランナが順序を吸収する）。
    __table_args__ = (
        Index("ix_generation_requests_user_id_created_at", "user_id", "created_at"),
    )
