"""Structured reason code on transitions (FR-28).

Phase 3.2 adds ``WorkflowTransition.reason_code``: returns and reverts
carry a code from the placeholder vocabulary in ``rules/reason_codes.json``
alongside the free text, so the §11 metric "rejections and returns by
reason code" is computed from structured data (see IMPL-0022). Nullable:
actions other than return/revert carry no code.

Revision ID: 0012_workflow_reason_code
Revises: 0011_stage_instances
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_workflow_reason_code"
down_revision = "0011_stage_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_transitions",
        sa.Column("reason_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_transitions", "reason_code")
