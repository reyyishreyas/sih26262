"""Human-reviewed Chapter II grant lists and publication records."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class GrantBatch(Base):
    __tablename__ = "grant_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cycle: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), default="consolidated", index=True)
    last_grant_date: Mapped[date] = mapped_column(Date)
    calendar_source: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    ratified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ratified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GrantEntry(Base):
    __tablename__ = "grant_entries"
    __table_args__ = (
        UniqueConstraint("batch_id", "application_id", name="uq_grant_batch_application"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("grant_batches.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), index=True
    )
    approved_intake: Mapped[list[dict]] = mapped_column(JSON)
    letter_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True
    )
