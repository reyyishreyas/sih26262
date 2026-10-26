"""Snooze-once-with-reason on alerts (Phase 3.7, PRD §11 line 293).

Adds the three columns that carry one snooze per alert: `snoozed_until` (the
instant the reminder may resume — non-NULL is the "already snoozed" signal, so
the one-snooze limit is enforced by the data, no extra flag), `snooze_reason`
(mandatory free text, same idea as the close reason) and `snoozed_by`. While
snoozed and unexpired the reminder is suppressed by `alert_service.deliver`,
the same way an acknowledged/closed alert already is (see IMPL-0028).

Revision ID: 0013_alert_snooze
Revises: 0012_workflow_reason_code
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_alert_snooze"
down_revision = "0012_workflow_reason_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "snooze_reason", sa.String(length=1024), server_default="", nullable=False
            )
        )
        batch_op.add_column(
            sa.Column("snoozed_by", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_alerts_snoozed_by", "users", ["snoozed_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_alerts_snoozed_by", type_="foreignkey")
        batch_op.drop_column("snoozed_by")
        batch_op.drop_column("snooze_reason")
        batch_op.drop_column("snoozed_until")
