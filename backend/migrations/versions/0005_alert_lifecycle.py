"""Alert lifecycle: acknowledge and close an alert with an audit trail.

Revision ID: 0005_alert_lifecycle
Revises: 0004_rule_immutability_trigger
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_alert_lifecycle"
down_revision = "0004_rule_immutability_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("acknowledged_by", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("closed_by", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("close_reason", sa.String(length=1024), nullable=False, server_default="")
        )
        batch_op.create_foreign_key(
            "fk_alerts_acknowledged_by", "users", ["acknowledged_by"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_alerts_closed_by", "users", ["closed_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_alerts_closed_by", type_="foreignkey")
        batch_op.drop_constraint("fk_alerts_acknowledged_by", type_="foreignkey")
        batch_op.drop_column("close_reason")
        batch_op.drop_column("closed_by")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("acknowledged_by")
        batch_op.drop_column("acknowledged_at")
