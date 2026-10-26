"""Officer decisions on the FR-03 blocked-application flags.

Phase 2.3 adds ``ReadinessFlag`` to the ORM: one row per application +
config rule, holding only the officer's clear/hold decision. The five FR-03
rules themselves stay in ``rules/readiness_policy.json`` and are evaluated
on read, so nothing about a rule edit is ever persisted here (see the model
docstring and IMPL-0018).

Revision ID: 0010_readiness_flags
Revises: 0009_application_items
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_readiness_flags"
down_revision = "0009_application_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "readiness_flags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("flag_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "flag_id", name="uq_readiness_flag_rule"
        ),
    )
    op.create_index(
        "ix_readiness_flags_application_id",
        "readiness_flags",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_readiness_flags_application_id", table_name="readiness_flags")
    op.drop_table("readiness_flags")
