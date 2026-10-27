"""Keep unverified regulation mappings advisory at runtime.

Revision ID: e3a8c2b1d740
Revises: d948f3303deb
Create Date: 2026-10-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.db_guards import install_rule_version_guard

revision = "e3a8c2b1d740"
down_revision = "d948f3303deb"
branch_labels = None
depends_on = None


def _drop_rule_version_triggers(bind) -> None:
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS rule_versions_immutable_update")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS rule_versions_immutable_delete")
    elif bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS rule_versions_immutability ON rule_versions")


def upgrade() -> None:
    op.add_column(
        "rule_versions",
        sa.Column(
            "regulatory_status",
            sa.String(length=24),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "rule_evaluations",
        sa.Column(
            "regulatory_status",
            sa.String(length=24),
            nullable=False,
            server_default="unverified",
        ),
    )
    bind = op.get_bind()
    _drop_rule_version_triggers(bind)
    install_rule_version_guard(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _drop_rule_version_triggers(bind)
    with op.batch_alter_table("rule_evaluations") as batch:
        batch.drop_column("regulatory_status")
    with op.batch_alter_table("rule_versions") as batch:
        batch.drop_column("regulatory_status")
    install_rule_version_guard(bind, include_regulatory_status=False)
