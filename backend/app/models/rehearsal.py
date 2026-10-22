"""Simulation-only records. Written through SimResultsWriter, never through the
operational session."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class SimRun(Base):
    __tablename__ = "sim_runs"

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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("sim_runs.id", ondelete="CASCADE"), index=True
    )
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)


class SimRuleResult(Base):
    __tablename__ = "sim_rule_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("sim_runs.id", ondelete="CASCADE"), index=True
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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("sim_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    formula_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
