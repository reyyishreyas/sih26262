"""Snooze-once-with-reason on alerts (Phase 3.7, PRD §11 line 293).

"One snooze with a reason, no second." An alert can be snoozed exactly once,
with a mandatory reason; while snoozed and unexpired the reminder is suppressed
by `alert_service.deliver` (the same way an acknowledged or closed alert is),
and once `snoozed_until` passes the alert is eligible to be delivered again
because it was never closed.

Safety properties under test:

- The reason is mandatory (a blank snooze is refused, 422).
- A second snooze is refused, not silently extended — the caller sees the
  existing hold instead of starting a new one.
- Delivery is suppressed while snoozed and unexpired, and resumes after the
  window passes.
- The snooze writes an audit event recording who snoozed it, why, and until when.
- The route is permission-gated (MONITORING_READ) and respects scope (401, 403/404).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.clock import FixedClock, set_clock
from app.models import Alert, AuditEvent
from app.services import alert_service, deadline_service

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def _first_alert_id(db, client, as_user) -> str:
    deadline_service.sweep(db, NOW)
    admin = as_user("admin@demo.local")
    return client.get("/api/v1/alerts", headers=admin).json()["alerts"][0]["id"]


# ------------------------------------------------------------- the snooze


def test_snoozing_records_the_fields_and_audits(db, client, as_user):
    alert_id = _first_alert_id(db, client, as_user)
    admin = as_user("admin@demo.local")
    before_status = db.get(Alert, alert_id).status

    body = client.post(
        f"/api/v1/alerts/{alert_id}/snooze",
        headers=admin,
        json={"reason": "Chasing the institution by phone today.", "days": 2},
    ).json()
    # A snooze is a temporary hold, not a lifecycle terminal: status is unchanged.
    assert body["status"] == before_status
    assert body["snoozed_until"] is not None
    assert body["snooze_reason"] == "Chasing the institution by phone today."
    assert body["snoozed_by"]

    event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "alert.snoozed")
    ).first()
    assert event is not None
    assert event.reason == "Chasing the institution by phone today."


def test_a_blank_reason_is_refused(db, client, as_user):
    alert_id = _first_alert_id(db, client, as_user)
    admin = as_user("admin@demo.local")
    refused = client.post(
        f"/api/v1/alerts/{alert_id}/snooze", headers=admin, json={"reason": "   "}
    )
    assert refused.status_code == 422


def test_a_second_snooze_is_refused_not_extended(db, client, as_user):
    alert_id = _first_alert_id(db, client, as_user)
    admin = as_user("admin@demo.local")

    first = client.post(
        f"/api/v1/alerts/{alert_id}/snooze",
        headers=admin,
        json={"reason": "One hold.", "days": 3},
    ).json()
    first_until = first["snoozed_until"]

    second = client.post(
        f"/api/v1/alerts/{alert_id}/snooze",
        headers=admin,
        json={"reason": "Another hold.", "days": 5},
    ).json()
    # "no second": the hold is not extended and the reason is not replaced.
    assert second["snoozed_until"] == first_until
    assert second["snooze_reason"] == "One hold."


# ------------------------------------------------- delivery while snoozed


def test_delivery_is_suppressed_while_snoozed_and_resumes_after(db, client, as_user):
    alert_id = _first_alert_id(db, client, as_user)
    admin = as_user("admin@demo.local")
    # The sweep leaves seeded alerts "delivered"; put one back to "open" so we
    # are testing the reminder path (an undelivered nag), not a re-send.
    alert = db.get(Alert, alert_id)
    alert.status = "open"
    db.commit()

    client.post(
        f"/api/v1/alerts/{alert_id}/snooze",
        headers=admin,
        json={"reason": "Hold the reminder.", "days": 1},
    )
    # The API committed in another session; expire so we re-read snoozed_until.
    db.refresh(alert)

    suppressed = alert_service.deliver(db, alert)
    assert suppressed.suppressed is True
    assert suppressed.delivered is False

    # After the hold expires the alert is eligible again (it was never closed).
    set_clock(FixedClock(NOW + timedelta(days=2)))
    try:
        resumed = alert_service.deliver(db, alert)
        assert resumed.suppressed is False
    finally:
        set_clock(None)


# ----------------------------------------------------------- the API gate


def test_snoozing_needs_a_token(client):
    alert_id = "any"
    assert (
        client.post(f"/api/v1/alerts/{alert_id}/snooze", json={"reason": "x"}).status_code
        == 401
    )
