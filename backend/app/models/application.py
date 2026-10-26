"""Institutions, applications, documents and extracted evidence."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
    documents: Mapped[list[Document]] = relationship(back_populates="application")
    items: Mapped[list[ApplicationItem]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationItem(Base):
    """One Table 2.3 category on a (possibly combined) application.

    PRD routing rule 2 / FR-08: a combined application runs the union of its
    categories' stages and records its outcome **per category**, so a
    conversion that clears and a merger that does not are not flattened into
    one verdict. A plain single-category case carries exactly one item.
    """

    __tablename__ = "application_items"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "category_id", name="uq_application_item_category"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    # Table 2.3 category id (t23-01 … t23-21); route is copied from the
    # category's pattern so a case history survives later table edits.
    category_id: Mapped[str] = mapped_column(String(16))
    route: Mapped[str] = mapped_column(String(32))
    # Per-category outcome (FR-08); None until that category is decided.
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="items")


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
    # Why this version exists. A replacement records what was corrected, so the
    # version history explains itself without opening the audit timeline.
    # Null on uploads where nobody recorded a reason (the field is optional).
    upload_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    application: Mapped[Application | None] = relationship(back_populates="documents")
    fields: Mapped[list[ExtractedField]] = relationship(
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


class EvcVisit(Base):
    """One scheduled Expert Visit Committee visit for a case.

    A case may be rescheduled any number of times; only the latest visit in
    `scheduled` status is the live appointment. Completion is recorded here when
    the `complete_evc` workflow transition is accepted, so the queue report and
    the timeline always agree with the workflow state.
    """

    __tablename__ = "evc_visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    committee_id: Mapped[str | None] = mapped_column(
        ForeignKey("committees.id"), nullable=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date)
    venue: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(24), default="scheduled", index=True)
    notes: Mapped[str] = mapped_column(String(1024), default="")
    scheduled_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Deficiency(Base):
    """A structured deficiency item recorded against an application or specific evidence.

    Status lifecycle:
    - 'draft': officer is noting the issue during scrutiny before returning
    - 'open': finalized and issued to institution upon return_for_clarification
    - 'addressed': institution has uploaded a corrective document version
    - 'closed': officer has re-verified and accepted the resolution
    """

    __tablename__ = "deficiencies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    extracted_field_id: Mapped[str | None] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64), default="document_deficiency")
    rule_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_value: Mapped[object] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    corrective_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )

    application: Mapped[Application] = relationship()
    document: Mapped[Document | None] = relationship(foreign_keys=[document_id])
    extracted_field: Mapped[ExtractedField | None] = relationship()
    corrective_document: Mapped[Document | None] = relationship(foreign_keys=[corrective_document_id])


class ReadinessFlag(Base):
    """An officer's clear/hold decision on one FR-03 blocked-application flag.

    Rows exist only once an officer has acted (PRD §7: "Regional officer
    clears flags ... official clears/holds each flag"). The five FR-03 rules
    themselves are configuration (`rules/readiness_policy.json`) and are
    evaluated on read — the advisory evaluation is deliberately never stored,
    so a rule edit cannot leave stale verdicts behind (same principle as the
    deadline clocks: nothing stores a computed verdict).

    One row per application + rule; re-deciding updates it and the audit
    timeline keeps both decisions. This table gates nothing: no workflow
    transition reads it (DEC-0003, PRD §0).
    """

    __tablename__ = "readiness_flags"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "flag_id", name="uq_readiness_flag_rule"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    # The config rule id (bf-01 … bf-05) from readiness_policy.json.
    flag_id: Mapped[str] = mapped_column(String(64))
    # "cleared" | "held" — the PRD §7 vocabulary; validated against the
    # config `decisions` list by a test, and by the request schema at the edge.
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Latest decision time; a re-decision moves it (history lives in audit).
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship()

