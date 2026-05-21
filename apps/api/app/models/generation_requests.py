# generation_requests テーブル：問題生成リクエストの受付台帳。
#   1 リクエスト = 1 行。Worker がジョブを処理する過程で status / produced_problem_id
#   を書き換える（pending → completed / failed）。
#   Backend は INSERT（POST /api/problems/generate）と
#   SELECT（GET /api/problems/generate/:requestId）を担当する。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図 + ハードデリート方針）

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenerationRequest(Base):
    """問題生成リクエストの受付台帳。

    ## カラム
    - id                  : UUID（gen_random_uuid()）。クライアントへ requestId として返す
    - user_id             : リクエスト発行ユーザー。FK は ON DELETE CASCADE だが、
                            users は ADR 0048 のソフトデリート対象でアプリ経由の
                            物理 DELETE は通常起こらない。CASCADE は将来 GDPR 等で
                            users を物理削除する運用に切り替えた時に履歴も消える
                            保険として置いている
    - category            : 要望カテゴリ（バリデーションは schemas/problems.py で Literal 縛り）
    - difficulty          : 要望難易度（同上）
    - status              : "pending" / "completed" / "failed" / "canceled"
                            （マシン的というよりユーザー視点の遷移なので status を採用、
                            data-model.md「状態カラム」と整合）
    - produced_problem_id : 完成時に問題テーブルへの FK を書く。Worker が SET ONLY
    - retry_of            : 再試行時に元 generation_request を指す自己 FK（履歴上で
                            「N 回目の再試行」を辿れるようにする、SET NULL で循環時の安全側）
    - failure_reason      : 失敗時に Worker が書き込む短い文字列（ユーザーには丸めて
                            表示するが、運用ログ用に詳細種別を保持）
    - completed_at        : completed / failed / canceled 遷移時の確定時刻。所要時間
                            （completed_at - created_at）の計算用
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
    # retry_of: 再試行時に元 ID を指す自己参照 FK。ON DELETE SET NULL で
    #   親が物理削除された時も子を残す（履歴の不完全性は許容、UI 側で「元行不明」表示）。
    retry_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generation_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    # failure_reason: Worker が failed 遷移時に書く短い文字列（例: "judge_below_threshold"
    #   / "sandbox_failed" / "llm_invalid_output"）。ユーザー UI には丸めて表示する。
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # progress_step: Worker が pending 中の現在ステップを書く文字列。
    #   "llm_generating" / "sandbox_verifying" / "judging" / "persisting"
    #   の 4 値（schemas/me_generations.py の ProgressStep Literal が SSoT）。
    #   terminal 遷移時は NULL（status を見れば終了状態が分かるため）。
    progress_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    # completed_at: completed / failed / canceled 遷移時の確定時刻。
    #   履歴画面の「所要時間」表示と SLA 集計に使う。pending / running 中は NULL。
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
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
