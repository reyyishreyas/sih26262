"""Persistent deadline job.

Run as a separate process (`python -m app.workers.scheduler`). It re-queries the
database on every tick, so a restart never loses a deadline and two workers never
create two logical alerts — the unique dedupe key decides.
"""

from __future__ import annotations

from ..core.db import SessionLocal
from ..services import alert_service, deadline_service


def run_once() -> dict:
    db = SessionLocal()
    try:
        result = deadline_service.sweep(db)
        return result.as_dict()
    finally:
        db.close()


def retry_pending(max_attempts: int = 3) -> dict:
    from sqlalchemy import select

    from ..models import Alert

    db = SessionLocal()
    try:
        alerts = db.scalars(
            select(Alert).where(Alert.status != "delivered").order_by(Alert.fired_at)
        ).all()
        retried = 0
        delivered = 0
        failed = 0
        for alert in alerts:
            attempts = len(alert.deliveries or [])
            if attempts == 0 or attempts >= max_attempts:
                continue
            outcome = alert_service.deliver(db, alert, max_attempts=max_attempts)
            retried += 1
            delivered += int(outcome.delivered)
            failed += int(not outcome.delivered)
        db.commit()
        return {"retried": retried, "delivered": delivered, "failed": failed}
    finally:
        db.close()
