"""Deficiency records and expert-visit bookings: the tables the models already declared.

Two feature commits added ``deficiencies`` and ``evc_visits`` to the ORM
(``889c026``, ``4fd3c4d``) without a migration, so ``alembic check`` failed and
a Compose deployment — which builds its schema from ``alembic upgrade head``
only — came up without the tables the deficiency loop and the EVC queue read
and write. Found while running the mandatory ``alembic check`` for H.4
(BUG-0006). Created here, exactly as the models declare them.

Revision ID: 0008_deficiencies_and_evc_visits
Revises: 0007_document_upload_reason
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_deficiencies_and_evc_visits"
down_revision = "0007_document_upload_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evc_visits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("committee_id", sa.String(length=36), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.String(length=1024), nullable=False),
        sa.Column("scheduled_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["committee_id"], ["committees.id"]),
        sa.ForeignKeyConstraint(["scheduled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evc_visits_application_id", "evc_visits", ["application_id"], unique=False
    )
    op.create_index("ix_evc_visits_status", "evc_visits", ["status"], unique=False)

    op.create_table(
        "deficiencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("extracted_field_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("extracted_value", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("corrective_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("corrective_document_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["corrective_document_id"], ["documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["extracted_field_id"], ["extracted_fields.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deficiencies_application_id", "deficiencies", ["application_id"], unique=False
    )
    op.create_index(
        "ix_deficiencies_document_id", "deficiencies", ["document_id"], unique=False
    )
    op.create_index(
        "ix_deficiencies_extracted_field_id",
        "deficiencies",
        ["extracted_field_id"],
        unique=False,
    )
    op.create_index("ix_deficiencies_status", "deficiencies", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_deficiencies_status", table_name="deficiencies")
    op.drop_index(
        "ix_deficiencies_extracted_field_id", table_name="deficiencies"
    )
    op.drop_index("ix_deficiencies_document_id", table_name="deficiencies")
    op.drop_index("ix_deficiencies_application_id", table_name="deficiencies")
    op.drop_table("deficiencies")
    op.drop_index("ix_evc_visits_status", table_name="evc_visits")
    op.drop_index("ix_evc_visits_application_id", table_name="evc_visits")
    op.drop_table("evc_visits")
