"""Simulation-only records. Written through SimResultsWriter, never through the
operational session.

In PostgreSQL deployments ``SIH_SIMULATION_SCHEMA=sim`` places every table in a
dedicated schema. The ``sim_results_rw`` role has USAGE only on that schema, so it
cannot resolve operational table names even if application code goes wrong. On
SQLite (development and tests) no schema is used and isolation is enforced by the
read-only baseline connection plus ``SimResultsWriter``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config import get_settings
from .base import Base, new_id, utcnow

SIM_SCHEMA = get_settings().simulation_schema or None
_TABLE_ARGS = {"schema": SIM_SCHEMA} if SIM_SCHEMA else {}
_RUN_FK = f"{SIM_SCHEMA}.sim_runs.id" if SIM_SCHEMA else "sim_runs.id"


class SimRun(Base):
    __tablename__ = "sim_runs"
    __table_args__ = _TABLE_ARGS

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    run_by: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    baseline_version: Mapped[int] = mapped_column(Integer, default=1)
    rule_set_version: Mapped[str] = mapped_column(String(64), default="")
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SimInputSnapshot(Base):
    __tablename__ = "sim_input_snapshots"
    __table_args__ = _TABLE_ARGS

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(_RUN_FK, ondelete="CASCADE"), index=True
    )
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)


class SimRuleResult(Base):
    __tablename__ = "sim_rule_results"
    __table_args__ = _TABLE_ARGS

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(_RUN_FK, ondelete="CASCADE"), index=True
    )
    rule_key: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[int] = mapped_column(Integer)
    before_outcome: Mapped[str] = mapped_column(String(24))
    after_outcome: Mapped[str] = mapped_column(String(24))
    before_explanation: Mapped[str] = mapped_column(String(1024), default="")
    after_explanation: Mapped[str] = mapped_column(String(1024), default="")
    change: Mapped[str] = mapped_column(String(24))  # resolved|remaining|new|regressed|unchanged
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)


class SimMetric(Base):
    __tablename__ = "sim_metrics"
    __table_args__ = _TABLE_ARGS

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(_RUN_FK, ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    formula_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
