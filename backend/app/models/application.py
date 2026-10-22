"""Institutions, applications, documents and extracted evidence."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, new_id, utcnow


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aicte_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(64))
    route_key: Mapped[str] = mapped_column(String(64))
    cycle: Mapped[str] = mapped_column(String(16))
    cycle_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_state: Mapped[str] = mapped_column(String(32), default="draft")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    assigned_officer_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Bumped on every evidence/state change. A rehearsal that captured an older
    # version is marked superseded rather than silently mixing snapshots.
    baseline_version: Mapped[int] = mapped_column(Integer, default=1)
    current_state_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    institution: Mapped[Institution] = relationship()
    documents: Mapped[list["Document"]] = relationship(back_populates="application")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_ref: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    application: Mapped[Application | None] = relationship(back_populates="documents")
    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ExtractedField(Base):
    """One field, tied to a document version, page and extraction method.

    Nothing in this table is authoritative on its own: rules read the
    `verification_status` and degrade to NEEDS_REVIEW when it is not verified.
    """

    __tablename__ = "extracted_fields"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "document_version", "field_name", name="uq_extracted_field"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version: Mapped[int] = mapped_column(Integer, default=1)
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[object] = mapped_column(JSON, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_span: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(64), default="mock_ocr")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    verified_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped[Document] = relationship(back_populates="fields")


class Committee(Base):
    __tablename__ = "committees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16), default="EVC")
    name: Mapped[str] = mapped_column(String(255))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
