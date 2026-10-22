"""Move simulation tables to their own schema and store explainable finding labels.

Two changes that belong together:

* PostgreSQL deployments can isolate ``sim_*`` tables in a dedicated schema
  (``SIH_SIMULATION_SCHEMA=sim``). The ``sim_results_rw`` role gets USAGE only on
  that schema; it cannot resolve operational table names at all.
* A persisted rule evaluation now carries the rule title, severity and regulatory
  reference so the review UI can explain a stored finding even after the catalogue
  has moved on. The rule version remains the authoritative link.

Revision ID: 0002_sim_schema
Revises: 075aed043fd2
Create Date: 2026-10-22
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0002_sim_schema"
down_revision = "075aed043fd2"
branch_labels = None
depends_on = None

SIM_TABLES = (
    "sim_input_snapshots",
    "sim_rule_results",
    "sim_metrics",
    "sim_runs",
)


def _schema() -> str | None:
    return os.environ.get("SIH_SIMULATION_SCHEMA") or None


def upgrade() -> None:
    schema = _schema()
    bind = op.get_bind()
    if schema and bind.dialect.name == "postgresql":
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        for table in SIM_TABLES:
            op.execute(f'ALTER TABLE public.{table} SET SCHEMA "{schema}"')

    with op.batch_alter_table("rule_evaluations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "unverified_inputs",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "title",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("''"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "severity",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'major'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "regulatory_reference",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("''"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("rule_evaluations", schema=None) as batch_op:
        batch_op.drop_column("regulatory_reference")
        batch_op.drop_column("severity")
        batch_op.drop_column("title")
        batch_op.drop_column("unverified_inputs")

    schema = _schema()
    bind = op.get_bind()
    if schema and bind.dialect.name == "postgresql":
        for table in SIM_TABLES:
            op.execute(f'ALTER TABLE "{schema}".{table} SET SCHEMA public')
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}"')
