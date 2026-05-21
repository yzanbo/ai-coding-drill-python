"""add retry_of failure_reason completed_at to generation_requests

Revision ID: 54b902247e80
Revises: f032cf226a1f
Create Date: 2026-05-21 12:06:12.154852

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '54b902247e80'
down_revision: str | Sequence[str] | None = 'f032cf226a1f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    R1-7 問題生成履歴・状態管理機能のための拡張：
      - retry_of       : 再試行時に元 generation_request を指す自己参照 FK
      - failure_reason : Worker が failed 遷移時に書く失敗理由文字列
      - completed_at   : completed / failed / canceled 遷移時の確定時刻

    status enum に 'canceled' を追加するが、DB レベルでは CHECK 制約を
    張っていない設計（schemas の Pydantic Literal が SSoT）のため、
    本マイグレーションで DDL は不要。
    """
    op.add_column(
        'generation_requests',
        sa.Column('retry_of', sa.UUID(), nullable=True),
    )
    op.add_column(
        'generation_requests',
        sa.Column('failure_reason', sa.Text(), nullable=True),
    )
    op.add_column(
        'generation_requests',
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    # 既存の終了済み行を backfill。
    #   completed_at は今回新設したカラムなので、本マイグレーション前に
    #   completed / failed に到達済みの行は NULL のまま残る。
    #   履歴画面の所要時間表示が「completed_at が無い行 = 進行中」とみなして
    #   現在時刻との差分を出してしまうため、updated_at（最終遷移時刻）を入れて
    #   表示が壊れないようにする。canceled は今回新設した状態なので既存行に存在しない。
    op.execute(
        "UPDATE generation_requests "
        "SET completed_at = updated_at "
        "WHERE status IN ('completed', 'failed') AND completed_at IS NULL"
    )
    # 自己参照 FK。ON DELETE SET NULL で「親が物理削除されても子は残す」設計
    # （履歴のトレーサビリティを優先し、不完全な行は UI 側で「元行不明」表示）。
    op.create_foreign_key(
        'fk_generation_requests_retry_of',
        source_table='generation_requests',
        referent_table='generation_requests',
        local_cols=['retry_of'],
        remote_cols=['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_generation_requests_retry_of',
        'generation_requests',
        type_='foreignkey',
    )
    op.drop_column('generation_requests', 'completed_at')
    op.drop_column('generation_requests', 'failure_reason')
    op.drop_column('generation_requests', 'retry_of')
