"""Derived PRD §7 stage rows per case (FR-09 auto-advance).

Phase 3.1 adds ``StageInstance`` to the ORM: one row per application +
config stage key, holding where already-authorised transitions left the
case. The stage list and its per-route state mapping live in
``rules/stage_graph.json`` and are derived on every accepted transition or
revert by ``services.stages.sync_stage_instances`` — the rows carry no
authority of their own and gate nothing (see the model docstring and
IMPL-0021).

Revision ID: 0011_stage_instances
Revises: 0010_readiness_flags
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_stage_instances"
down_revision = "0010_readiness_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("stage_key", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "stage_key", name="uq_stage_instance_stage"
        ),
    )
    op.create_index(
        "ix_stage_instances_application_id",
        "stage_instances",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_stage_instances_status",
        "stage_instances",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stage_instances_status", table_name="stage_instances")
    op.drop_index("ix_stage_instances_application_id", table_name="stage_instances")
    op.drop_table("stage_instances")
