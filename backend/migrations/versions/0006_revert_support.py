"""Undo support: mark a workflow transition as reverted.

Revision ID: 0006_revert_support
Revises: 0005_alert_lifecycle
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_revert_support"
down_revision = "0005_alert_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_transitions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reverted_by", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_workflow_transitions_reverted_by", "users", ["reverted_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_transitions", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_workflow_transitions_reverted_by", type_="foreignkey"
        )
        batch_op.drop_column("reverted_by")
        batch_op.drop_column("reverted_at")
