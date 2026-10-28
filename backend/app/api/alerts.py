from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.pagination import PageParams, pagination, set_total
from ..core.permissions import ADMIN_USERS, MONITORING_READ
from ..models import Alert, Document, Undertaking
from ..services import deadline_service, reconcile
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, scope_filter
from .deps import require

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    response: Response,
    page: PageParams = Depends(pagination),
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    from ..models import Application

    query = select(Application.id)
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    scoped_ids = set(db.scalars(query).all())

    # The scope filter needs related rows, so the window is applied after
    # filtering and the fetch is bounded above by a generous constant.
    rows = db.scalars(
        select(Alert).order_by(Alert.fired_at.desc()).limit(2000)
    ).all()
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
                "acknowledged_at": iso(alert.acknowledged_at),
                "acknowledged_by": alert.acknowledged_by,
                "closed_at": iso(alert.closed_at),
                "closed_by": alert.closed_by,
                "close_reason": alert.close_reason,
                "snoozed_until": iso(alert.snoozed_until),
                "snooze_reason": alert.snooze_reason,
                "snoozed_by": alert.snoozed_by,
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
    total = len(out)
    set_total(response, total)
    return {
        "delivery_channel": "in_app",
        "simulated": True,
        "note": "Notification delivery is a mock adapter; records are real, transport is not.",
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "alerts": out[page.offset : page.offset + page.limit],
    }


class AlertActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=1024)


class SnoozeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # PRD §11 line 293: "One snooze with a reason, no second." The reason is
    # mandatory (same idea as the close reason — an alert that disappears
    # silently is indistinguishable from one nobody looked at), and the caller
    # says how long to hold it, so the hold is explicit rather than a fixed
    # silent window the officer cannot see.
    reason: str = Field(default="", max_length=1024)
    # Snooze length in days; bounded so a caller cannot park a reminder for a
    # decade. The exact window is a policy choice (no PRD figure), so it is
    # capped here and the resulting `snoozed_until` is always returned.
    days: int = Field(default=1, ge=1, le=30)


def _load_scoped_alert(db: Session, access: EffectiveAccess, alert_id: str) -> Alert:
    """Fetch an alert only if its case sits inside the caller's scope."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")

    from ..models import Application

    query = select(Application.id)
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    scoped_ids = set(db.scalars(query).all())
    if _application_for(db, alert) not in scoped_ids:
        # Same answer as "no such alert": scope must not be observable.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    return alert


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(
    alert_id: str,
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """An officer has seen this reminder and owns it from here.

    Idempotent: acknowledging an already-acknowledged alert changes nothing and
    writes no second audit event.
    """
    alert = _load_scoped_alert(db, access, alert_id)
    if alert.acknowledged_at is not None:
        return _serialise_alert(alert)

    now = get_clock().now()
    before = {"status": alert.status}
    alert.acknowledged_at = now
    alert.acknowledged_by = access.user_id
    alert.status = "acknowledged"
    AuditService(db).append(
        action="alert.acknowledged",
        entity_type="alert",
        entity_id=alert.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        before=before,
        after={"status": alert.status, "alert_type": alert.alert_type},
    )
    db.commit()
    return _serialise_alert(alert)


@router.post("/alerts/{alert_id}/close")
def close_alert(
    alert_id: str,
    payload: AlertActionRequest,
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """The matter behind this reminder has been dealt with — say how.

    Closing always records a reason: an alert that disappears silently is
    indistinguishable from one nobody looked at.
    """
    alert = _load_scoped_alert(db, access, alert_id)
    if alert.status == "closed":
        return _serialise_alert(alert)
    if not payload.reason.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "say what you did about this alert before closing it",
        )

    now = get_clock().now()
    before = {"status": alert.status}
    alert.status = "closed"
    alert.closed_at = now
    alert.closed_by = access.user_id
    alert.close_reason = payload.reason.strip()
    if alert.acknowledged_at is None:
        alert.acknowledged_at = now
        alert.acknowledged_by = access.user_id
    AuditService(db).append(
        action="alert.closed",
        entity_type="alert",
        entity_id=alert.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=alert.close_reason,
        before=before,
        after={"status": "closed", "alert_type": alert.alert_type},
    )
    db.commit()
    return _serialise_alert(alert)


@router.post("/alerts/{alert_id}/snooze")
def snooze_alert(
    alert_id: str,
    payload: SnoozeRequest,
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Hold this reminder for a while — once, and say why.

    PRD §11 line 293: "One snooze with a reason, no second." An alert may be
    snoozed exactly once; a second snooze is refused rather than silently
    extending the hold. The reason is mandatory. While snoozed and unexpired
    the reminder is suppressed by `alert_service.deliver`, the same way an
    acknowledged or closed alert already is; once `snoozed_until` passes the
    alert is eligible to be delivered again (it was never closed).
    """
    alert = _load_scoped_alert(db, access, alert_id)
    if alert.snoozed_until is not None:
        # "no second" — the hold already happened. Answer with the current
        # state (idempotent read) rather than an error, so a retry is safe and
        # the caller can see when the existing hold expires.
        return _serialise_alert(alert)
    if not payload.reason.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "say why you are snoozing this alert before snoozing it",
        )

    now = get_clock().now()
    snoozed_until = now + timedelta(days=payload.days)
    # A snooze is a temporary hold, not a lifecycle terminal: the alert stays
    # "open" so it can be delivered again once the window passes. Only the
    # snoozed_* fields mark the hold, and `alert_service.deliver` suppresses
    # the reminder while `snoozed_until` is still in the future.
    before = {"status": alert.status, "snoozed_until": iso(alert.snoozed_until)}
    alert.snoozed_until = snoozed_until
    alert.snooze_reason = payload.reason.strip()
    alert.snoozed_by = access.user_id
    AuditService(db).append(
        action="alert.snoozed",
        entity_type="alert",
        entity_id=alert.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=alert.snooze_reason,
        before=before,
        after={
            "status": alert.status,
            "snoozed_until": iso(snoozed_until),
            "alert_type": alert.alert_type,
        },
    )
    db.commit()
    return _serialise_alert(alert)


def _serialise_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "status": alert.status,
        "acknowledged_at": iso(alert.acknowledged_at),
        "acknowledged_by": alert.acknowledged_by,
        "closed_at": iso(alert.closed_at),
        "closed_by": alert.closed_by,
        "close_reason": alert.close_reason,
        "snoozed_until": iso(alert.snoozed_until),
        "snooze_reason": alert.snooze_reason,
        "snoozed_by": alert.snoozed_by,
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
    if alert.entity_type == "evc_visit":
        from ..models import EvcVisit

        visit = db.get(EvcVisit, alert.entity_id)
        return visit.application_id if visit else None
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
        for threshold in deadline_service.eligible_thresholds(
            item.alert_type, item.due_at, now, db=db
        ):
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


@router.get("/internal/reconcile-clocks")
def reconcile_clocks(
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Recompute every clock-derived date and report any drift. Read-only.

    Proves the "nothing stores a due flag" invariant: after a demo-clock jump
    every deadline recomputes cleanly, so the report shows zero differences.
    Frozen alert due_dates are surfaced for transparency but never counted as
    a drift — they snapshot the cycle they fired in by design.
    """
    report = reconcile.reconcile(db)
    return report.as_dict()
