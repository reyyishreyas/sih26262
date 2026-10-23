"""Undertakings, persisted rule evaluations, alerts and delivery attempts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, new_id, utcnow


class Undertaking(Base):
    __tablename__ = "undertakings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    obligation_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    condition_text: Mapped[str] = mapped_column(String(2048), default="")
    evidence_required: Mapped[str] = mapped_column(String(255), default="")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reminder_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuleEvaluation(Base):
    """Persisted operational assessment. One row per rule per evaluation run."""

    __tablename__ = "rule_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    rule_key: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[int] = mapped_column(Integer)
    batch_id: Mapped[str] = mapped_column(String(36), index=True, default=new_id)
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    explanation: Mapped[str] = mapped_column(String(1024), default="")
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    missing_inputs: Mapped[list] = mapped_column(JSON, default=list)
    unverified_inputs: Mapped[list] = mapped_column(JSON, default=list)
    # Denormalised labels so a stored finding is still explainable after the rule
    # catalogue changes. The version number remains the authoritative link.
    title: Mapped[str] = mapped_column(String(255), default="")
    severity: Mapped[str] = mapped_column(String(16), default="major")
    regulatory_reference: Mapped[str] = mapped_column(String(255), default="")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    application_baseline_version: Mapped[int] = mapped_column(Integer, default=1)
    context: Mapped[str] = mapped_column(String(32), default="operational")
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Alert(Base):
    """One logical alert. `dedupe_key` is what makes sweeps idempotent."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_alert_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(32))
    cycle_key: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="open")
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    # Lifecycle: an officer has seen it (acknowledged) and/or dealt with it
    # (closed, with a reason). The same transitions are also written to the
    # hash-chained audit log, so this is the fast-to-read copy, not the history.
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    close_reason: Mapped[str] = mapped_column(
        String(1024), default="", server_default=""
    )

    deliveries: Mapped[list[AlertDelivery]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("alert_id", "channel", "attempt", name="uq_alert_delivery"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="in_app")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    alert: Mapped[Alert] = relationship(back_populates="deliveries")
