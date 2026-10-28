from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.permissions import (
    CASE_TRANSITION,
    DOCUMENT_VERIFY,
    UNDERTAKING_READ,
    UNDERTAKING_SUBMIT,
)
from ..models import Document, Undertaking
from ..schemas.api import UndertakingSubmitRequest
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
)
from .deps import require

router = APIRouter(prefix="/applications/{application_id}/undertakings", tags=["undertakings"])


class UndertakingCreateRequest(BaseModel):
    """An officer imposes a follow-up condition on the college."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=255)
    condition_text: str = ""
    evidence_required: str = ""
    due_at: date | None = None
    obligation_key: str = ""
    source_received_on: date | None = None
    source_document_id: str | None = None


class UndertakingWaiveRequest(BaseModel):
    """An officer lets a condition go, with the reason recorded."""

    model_config = ConfigDict(extra="forbid")

    reason: str = ""


def _serialise(item: Undertaking) -> dict:
    return {
        "id": item.id,
        "obligation_key": item.obligation_key,
        "title": item.title,
        "condition_text": item.condition_text,
        "evidence_required": item.evidence_required,
        "due_at": iso(item.due_at),
        "status": item.status,
        "submitted_at": iso(item.submitted_at),
        "verified_at": iso(item.verified_at),
        "reminder_policy": item.reminder_policy,
        "source_received_on": (
            item.source_received_on.isoformat() if item.source_received_on else None
        ),
        "source_document_id": item.source_document_id,
        "evidence_document_ids": item.evidence_document_ids or [],
    }


@router.get("")
def list_undertakings(
    application_id: str,
    access: EffectiveAccess = Depends(require(UNDERTAKING_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    require_application(db, access, application_id)
    rows = db.scalars(
        select(Undertaking)
        .where(Undertaking.application_id == application_id)
        .order_by(Undertaking.due_at)
    ).all()
    return [_serialise(item) for item in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_undertaking(
    application_id: str,
    payload: UndertakingCreateRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """An officer records a condition the college must keep (an undertaking).

    The condition is live the moment it is created: it appears on the college's
    case, reminders are generated before the due date, and an approval is
    blocked while one is overdue.
    """
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)

    obligation_key = payload.obligation_key.strip() or _key_from_title(payload.title)
    existing = db.scalars(
        select(Undertaking).where(
            Undertaking.application_id == application.id,
            Undertaking.obligation_key == obligation_key,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"this case already has a condition with the key {obligation_key!r}",
        )

    if obligation_key == "security_deposit_proof":
        if payload.source_received_on is None or not payload.source_document_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "record the notice date and link the uploaded notice document",
            )
        if application.current_state != "approved":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "a Security Deposit notice can only be recorded for an approved case",
            )
        if payload.source_received_on > get_clock().now().date():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "the recorded notice date cannot be in the future",
            )
        source_document = db.get(Document, payload.source_document_id)
        if (
            source_document is None
            or source_document.application_id != application.id
            or source_document.status == "rejected"
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "the notice document must be an available document on this case",
            )
        from ..services import security_deposit

        try:
            item, _created = security_deposit.ensure_proof_undertaking(
                db,
                application,
                intimation_date=payload.source_received_on,
                intimation_document_id=source_document.id,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        item.condition_text = payload.condition_text.strip() or item.condition_text
        item.evidence_required = payload.evidence_required.strip() or item.evidence_required
        item.title = payload.title.strip() or item.title
    else:
        if payload.source_received_on is not None or payload.source_document_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "notice source fields are only valid for the Security Deposit obligation",
            )
        if payload.due_at is None or payload.due_at <= get_clock().now().date():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "the due date must be in the future when the condition is created",
            )
        item = Undertaking(
            application_id=application.id,
            obligation_key=obligation_key,
            title=payload.title.strip(),
            condition_text=payload.condition_text.strip(),
            evidence_required=payload.evidence_required.strip(),
            # Deadlines are end-of-day in the business timezone, like every other
            # deadline in the system (see deadline_service).
            due_at=datetime.combine(payload.due_at, time(23, 59, 59), tzinfo=UTC),
            status="pending",
            reminder_policy={"profile": "undertaking_default"},
        )
        db.add(item)
    # The id default runs at insert time; flush so the audit event can name
    # the row it is about.
    db.flush()
    application.baseline_version += 1
    AuditService(db).append(
        action="undertaking.created",
        entity_type="undertaking",
        entity_id=item.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=item.condition_text,
        after={
            "title": item.title,
            "obligation_key": item.obligation_key,
            "due_at": iso(item.due_at),
            "status": "pending",
            "application_id": application.id,
            "source_received_on": (
                item.source_received_on.isoformat() if item.source_received_on else None
            ),
            "source_document_id": item.source_document_id,
            "placeholder": bool(item.reminder_policy.get("placeholder", False)),
            "advisory_only": bool(item.reminder_policy.get("advisory_only", True)),
        },
    )
    db.commit()
    return _serialise(item)


def _key_from_title(title: str) -> str:
    """A stable, readable key derived from the officer's own words."""
    import re

    key = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")
    return (key or "undertaking")[:64]


