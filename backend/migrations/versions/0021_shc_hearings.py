"""Store SHC hearing schedules and recommendations.

Revision ID: 0021_shc_hearings
Revises: 0020_evc_reports_fraud_referrals
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_shc_hearings"
down_revision = "0020_evc_reports_fraud_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shc_hearings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("visit_mode", sa.String(length=16), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=False),
        sa.Column("meeting_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("scheduled_by", sa.String(length=36), nullable=False),
        sa.Column("compliance_record", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.String(length=36), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["evc_reports.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scheduled_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"]),
        sa.UniqueConstraint("report_id", name="uq_shc_hearing_report"),
    )
    op.create_index("ix_shc_hearings_report_id", "shc_hearings", ["report_id"])
    op.create_index("ix_shc_hearings_status", "shc_hearings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_shc_hearings_status", table_name="shc_hearings")
    op.drop_index("ix_shc_hearings_report_id", table_name="shc_hearings")
    op.drop_table("shc_hearings")
