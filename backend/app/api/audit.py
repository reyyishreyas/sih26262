from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import iso
from ..core.db import get_db
from ..core.pagination import PageParams, apply_page, pagination, set_total
from ..core.permissions import AUDIT_READ
from ..models import AuditEvent
from ..services.audit_service import verify_chain
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
    entity_ids = {application.id}
    from ..models import Document, Undertaking

    entity_ids |= set(
        db.scalars(
            select(Document.id).where(Document.application_id == application.id)
        ).all()
    )
    entity_ids |= set(
        db.scalars(
            select(Undertaking.id).where(Undertaking.application_id == application.id)
        ).all()
    )

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


@router.get("/audit/verify")
def verify(
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return verify_chain(db).as_dict()


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
