"""Bounded retention for transient operational rows.

Audit events are deliberately out of scope: deleting an event in the middle of the
hash chain would make every later event unverifiable. A records-retention policy for
the audit log needs an archival/re-anchoring design and legal sign-off, not a
nightly DELETE.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..models import AlertDelivery, LoginAttempt


@dataclass(frozen=True)
class RetentionPlan:
    now: datetime
    login_attempt_cutoff: datetime
    alert_delivery_cutoff: datetime
    login_attempts_eligible: int
    alert_deliveries_eligible: int

    def as_dict(self) -> dict:
        return asdict(self)


def plan_retention(db: Session, *, now: datetime, settings: Settings) -> RetentionPlan:
    login_cutoff = now - timedelta(days=settings.retention_login_attempt_days)
    delivery_cutoff = now - timedelta(days=settings.retention_alert_delivery_days)
    login_count = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.attempted_at < login_cutoff)
    ) or 0
    delivery_count = db.scalar(
        select(func.count())
        .select_from(AlertDelivery)
        .where(AlertDelivery.attempted_at < delivery_cutoff)
    ) or 0
    return RetentionPlan(
        now=now,
        login_attempt_cutoff=login_cutoff,
        alert_delivery_cutoff=delivery_cutoff,
        login_attempts_eligible=int(login_count),
        alert_deliveries_eligible=int(delivery_count),
    )


def apply_retention(db: Session, *, now: datetime, settings: Settings) -> dict:
    plan = plan_retention(db, now=now, settings=settings)
    if plan.login_attempts_eligible:
        db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.attempted_at < plan.login_attempt_cutoff
            )
        )
    if plan.alert_deliveries_eligible:
        db.execute(
            delete(AlertDelivery).where(
                AlertDelivery.attempted_at < plan.alert_delivery_cutoff
            )
        )
    db.commit()
    return {
        **plan.as_dict(),
        "applied": True,
        "login_attempts_deleted": plan.login_attempts_eligible,
        "alert_deliveries_deleted": plan.alert_deliveries_eligible,
        "audit_events": "retained indefinitely; hash chain is not pruned",
    }
