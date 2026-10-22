from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.permissions import DOCUMENT_VERIFY, UNDERTAKING_READ, UNDERTAKING_SUBMIT
from ..models import Undertaking
from ..schemas.api import UndertakingSubmitRequest
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
)
from .deps import require

router = APIRouter(prefix="/applications/{application_id}/undertakings", tags=["undertakings"])


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
        after={"status": "submitted"},
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
