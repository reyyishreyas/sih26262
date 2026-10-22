from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import iso
from ..core.config import get_settings
from ..core.db import get_db
from ..core.permissions import ADMIN_USERS, ALERT_DELIVER, MONITORING_READ
from ..models import Alert, Document, Undertaking
from ..services import deadline_service
from ..services.authorization_service import EffectiveAccess, scope_filter
from .deps import require

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    from ..models import Application

    query = select(Application.id)
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    scoped_ids = set(db.scalars(query).all())

    rows = db.scalars(select(Alert).order_by(Alert.fired_at.desc()).limit(500)).all()
    out = []
    for alert in rows:
        application_id = _application_for(db, alert)
        if application_id not in scoped_ids:
            continue
        out.append(
            {
                "id": alert.id,
                "entity_type": alert.entity_type,
                "entity_id": alert.entity_id,
                "application_id": application_id,
                "alert_type": alert.alert_type,
                "level": alert.level,
                "status": alert.status,
                "due_at": iso(alert.due_at),
                "fired_at": iso(alert.fired_at),
                "recipients": alert.recipients,
                "payload": alert.payload,
                "deliveries": [
                    {
                        "attempt": delivery.attempt,
                        "status": delivery.status,
                        "error": delivery.error,
                        "at": iso(delivery.attempted_at),
                        "provider_ref": delivery.provider_ref,
                    }
                    for delivery in alert.deliveries
                ],
            }
        )
    return {
        "delivery_channel": "in_app",
        "simulated": True,
        "note": "Notification delivery is a mock adapter; records are real, transport is not.",
        "alerts": out,
    }


def _application_for(db: Session, alert: Alert) -> str | None:
    if alert.entity_type == "application":
        return alert.entity_id
    if alert.entity_type == "undertaking":
        undertaking = db.get(Undertaking, alert.entity_id)
        return undertaking.application_id if undertaking else None
    if alert.entity_type == "document":
        document = db.get(Document, alert.entity_id)
        return document.application_id if document else None
    return None


@router.post("/internal/deadline-sweep")
def run_deadline_sweep(
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Manual trigger for the persistent worker's job. Idempotent by construction."""
    result = deadline_service.sweep(db)
    return result.as_dict() | {"clock": iso(deadline_service.get_clock().now())}


@router.get("/internal/deadline-preview")
def preview(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Which alerts *would* fire now. No writes, useful for boundary testing."""
    now = deadline_service.get_clock().now()
    items = deadline_service.collect_items(db, now)
    preview_rows = []
    for item in items:
        for threshold in deadline_service.eligible_thresholds(item.alert_type, item.due_at, now):
            preview_rows.append(
                {
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "alert_type": item.alert_type,
                    "level": threshold.level,
                    "severity": threshold.severity,
                    "due_at": item.due_at.isoformat(),
                }
            )
    return {"now": now.isoformat(), "items": len(items), "eligible_alerts": preview_rows}
