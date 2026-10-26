"""Deadline discovery and the idempotent sweep.

Every obligation's status is computed from the clock, never stored. The sweep turns
*threshold crossings* into alerts, and the alert's semantic `dedupe_key` is what makes
running the sweep twice produce nothing new.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..core.config import get_settings
from ..models import Alert, Application, Document, EvcVisit, ExtractedField, Undertaking
from . import alert_service, policy

TERMINAL_STATES = ("approved", "rejected", "draft")


@dataclass
class DeadlineItem:
    entity_type: str
    entity_id: str
    alert_type: str
    due_at: datetime
    cycle_key: str
    application_id: str
    payload: dict = field(default_factory=dict)


@dataclass
class SweepResult:
    scanned: int = 0
    created: int = 0
    existing: int = 0
    delivered: int = 0
    failed: int = 0
    suppressed: int = 0
    alerts: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "created": self.created,
            "existing": self.existing,
            "delivered": self.delivered,
            "failed": self.failed,
            "suppressed": self.suppressed,
            "alerts": self.alerts,
        }


def end_of_day(value: date) -> datetime:
    """Deadlines are end-of-day in the configured business timezone, stored in UTC."""
    settings = get_settings()
    tz = ZoneInfo(settings.business_timezone)
    return datetime.combine(value, time(23, 59, 59), tzinfo=tz).astimezone(UTC)


def collect_items(db: Session, now: datetime) -> list[DeadlineItem]:
    items: list[DeadlineItem] = []

    # 1. Undertakings awaiting evidence or verification.
    undertakings = db.scalars(
        select(Undertaking).where(Undertaking.status.in_(("pending", "submitted")))
    ).all()
    for undertaking in undertakings:
        due_at = to_utc(undertaking.due_at)
        if due_at is None:
            continue
        items.append(
            DeadlineItem(
                entity_type="undertaking",
                entity_id=undertaking.id,
                alert_type="undertaking_due",
                due_at=due_at,
                cycle_key=due_at.date().isoformat(),
                application_id=undertaking.application_id,
                payload={
                    "title": undertaking.title,
                    "status": undertaking.status,
                    "evidence_required": undertaking.evidence_required,
                },
            )
        )

    # 2. Verified document validity. Unverified extracted dates must not drive alerts.
    documents = db.scalars(
        select(Document)
        .where(Document.application_id.is_not(None), Document.status != "rejected")
        .order_by(Document.uploaded_at.asc())
    ).all()
    latest: dict[tuple[str, str], Document] = {}
    for document in documents:
        latest[(document.application_id, document.doc_type)] = document

    for (application_id, doc_type), document in latest.items():
        field_row = db.scalars(
            select(ExtractedField).where(
                ExtractedField.document_id == document.id,
                ExtractedField.document_version == document.version,
                ExtractedField.field_name.in_(("valid_to", "lease_expiry")),
                ExtractedField.verification_status == "verified",
            )
        ).first()
        if field_row is None or not field_row.value:
            continue
        try:
            expiry = date.fromisoformat(str(field_row.value)[:10])
        except ValueError:
            continue
        due_at = end_of_day(expiry)
        items.append(
            DeadlineItem(
                entity_type="document",
                entity_id=document.id,
                alert_type="document_expiry",
                due_at=due_at,
                cycle_key=document.id,
                application_id=application_id,
                payload={
                    "doc_type": doc_type,
                    "valid_to": expiry.isoformat(),
                    "source": f"document:{document.id}#page={field_row.source_page}",
                },
            )
        )

    # 3. Scheduled EVC visits: remind before, escalate after the visit date.
    visits = db.scalars(
        select(EvcVisit).where(EvcVisit.status == "scheduled")
    ).all()
    for visit in visits:
        due_at = end_of_day(visit.scheduled_date)
        items.append(
            DeadlineItem(
                entity_type="evc_visit",
                entity_id=visit.id,
                alert_type="evc_visit",
                due_at=due_at,
                cycle_key=visit.id,
                application_id=visit.application_id,
                payload={
                    "scheduled_date": visit.scheduled_date.isoformat(),
                    "venue": visit.venue,
                },
            )
        )

    # 4. Stage ageing against the configured SLA for the route.
    applications = db.scalars(
        select(Application).where(Application.current_state.notin_(TERMINAL_STATES))
    ).all()
    for application in applications:
        sla = policy.stage_sla_days(application.route_key, application.current_state)
        if sla is None:
            continue
        since = to_utc(application.current_state_since) or now
        due_at = since + timedelta(days=sla)
        # PRD §11 escalation ladder (Phase 3.4): the same elapsed/limit clock,
        # expressed as the L0-L3 level the case has reached. Advisory and
        # additive — it rides in the payload so the alert shows who it would
        # escalate to, without a second clock, a dedupe change, or a new gate.
        from . import escalation as _escalation

        elapsed = max(0, (now - since).days)
        items.append(
            DeadlineItem(
                entity_type="application",
                entity_id=application.id,
                alert_type="stage_ageing",
                due_at=due_at,
                cycle_key=f"{application.current_state}:{since.date().isoformat()}",
                application_id=application.id,
                payload={
                    "state": application.current_state,
                    "sla_days": sla,
                    "days_in_state": elapsed,
                    "escalation_level": _escalation.level_for_percentage(elapsed, sla),
                },
            )
        )

    # 5. Appeal window on a decision (FR-27, Phase 3.5). Advisory reminder
    # only — it raises the day-3 / day-6 alerts, never a gate (DEC-0003).
    decided = db.scalars(
        select(Application).where(Application.current_state.in_(("approved", "rejected")))
    ).all()
    for application in decided:
        from . import appeal as _appeal

        item = _appeal.appeal_window_item(application, now)
        if item is not None:
            items.append(item)

    return items


def eligible_thresholds(alert_type: str, due_at: datetime, now: datetime):
    kind = {
        "undertaking_due": "undertaking",
        "document_expiry": "document_expiry",
        "stage_ageing": "stage_ageing",
        "evc_visit": "evc_visit",
        "appeal_window": "appeal",
    }[alert_type]
    for threshold in policy.thresholds(kind):
        if now >= due_at + timedelta(days=threshold.offset_days):
            yield threshold


def _get_or_create_alert(
    db: Session, item: DeadlineItem, level: str, severity: str, recipients: list[str], now: datetime
) -> tuple[Alert, bool]:
    dedupe_key = f"{item.entity_type}:{item.entity_id}:{item.alert_type}:{level}:{item.cycle_key}"
    existing = db.scalars(select(Alert).where(Alert.dedupe_key == dedupe_key)).first()
    if existing is not None:
        return existing, False

    alert = Alert(
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        alert_type=item.alert_type,
        level=level,
        cycle_key=item.cycle_key,
        dedupe_key=dedupe_key,
        due_at=item.due_at,
        fired_at=now,
        status="open",
        recipients=recipients,
        payload={**item.payload, "severity": severity},
    )
    try:
        with db.begin_nested():
            db.add(alert)
            db.flush()
        return alert, True
    except IntegrityError:
        # A concurrent sweep won the race. The unique constraint is the source of truth.
        return db.scalars(select(Alert).where(Alert.dedupe_key == dedupe_key)).one(), False


def sweep(db: Session, now: datetime | None = None, *, dry_run: bool = False) -> SweepResult:
    now = now or get_clock().now()
    result = SweepResult()
    items = collect_items(db, now)

    for item in items:
        application = db.get(Application, item.application_id)
        if application is None:
            continue
        for threshold in eligible_thresholds(item.alert_type, item.due_at, now):
            result.scanned += 1
            recipients = alert_service.recipients_for(
                db, application, severity=threshold.severity
            )
            if dry_run:
                continue
            alert, created = _get_or_create_alert(
                db, item, threshold.level, threshold.severity, recipients, now
            )
            if created:
                result.created += 1
                # Alerts are system-generated, so the actor is the system. The
                # event is what makes "who was told, and when" auditable rather
                # than something you have to take on trust.
                from .audit_service import AuditService

                AuditService(db).append(
                    action=(
                        "alert.escalated"
                        if threshold.severity == "escalated"
                        else "alert.fired"
                    ),
                    entity_type="alert",
                    entity_id=alert.id,
                    outcome="accepted",
                    actor_role="system",
                    reason=f"{threshold.level} ({threshold.severity})",
                    after={
                        "application_id": item.application_id,
                        "alert_type": alert.alert_type,
                        "level": alert.level,
                        "severity": threshold.severity,
                        "due_at": iso(item.due_at),
                        "recipients": recipients,
                    },
                )
            else:
                result.existing += 1

            outcome = alert_service.deliver(db, alert)
            if outcome.suppressed:
                # Acknowledged or closed: deliberately silent, not a failure.
                result.suppressed += 1
            elif outcome.delivered:
                result.delivered += 1
            else:
                result.failed += 1
            result.alerts.append(
                {
                    "alert_id": alert.id,
                    "entity_type": alert.entity_type,
                    "entity_id": alert.entity_id,
                    "alert_type": alert.alert_type,
                    "level": alert.level,
                    "dedupe_key": alert.dedupe_key,
                    "created": created,
                    "delivery": {
                        "delivered": outcome.delivered,
                        "attempt": outcome.attempt,
                        "error": outcome.error,
                        "suppressed": outcome.suppressed,
                    },
                }
            )

    if not dry_run:
        db.commit()
    return result
