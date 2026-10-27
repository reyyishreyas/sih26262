from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.pagination import PageParams, apply_page, pagination, set_total
from ..core.permissions import AUDIT_READ
from ..models import AuditChainHead, AuditEvent
from ..services.audit_service import AuditService, verify_chain
from ..services.authorization_service import EffectiveAccess, require_application
from .deps import require

router = APIRouter(tags=["audit"])


@router.get("/applications/{application_id}/audit")
def case_timeline(
    application_id: str,
    response: Response,
    page: PageParams = Depends(pagination),
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    entity_ids = _case_entity_ids(db, application.id)

    events = db.scalars(
        apply_page(
            select(AuditEvent)
            .where(AuditEvent.entity_id.in_(entity_ids))
            .order_by(AuditEvent.seq),
            page,
        )
    ).all()
    total = int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id.in_(entity_ids))
        )
        or 0
    )
    set_total(response, total)
    return {
        "application_id": application.id,
        "note": (
            "Chronological audit timeline. This is not a historical state replay: "
            "reconstruction from snapshots is not implemented."
        ),
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "events": [_serialise(event) for event in events],
    }


@router.get("/applications/{application_id}/audit/export")
def export_case_audit(
    application_id: str,
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Download a case-scoped audit bundle after verifying the full chain."""
    application = require_application(db, access, application_id)
    verification = verify_chain(db)
    if not verification.ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "audit chain verification failed", **verification.as_dict()},
        )

    entity_ids = _case_entity_ids(db, application.id)
    event_count = int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_id.in_(entity_ids))
        )
        or 0
    )
    AuditService(db).append(
        action="audit.exported",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={"application_id": application.id, "event_count_before_export": event_count},
        request_id=current_request_id(),
    )
    db.commit()

    verification = verify_chain(db)
    if not verification.ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "audit chain verification failed", **verification.as_dict()},
        )
    entity_ids = _case_entity_ids(db, application.id)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id.in_(entity_ids))
        .order_by(AuditEvent.seq)
    ).all()
    head = db.get(AuditChainHead, 1)
    bundle = {
        "format": "sih26262.case-audit.v1",
        "application_id": application.id,
        "exported_at": get_clock().now().isoformat(),
        "scope": "events linked to this application and its tracked resources",
        "integrity": {
            "verified_before_export": True,
            "chain_verification": verification.as_dict(),
            "chain_head_seq": head.last_seq if head else 0,
            "chain_head_hash": head.last_hash if head else "0" * 64,
            "note": "The complete global chain was checked; this scoped export is not independently re-verifiable without other cases' events.",
        },
        "events": [_serialise(event) for event in events],
    }
    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="{application.id}-audit.json"'
        },
    )


@router.get("/audit/verify")
def verify(
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return verify_chain(db).as_dict()


@router.post("/audit/verify")
def record_verification(
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Record an explicit chain check without giving the GET read side effects."""
    observed = verify_chain(db)
    event = AuditService(db).append(
        action="audit.verification",
        entity_type="system",
        entity_id="audit_chain",
        outcome="accepted" if observed.ok else "rejected",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after=observed.as_dict(),
        request_id=current_request_id(),
    )
    db.commit()
    final = verify_chain(db)
    result = final.as_dict()
    result["verification_event_seq"] = event.seq
    return result


def _case_entity_ids(db: Session, application_id: str) -> set[str]:
    from ..models import Alert, Deficiency, Document, EvcVisit, Undertaking

    entity_ids = {application_id}
    for model in (Document, Deficiency, Undertaking, EvcVisit):
        entity_ids.update(
            db.scalars(
                select(model.id).where(model.application_id == application_id)
            ).all()
        )
    # Alert lifecycle events are recorded against the alert itself.
    entity_ids.update(
        db.scalars(select(Alert.id).where(Alert.entity_id.in_(entity_ids))).all()
    )
    return entity_ids


def _serialise(event: AuditEvent) -> dict:
    return {
        "seq": event.seq,
        "at": iso(event.at),
        "actor_id": event.actor_id,
        "actor_role": event.actor_role,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "outcome": event.outcome,
        "reason": event.reason,
        "before": event.before,
        "after": event.after,
        "request_id": event.request_id,
        "hash": event.hash,
        "prev_hash": event.prev_hash,
    }
