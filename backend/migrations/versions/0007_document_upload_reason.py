"""Document uploads record why this version exists.

Revision ID: 0007_document_upload_reason
Revises: 0006_revert_support
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_document_upload_reason"
down_revision = "0006_revert_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows were uploaded before the question was asked, and
    # a first upload without a reason is still a legitimate upload.
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("upload_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("upload_reason")
