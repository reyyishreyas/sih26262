"""One-time application reopening requests (APH 2024–27, Ch. II §2.3.3e)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class ReopeningRequest(Base):
    __tablename__ = "reopening_requests"
    __table_args__ = (UniqueConstraint("application_id", name="uq_reopening_application"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    institution_actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    representation_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_notice_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    filing_window_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_evidence_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
    payment_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
