"""Link human workflow decisions to Speaking Order documents.

Revision ID: 0022_speaking_order_transition
Revises: 0021_shc_hearings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_speaking_order_transition"
down_revision = "0021_shc_hearings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_transitions") as batch:
        batch.add_column(
            sa.Column("speaking_order_document_id", sa.String(length=36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_workflow_transitions_speaking_order_document_id_documents",
            "documents",
            ["speaking_order_document_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_workflow_transitions_speaking_order_document_id",
            ["speaking_order_document_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_transitions") as batch:
        batch.drop_index("ix_workflow_transitions_speaking_order_document_id")
        batch.drop_constraint(
            "fk_workflow_transitions_speaking_order_document_id_documents",
            type_="foreignkey",
        )
        batch.drop_column("speaking_order_document_id")
