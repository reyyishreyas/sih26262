"""Combined applications: one row per Table 2.3 category, outcome per category.

PRD routing rule 2 / FR-08: a combined application runs the union of its
categories' stages and records its outcome per category, so this table
carries the categories of a case individually. A single-category case
carries exactly one row.

Revision ID: 0009_application_items
Revises: 0008_deficiencies_and_evc_visits
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_application_items"
down_revision = "0008_deficiencies_and_evc_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=16), nullable=False),
        sa.Column("route", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "category_id", name="uq_application_item_category"
        ),
    )
    op.create_index(
        "ix_application_items_application_id",
        "application_items",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_application_items_application_id", table_name="application_items")
    op.drop_table("application_items")
