"""Institution appeals and the SAC/Council record (APH 2024–27, Ch. II)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class Appeal(Base):
    __tablename__ = "appeals"
    __table_args__ = (UniqueConstraint("application_id", name="uq_appeal_application"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    decision_transition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_transitions.id", ondelete="RESTRICT"), unique=True
    )
    appellant_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    grounds: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    appeal_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="submitted", index=True)
    hearing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hearing_venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hearing_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    hearing_notice_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    sac_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    sac_recommendation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    council_outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    council_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    council_decision_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    council_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    council_actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppealEvidence(Base):
    __tablename__ = "appeal_evidence"
    __table_args__ = (
        UniqueConstraint("appeal_id", "document_id", name="uq_appeal_evidence_document"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )


class AppealRepresentative(Base):
    __tablename__ = "appeal_representatives"
    __table_args__ = (
        UniqueConstraint("appeal_id", "position", name="uq_appeal_representative_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    institutional_role: Mapped[str] = mapped_column(String(128))
    id_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), unique=True
    )
    authorization_attested: Mapped[bool] = mapped_column(Boolean, default=False)
