"""set string length constraints on users and auth_providers

Revision ID: 0bf1836cc8cf
Revises: 3b77dece861e
Create Date: 2026-05-18 01:26:07.557976

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0bf1836cc8cf"
down_revision: str | Sequence[str] | None = "3b77dece861e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Alembic の autogenerate は VARCHAR の長さ変更（無制限 → VARCHAR(N)）を
    検知しないため、ALTER COLUMN ... TYPE VARCHAR(N) を手書きする。
    Postgres は既存値が新長さに収まれば即時変更可能。
    """
    op.alter_column(
        "users",
        "email",
        type_=sa.String(length=320),
        existing_type=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "display_name",
        type_=sa.String(length=255),
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.alter_column(
        "auth_providers",
        "provider",
        type_=sa.String(length=32),
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.alter_column(
        "auth_providers",
        "provider_id",
        type_=sa.String(length=255),
        existing_type=sa.String(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "auth_providers",
        "provider_id",
        type_=sa.String(),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "auth_providers",
        "provider",
        type_=sa.String(),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "display_name",
        type_=sa.String(),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "email",
        type_=sa.String(),
        existing_type=sa.String(length=320),
        existing_nullable=True,
    )
