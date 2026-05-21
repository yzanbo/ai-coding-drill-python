"""add progress_step to generation_requests

Revision ID: 07cfdec5b271
Revises: 54b902247e80
Create Date: 2026-05-21 14:27:08.252304

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '07cfdec5b271'
down_revision: str | Sequence[str] | None = '54b902247e80'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    R1-7-2 ステップ進捗の可視化のための拡張：
      - progress_step : Worker が現在処理中のステップを書く文字列
        ("llm_generating" / "sandbox_verifying" / "judging" / "persisting")
        terminal 行（completed / failed / canceled）では NULL に倒される
        （Pydantic Literal が SSoT、DB CHECK 制約は無し）。

    status だけだと「pending の間に Worker が今どこにいるか」が分からなかったため、
    UI（生成ステータス画面 / 生成履歴画面）でステップインジケータを表示できるよう
    にする。Worker は各ステップ開始時にこの列を UPDATE する。
    """
    op.add_column(
        'generation_requests',
        sa.Column('progress_step', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generation_requests', 'progress_step')
