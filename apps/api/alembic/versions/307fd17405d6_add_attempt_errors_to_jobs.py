"""add attempt_errors to jobs

Revision ID: 307fd17405d6
Revises: 07cfdec5b271
Create Date: 2026-05-21 14:50:22.655479

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '307fd17405d6'
down_revision: str | Sequence[str] | None = '07cfdec5b271'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    R1-7-3 max_attempts_exceeded の中身を試行単位で残すための拡張：
      - attempt_errors : Worker が MarkFailed / MarkDead のたびに 1 要素 append
        する JSONB array。各要素は
          {"attempt": int, "failureReason": str, "message": str, "failedAt": str}
        の形（schemas/me_generations.py AttemptError と 1:1）。

    NOT NULL DEFAULT '[]'::jsonb で既存行も空配列に揃える（API レスポンスで
    list[AttemptError] のフィールドが必ず存在する契約に揃える）。
    """
    op.add_column(
        'jobs',
        sa.Column(
            'attempt_errors',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'attempt_errors')
