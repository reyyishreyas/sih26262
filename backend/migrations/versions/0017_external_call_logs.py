"""Metadata-only external model call logs (Phase 5.9).

Revision ID: 0017_external_call_logs
Revises: 0016_finding_dispositions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_external_call_logs"
down_revision = "0016_finding_dispositions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_call_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(length=36),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pages", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_call_logs_application_id", "external_call_logs", ["application_id"])
    op.create_index("ix_external_call_logs_document_id", "external_call_logs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_external_call_logs_document_id", table_name="external_call_logs")
    op.drop_index("ix_external_call_logs_application_id", table_name="external_call_logs")
    op.drop_table("external_call_logs")
