"""Store online/physical mode for newly scheduled EVC visits.

Revision ID: 0018_evc_visit_mode
Revises: 0017_external_call_logs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_evc_visit_mode"
down_revision = "0017_external_call_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evc_visits", sa.Column("visit_mode", sa.String(16), nullable=True))
    op.add_column("evc_visits", sa.Column("meeting_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("evc_visits", "meeting_url")
    op.drop_column("evc_visits", "visit_mode")
