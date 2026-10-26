"""Alert recipients and delivery.

Delivery is an adapter. The prototype uses an in-app/logged adapter, and can be told
to fail on purpose so the retry path is demonstrable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.notifications.mock import MockNotificationAdapter
from ..core.clock import get_clock, to_utc
from ..models import (
    Alert,
    Application,
    Institution,
    JurisdictionAssignment,
    Role,
    User,
    UserRoleAssignment,
)

_adapter: MockNotificationAdapter = MockNotificationAdapter()


def set_notification_adapter(adapter: MockNotificationAdapter) -> None:
    global _adapter
    _adapter = adapter


def get_notification_adapter() -> MockNotificationAdapter:
    return _adapter


@dataclass
class DeliveryOutcome:
    delivered: bool
    attempt: int
    provider_ref: str | None = None
    error: str | None = None
    # True when nothing was sent on purpose (the alert was acknowledged or
    # closed). Distinct from a failure so reports never claim a nag went out.
    suppressed: bool = False


def _users_with_role(
    db: Session, role_name: str, *, scope_type: str, scope_id: str | None
) -> list[str]:
    query = (
        select(User.id)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            Role.name == role_name,
            User.is_active.is_(True),
            UserRoleAssignment.revoked_at.is_(None),
        )
    )
    if scope_id is not None:
        query = query.where(
            UserRoleAssignment.scope_type == scope_type,
            UserRoleAssignment.scope_id == scope_id,
        )
    return list(db.scalars(query).all())


def regional_officers(db: Session, region_id: str) -> list[str]:
    direct = _users_with_role(
        db, "regional_officer", scope_type="region", scope_id=region_id
    )
    via_jurisdiction = list(
        db.scalars(
            select(JurisdictionAssignment.user_id)
            .join(User, User.id == JurisdictionAssignment.user_id)
            .where(
                JurisdictionAssignment.region_id == region_id,
                User.is_active.is_(True),
            )
        ).all()
    )
    return sorted(set(direct) | set(via_jurisdiction))


def supervisory_officers(db: Session, region_id: str) -> list[str]:
    """Users holding the `supervisory_officer` role scoped to a region.

    Used as the placeholder resolution for escalation level L2 ("Regulation
    Bureau", Phase 3.4) — the PRD names no explicit role for the Bureau and
    §19 Q5 leaves the designated authority per Region open, so the nearest
    existing region-scoped role is used, clearly labelled in the config.
    """
    return sorted(
        _users_with_role(db, "supervisory_officer", scope_type="region", scope_id=region_id)
    )


def recipients_for(
    db: Session, application: Application, *, severity: str
) -> list[str]:
    recipients: set[str] = set()
    recipients |= set(
        _users_with_role(
            db,
            "institution_representative",
            scope_type="institution",
            scope_id=application.institution_id,
        )
    )
    if application.assigned_officer_id:
        recipients.add(application.assigned_officer_id)

    if severity in ("warning", "critical", "escalated"):
        institution = db.get(Institution, application.institution_id)
        if institution:
            recipients |= set(regional_officers(db, institution.region_id))

    if severity == "escalated":
        institution = db.get(Institution, application.institution_id)
        if institution:
            recipients |= set(
                _users_with_role(
                    db,
                    "supervisory_officer",
                    scope_type="region",
                    scope_id=institution.region_id,
                )
            )
    return sorted(recipients)


def deliver(db: Session, alert: Alert, *, max_attempts: int = 3) -> DeliveryOutcome:
    from ..models import AlertDelivery

    attempts = len(alert.deliveries or [])
    if alert.status != "open":
        # Already sent, seen, or dealt with. Only "open" is eligible for a
        # (re)delivery attempt — a reminder must not nag after an officer
        # acknowledged or closed it.
        return DeliveryOutcome(
            delivered=False,
            attempt=attempts,
            provider_ref="suppressed",
            suppressed=True,
        )
    snoozed_until = to_utc(alert.snoozed_until)
    if snoozed_until is not None and get_clock().now() < snoozed_until:
        # Snoozed once with a reason (PRD §11 line 293) and the window has
        # not expired yet — suppress the reminder, exactly as an acknowledged
        # or closed alert is suppressed. Once the clock passes snoozed_until
        # the alert is eligible to be delivered again (it was never closed).
        return DeliveryOutcome(
            delivered=False,
            attempt=attempts,
            provider_ref="suppressed",
            suppressed=True,
        )
    if attempts >= max_attempts:
        return DeliveryOutcome(
            delivered=False,
            attempt=attempts,
            error="retry budget exhausted",
        )

    attempt = attempts + 1
    try:
        provider_ref = _adapter.send(alert)
    except Exception as exc:  # adapter failures are data, not crashes
        db.add(
            AlertDelivery(
                alert_id=alert.id,
                channel="in_app",
                attempt=attempt,
                status="failed",
                error=str(exc)[:500],
            )
        )
        return DeliveryOutcome(delivered=False, attempt=attempt, error=str(exc))

    db.add(
        AlertDelivery(
            alert_id=alert.id,
            channel="in_app",
            attempt=attempt,
            status="sent",
            provider_ref=provider_ref,
        )
    )
    alert.status = "delivered"
    return DeliveryOutcome(
        delivered=True, attempt=attempt, provider_ref=provider_ref
    )
