"""Record assigned EVC experts and institution visit confirmation.

Revision ID: 0019_evc_assignment_confirmation
Revises: 0018_evc_visit_mode
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_evc_assignment_confirmation"
down_revision = "0018_evc_visit_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("case_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("source_evc_visit_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_case_assignments_source_evc_visit_id",
            "evc_visits",
            ["source_evc_visit_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_case_assignments_source_evc_visit_id",
            ["source_evc_visit_id"],
        )
    with op.batch_alter_table("evc_visits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "confirmation_status",
                sa.String(length=16),
                server_default="pending",
                nullable=False,
            )
        )
        batch_op.alter_column("confirmation_status", server_default=None)
        batch_op.add_column(
            sa.Column("confirmed_by", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_evc_visits_confirmed_by_users",
            "users",
            ["confirmed_by"],
            ["id"],
        )
        batch_op.add_column(
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("evc_visits") as batch_op:
        batch_op.drop_column("confirmed_at")
        batch_op.drop_constraint("fk_evc_visits_confirmed_by_users", type_="foreignkey")
        batch_op.drop_column("confirmed_by")
        batch_op.drop_column("confirmation_status")
    with op.batch_alter_table("case_assignments") as batch_op:
        batch_op.drop_index("ix_case_assignments_source_evc_visit_id")
        batch_op.drop_constraint(
            "fk_case_assignments_source_evc_visit_id", type_="foreignkey"
        )
        batch_op.drop_column("source_evc_visit_id")