@router.post("/{undertaking_id}/waive")
def waive_undertaking(
    application_id: str,
    undertaking_id: str,
    payload: UndertakingWaiveRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """An officer releases the college from a condition, with a recorded reason.

    Only pending or submitted conditions can be waived, and the reason is
    mandatory: a dropped condition without a reason is not auditable.
    """
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)
    item = db.get(Undertaking, undertaking_id)
    if item is None or item.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "undertaking not found on this case")
    if item.status not in ("pending", "submitted"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"only a pending or submitted condition can be waived; this one is {item.status}",
        )
    if not payload.reason.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "waiving a condition requires a recorded reason",
        )

    before = {"status": item.status}
    item.status = "waived"
    application.baseline_version += 1
    AuditService(db).append(
        action="undertaking.waived",
        entity_type="undertaking",
        entity_id=item.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.reason.strip(),
        before=before,
        after={"status": "waived"},
    )
    db.commit()
    return _serialise(item)


@router.post("/{undertaking_id}/submit")
def submit_undertaking(
    application_id: str,
    undertaking_id: str,
    payload: UndertakingSubmitRequest,
    access: EffectiveAccess = Depends(require(UNDERTAKING_SUBMIT)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    item = db.get(Undertaking, undertaking_id)
    if item is None or item.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "undertaking not found on this case")
    if item.status not in ("pending", "submitted"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"undertaking is {item.status}")

    before = {"status": item.status}
    evidence_ids = sorted(set(payload.evidence_document_ids))
    if item.obligation_key == "security_deposit_proof" and not evidence_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "link the uploaded deposit proof and Affidavit 3 documents before submission",
        )
    if evidence_ids:
        linked_documents = db.scalars(
            select(Document).where(
                Document.application_id == application.id,
                Document.id.in_(evidence_ids),
                Document.status != "rejected",
            )
        ).all()
        if {document.id for document in linked_documents} != set(evidence_ids):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "evidence documents must be available on this case",
            )
    item.evidence_document_ids = evidence_ids
    item.status = "submitted"
    item.submitted_at = get_clock().now()
    application.baseline_version += 1
    AuditService(db).append(
        action="undertaking.submitted",
        entity_type="undertaking",
        entity_id=item.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.evidence_note,
        before=before,
        after={"status": "submitted", "evidence_document_ids": evidence_ids},
    )
    db.commit()
    return _serialise(item)


@router.post("/{undertaking_id}/verify")
def verify_undertaking(
    application_id: str,
    undertaking_id: str,
    access: EffectiveAccess = Depends(require(DOCUMENT_VERIFY)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    require_permission(access, DOCUMENT_VERIFY)
    item = db.get(Undertaking, undertaking_id)
    if item is None or item.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "undertaking not found on this case")
    if item.status != "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "only a submitted undertaking can be verified")

    before = {"status": item.status}
    item.status = "verified"
    item.verified_at = get_clock().now()
    item.verified_by = access.user_id
    application.baseline_version += 1
    AuditService(db).append(
        action="undertaking.verified",
        entity_type="undertaking",
        entity_id=item.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        before=before,
        after={"status": "verified"},
    )
    db.commit()
    return _serialise(item)
