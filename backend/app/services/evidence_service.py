"""Builds the evidence snapshot that the rule engine reads.

The snapshot is deliberately boring: plain values, a verified map, and a source map.
No ORM objects cross into the rule engine or the rehearsal engine, so the same
evaluation can run against production or against a hypothetical in-memory scenario.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..models import Application, Document, ExtractedField, Institution, Undertaking
from .rule_engine import Snapshot


def _serialise(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def latest_document_fields(
    db: Session, application_id: str
) -> dict[str, dict[str, object]]:
    """doc_type -> {field: value} for the latest document of each type."""
    documents = db.scalars(
        select(Document)
        .where(Document.application_id == application_id)
        .order_by(Document.uploaded_at.asc())
    ).all()

    by_type: dict[str, Document] = {}
    for document in documents:
        if document.status == "rejected":
            continue
        by_type[document.doc_type] = document  # later upload wins

    result: dict[str, dict[str, object]] = {}
    for doc_type, document in by_type.items():
        fields = db.scalars(
            select(ExtractedField).where(
                ExtractedField.document_id == document.id,
                ExtractedField.document_version == document.version,
                ExtractedField.verification_status != "rejected",
            )
        ).all()
        entry: dict[str, object] = {
            "document_id": document.id,
            "version": document.version,
            "uploaded_at": _serialise(document.uploaded_at),
        }
        for field in fields:
            entry[field.field_name] = _serialise(field.value)
        result[doc_type] = entry
    return result


def build_snapshot(db: Session, application: Application) -> Snapshot:
    institution = db.get(Institution, application.institution_id)
    now = get_clock().now()
    state_since = application.current_state_since
    if state_since.tzinfo is None:
        state_since = state_since.replace(tzinfo=timezone.utc)
    days_in_state = max(0, (now - state_since).days)

    values: dict[str, object] = {
        "application": {
            "id": application.id,
            "category": application.category,
            "route_key": application.route_key,
            "cycle": application.cycle,
            "cycle_end": _serialise(application.cycle_end),
            "state": application.current_state,
            "days_in_state": days_in_state,
            "baseline_version": application.baseline_version,
        },
        "institution": {
            "id": institution.id if institution else None,
            "aicte_id": institution.aicte_id if institution else None,
            "name": institution.name if institution else None,
            "region_id": institution.region_id if institution else None,
        },
    }

    documents = latest_document_fields(db, application.id)
    if documents:
        values["documents"] = documents

    undertakings = db.scalars(
        select(Undertaking).where(Undertaking.application_id == application.id)
    ).all()
    if undertakings:
        values["undertakings"] = {
            item.obligation_key: {
                "id": item.id,
                "due_at": _serialise(item.due_at),
                "status": item.status,
                "title": item.title,
                "evidence_required": item.evidence_required,
            }
            for item in undertakings
        }

    verified: dict[str, bool] = {}
    sources: dict[str, str] = {}

    document_rows = db.scalars(
        select(Document)
        .where(Document.application_id == application.id)
        .order_by(Document.uploaded_at.asc())
    ).all()
    for document in document_rows:
        fields = db.scalars(
            select(ExtractedField).where(
                ExtractedField.document_id == document.id,
                ExtractedField.document_version == document.version,
            )
        ).all()
        for field in fields:
            path = f"documents.{document.doc_type}.{field.field_name}"
            verified[path] = field.verification_status == "verified"
            page = f"#page={field.source_page}" if field.source_page else ""
            sources[path] = f"document:{document.id}{page}"
        sources[f"documents.{document.doc_type}"] = f"document:{document.id}"

    for item in undertakings:
        path = f"undertakings.{item.obligation_key}.due_at"
        verified[path] = True
        sources[path] = f"undertaking:{item.id}"

    return Snapshot(values=values, verified=verified, sources=sources)
