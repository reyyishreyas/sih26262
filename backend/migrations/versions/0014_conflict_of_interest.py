"""Conflict-of-interest declarations for case assignment (Phase 4.1, FR-12).

Adds the `conflict_of_interest_declarations` table that records an officer's
declared conflict on one case (PRD Appendix E: declaration, type, timestamp,
reviewer, exclusion, reassignment). A declared, unresolved declaration HIDES
the case from the declarer and keeps them out of the workload pool; it never
gates, moves or rejects a case (DEC-0003). See IMPL-0031.

Revision ID: 0014_conflict_of_interest
Revises: 0013_alert_snooze
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_conflict_of_interest"
down_revision = "0013_alert_snooze"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conflict_of_interest_declarations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(length=36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "declarant_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("conflict_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "reviewer_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "application_id", "declarant_id", name="uq_coi_case_declarant"
        ),
    )
    op.create_index(
        "ix_conflict_of_interest_declarations_application_id",
        "conflict_of_interest_declarations",
        ["application_id"],
    )
    op.create_index(
        "ix_conflict_of_interest_declarations_declarant_id",
        "conflict_of_interest_declarations",
        ["declarant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conflict_of_interest_declarations_declarant_id",
        table_name="conflict_of_interest_declarations",
    )
    op.drop_index(
        "ix_conflict_of_interest_declarations_application_id",
        table_name="conflict_of_interest_declarations",
    )
    op.drop_table("conflict_of_interest_declarations")
