"""Enforce rule-version immutability in the database.

The ORM listener remains the first line of defence, but a direct SQL client could
bypass it. This revision installs the same invariant as a trigger on both
PostgreSQL and SQLite. An approved version may be retired, but its rule content,
metadata, or deletion is rejected.

Revision ID: 0004_rule_immutability_trigger
Revises: 0003_auth_hardening
Create Date: 2026-10-22
"""

from __future__ import annotations

from alembic import op

from app.core.db_guards import install_rule_version_guard

revision = "0004_rule_immutability_trigger"
down_revision = "0003_auth_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This historical revision predates regulatory_status; the next revision
    # replaces the trigger after adding that column.
    install_rule_version_guard(op.get_bind(), include_regulatory_status=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS rule_versions_immutable_update")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS rule_versions_immutable_delete")
    elif bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            "DROP TRIGGER IF EXISTS rule_versions_immutability ON rule_versions"
        )
        bind.exec_driver_sql(
            "DROP FUNCTION IF EXISTS enforce_rule_version_immutability()"
        )
