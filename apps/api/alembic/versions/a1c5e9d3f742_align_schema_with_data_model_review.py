"""align schema with data-model review

Revision ID: a1c5e9d3f742
Revises: 307fd17405d6
Create Date: 2026-05-21 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c5e9d3f742"
down_revision: str | Sequence[str] | None = "307fd17405d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    docs/requirements/3-cross-cutting/01-data-model.md レビューで挙がった
    テーブル設計の改善 3 点を 1 マイグレーションにまとめて適用する。

    1. users.deleted_at を追加（ADR 0048 ソフトデリート方針との整合）。
       既存テーブル（problems / submissions）と同じパターン：
       - 型は TIMESTAMP(timezone=True)
       - nullable=True、NULL = 生きている / 非 NULL = 削除済
       - 既存行は全て NULL（生存扱い）になる
       退会時の deleted_at セット + PII（email / display_name）の NULL クリアは
       service 層側で実装する。

    2. submissions に部分インデックス
       ix_submissions_user_id_problem_id_created_at_active を追加。
       「ある問題に対する自分の直近解答」「弱点分析・問題別正答率の集計」
       で必要になるクエリパターン (user_id, problem_id) を高速化する。
       既存 ix_submissions_user_id_created_at_active（user_id 単独 + created_at DESC）
       は履歴一覧用としてそのまま残し、両 index を併存させる。

    3. auth_providers に UNIQUE (provider, user_id) を追加。
       「1 user × 1 provider = 1 アカウント」を DB で強制する
       （同じユーザーが同じ provider で複数の外部アカウントを紐付けることを禁止）。
    """
    # --- 1. users.deleted_at ---
    op.add_column(
        "users",
        sa.Column(
            "deleted_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # --- 2. submissions の (user_id, problem_id, created_at DESC) 部分 index ---
    op.create_index(
        "ix_submissions_user_id_problem_id_created_at_active",
        "submissions",
        ["user_id", "problem_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- 3. auth_providers の UNIQUE (provider, user_id) ---
    op.create_unique_constraint(
        "uq_auth_providers_provider_user_id",
        "auth_providers",
        ["provider", "user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_auth_providers_provider_user_id",
        "auth_providers",
        type_="unique",
    )
    op.drop_index(
        "ix_submissions_user_id_problem_id_created_at_active",
        table_name="submissions",
    )
    op.drop_column("users", "deleted_at")
