"""Authentication hardening: password-change invalidation and sign-in throttling.

Revision ID: 0003_auth_hardening
Revises: 0002_sim_schema
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_auth_hardening"
down_revision = "0002_sim_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_login_attempts_key_attempted",
        "login_attempts",
        ["key_hash", "attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_key_attempted", table_name="login_attempts")
    op.drop_table("login_attempts")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_changed_at")
