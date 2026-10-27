"""Scrutiny results per checklist item and overall (Phase 4.3, FR-14).

Adds two tables that record the scrutiny officer's HUMAN judgement on a
case's Annexure-2 checklist (Phase 4.2 generates the list; this records the
verdict per item and overall, both with remarks). The result vocabulary
("nil_deficiency" / "deficiency") is PRD FR-14's own wording via the
aa_gate.scrutiny_results configuration. Recording a result never moves or
gates a case (DEC-0003) — the transition stays a separate audited action.
The overall result refuses a self-contradiction: "nil_deficiency" is not
accepted while any item result is "deficiency".

Revision ID: 0015_scrutiny_results
Revises: 0014_conflict_of_interest
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_scrutiny_results"
down_revision = "0014_conflict_of_interest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrutiny_item_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(length=36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_id", sa.String(length=16), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False),
        sa.Column(
            "recorded_by",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "application_id",
            "category_id",
            "item_id",
            name="uq_scrutiny_item_result_line",
        ),
    )
    op.create_index(
        "ix_scrutiny_item_results_application_id",
        "scrutiny_item_results",
        ["application_id"],
    )
    op.create_table(
        "scrutiny_overall_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(length=36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False),
        sa.Column(
            "recorded_by",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "application_id", name="uq_scrutiny_overall_result_case"
        ),
    )
    op.create_index(
        "ix_scrutiny_overall_results_application_id",
        "scrutiny_overall_results",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scrutiny_overall_results_application_id",
        table_name="scrutiny_overall_results",
    )
    op.drop_table("scrutiny_overall_results")
    op.drop_index(
        "ix_scrutiny_item_results_application_id",
        table_name="scrutiny_item_results",
    )
    op.drop_table("scrutiny_item_results")
