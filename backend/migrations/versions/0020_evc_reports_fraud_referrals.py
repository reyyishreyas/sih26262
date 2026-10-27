"""Persist EVC reports and non-penal fraud referrals.

Revision ID: 0020_evc_reports_fraud_referrals
Revises: 0019_evc_assignment_confirmation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_evc_reports_fraud_referrals"
down_revision = "0019_evc_assignment_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evc_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("visit_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("submitted_by", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("deficiency_present", sa.Boolean(), nullable=False),
        sa.Column("fraud_flag", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["visit_id"], ["evc_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.UniqueConstraint("visit_id", name="uq_evc_report_visit"),
    )
    op.create_index("ix_evc_reports_visit_id", "evc_reports", ["visit_id"])
    op.create_index("ix_evc_reports_document_id", "evc_reports", ["document_id"])

    op.create_table(
        "fraud_referrals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("referred_by", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["evc_reports.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_by"], ["users.id"]),
        sa.UniqueConstraint("report_id", name="uq_fraud_referral_report"),
    )
    op.create_index("ix_fraud_referrals_report_id", "fraud_referrals", ["report_id"])
    op.create_index("ix_fraud_referrals_application_id", "fraud_referrals", ["application_id"])
    op.create_index("ix_fraud_referrals_status", "fraud_referrals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_fraud_referrals_status", table_name="fraud_referrals")
    op.drop_index("ix_fraud_referrals_application_id", table_name="fraud_referrals")
    op.drop_index("ix_fraud_referrals_report_id", table_name="fraud_referrals")
    op.drop_table("fraud_referrals")
    op.drop_index("ix_evc_reports_document_id", table_name="evc_reports")
    op.drop_index("ix_evc_reports_visit_id", table_name="evc_reports")
    op.drop_table("evc_reports")
