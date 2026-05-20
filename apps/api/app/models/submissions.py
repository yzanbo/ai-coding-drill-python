# submissions テーブル：ユーザーが送信した解答コードと、その採点結果の台帳。
#   1 解答送信 = 1 行。R1-4 では Backend が POST /api/submissions の INSERT を担当する。
#   採点ジョブの enqueue は R1-5（grading.md）が乗せる予定。本フェーズでは
#   submissions 行だけが先に積み上がり、status='pending' で止まる。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md（API SSoT、R1-5 で本格実装）
#   - docs/requirements/4-features/problem-display-and-answer.md（実行ボタン → 本テーブルへ）
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図 + ソフトデリート方針）

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Submission(Base):
    """解答送信 + 採点結果のレコード。

    ## カラム
    - id          : UUID（gen_random_uuid()）。クライアントへ submissionId として返す
    - user_id     : 送信ユーザー。ON DELETE CASCADE（users はソフトデリート運用だが
                    将来の物理削除に備えた保険）
    - problem_id  : 対象の問題。ON DELETE CASCADE（同上）
    - code        : ユーザーが提出した TS コード。長文許容のため上限なし
    - status      : "pending" / "graded" / "failed"（ユーザー視点の状態、data-model.md
                    の「状態カラム」方針）。本 PR で INSERT 直後は "pending" 固定、
                    "graded" / "failed" は R1-5 の Worker が遷移させる
    - result      : 採点結果 JSON。R1-5 で Worker が書き込む（本 PR では NULL のまま）
    - score       : 採点スコア（整数）。R1-5 で Worker が書き込む（本 PR では NULL）
    - created_at  : 作成時刻
    - graded_at   : 採点完了時刻。status='graded' / 'failed' の確定時に Worker が書く
                    （ADR 0048 の「updated_at は値が後から書き換わるテーブルにだけ付与」
                    に従い、本テーブルは graded_at で代替し updated_at を持たない）
    - deleted_at  : ソフトデリート印（ADR 0048）。NULL = 生きている / 非 NULL = 削除済。
                    クエリ側で WHERE deleted_at IS NULL を**明示的に**書く

    ## 設計メモ
    - R1-4 では本テーブルへの INSERT のみが行われる。job enqueue / 採点 / 結果書き込みは
      R1-5（grading.md）が乗せる
    - インデックス：自分の解答履歴一覧（GET /api/submissions、grading.md §API）と、
      自分の特定問題への直近送信参照を高速化するため、
      (user_id, created_at DESC) WHERE deleted_at IS NULL の部分インデックスを張る。
      R1-5 で結果取得時の (user_id, problem_id) 引きが増えたら追加で検討
    """

    __tablename__ = "submissions"

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
    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )
    # result / score: R1-5 で Worker が UPDATE する。本 PR では INSERT 時には None。
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    graded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # __table_args__: 自分の解答履歴一覧を新着順で引くための部分インデックス。
    #   ソフトデリート行は履歴一覧に出さないため、deleted_at IS NULL を WHERE に含める。
    __table_args__ = (
        Index(
            "ix_submissions_user_id_created_at_active",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
