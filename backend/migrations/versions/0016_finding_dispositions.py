"""Persist officer dispositions for operational findings (FR-47).

Revision ID: 0016_finding_dispositions
Revises: 70f34e02fce5
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_finding_dispositions"
down_revision = "70f34e02fce5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finding_dispositions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "rule_evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("rule_evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_evaluation_id", name="uq_finding_disposition_evaluation"),
    )
    op.create_index(
        "ix_finding_dispositions_rule_evaluation_id",
        "finding_dispositions",
        ["rule_evaluation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_finding_dispositions_rule_evaluation_id", table_name="finding_dispositions")
    op.drop_table("finding_dispositions")
