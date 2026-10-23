"""Deadlines and alerts: idempotence, boundaries, recipients, retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.adapters.notifications.mock import MockNotificationAdapter
from app.models import Alert, AlertDelivery, Document, User
from app.services import alert_service, deadline_service

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def test_repeated_sweeps_create_no_duplicate_alerts(db):
    first = deadline_service.sweep(db, NOW)
    assert first.created > 0

    second = deadline_service.sweep(db, NOW)
    assert second.created == 0
    assert second.existing == first.created

    third = deadline_service.sweep(db, NOW)
    assert third.created == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == first.created


def test_dedupe_keys_are_unique(db):
    deadline_service.sweep(db, NOW)
    keys = db.scalars(select(Alert.dedupe_key)).all()
    assert len(keys) == len(set(keys))
    for key in keys:
        parts = key.split(":")
        assert len(parts) >= 5


def test_threshold_boundaries():
    due = NOW
    levels = {t.level for t in deadline_service.eligible_thresholds("undertaking_due", due, NOW)}
    assert levels == {"reminder_30", "reminder_7"}

    just_before_due = due - timedelta(minutes=1)
    levels = {
        t.level
        for t in deadline_service.eligible_thresholds(
            "undertaking_due", due, just_before_due
        )
    }
    assert levels == {"reminder_30", "reminder_7"}

    after_due = due + timedelta(days=1, minutes=1)
    levels = {
        t.level
        for t in deadline_service.eligible_thresholds("undertaking_due", due, after_due)
    }
    assert "overdue" in levels

    after_escalation = due + timedelta(days=8)
    levels = {
        t.level
        for t in deadline_service.eligible_thresholds(
            "undertaking_due", due, after_escalation
        )
    }
    assert "escalated" in levels


def test_escalated_alerts_reach_the_regional_officer(db):
    deadline_service.sweep(db, NOW)
    escalated = db.scalars(select(Alert).where(Alert.level == "escalated")).all()
    assert escalated, "the overdue undertaking should escalate"
    regional = db.scalars(
        select(User).where(User.email == "regional@demo.local")
    ).one()
    for alert in escalated:
        assert regional.id in alert.recipients


def test_unverified_expiry_does_not_raise_an_alert(db):
    document = db.scalars(
        select(Document).where(
            Document.application_id == "app-second-0002",
            Document.doc_type == "lease_deed",
        )
    ).one()
    result = deadline_service.sweep(db, NOW)
    for alert in result.alerts:
        assert not (alert["entity_type"] == "document" and alert["entity_id"] == document.id)


def test_delivery_failure_is_recorded_and_retried(db):
    failing = MockNotificationAdapter(fail_times=100)
    alert_service.set_notification_adapter(failing)
    try:
        first = deadline_service.sweep(db, NOW)
        assert first.failed > 0
        alert = db.scalars(select(Alert).where(Alert.status != "delivered")).first()
        assert alert is not None
        failed_attempts = db.scalar(
            select(func.count()).select_from(AlertDelivery).where(
                AlertDelivery.alert_id == alert.id, AlertDelivery.status == "failed"
            )
        )
        assert failed_attempts >= 1

        alert_service.set_notification_adapter(MockNotificationAdapter())
        second = deadline_service.sweep(db, NOW)
        assert second.delivered > 0
        db.refresh(alert)
        statuses = [delivery.status for delivery in alert.deliveries]
        assert "sent" in statuses
        assert alert.status == "delivered"
    finally:
        alert_service.set_notification_adapter(MockNotificationAdapter())


def test_dry_run_writes_nothing(db):
    before = db.scalar(select(func.count()).select_from(Alert))
    result = deadline_service.sweep(db, NOW, dry_run=True)
    assert result.scanned > 0
    assert result.created == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == before


def test_alert_delivery_is_marked_simulated(db, tmp_path):
    adapter = MockNotificationAdapter(log_path=tmp_path / "notifications.log")
    alert_service.set_notification_adapter(adapter)
    try:
        deadline_service.sweep(db, NOW)
        log = (tmp_path / "notifications.log").read_text()
        assert '"simulated": true' in log.replace("True", "true")
    finally:
        alert_service.set_notification_adapter(MockNotificationAdapter())


# ---------------------------------------------------------------------------
# Lifecycle: acknowledge, close, audit
# ---------------------------------------------------------------------------


def test_acknowledging_then_closing_an_alert_is_audited(db, client, as_user):
    deadline_service.sweep(db, NOW)
    admin = as_user("admin@demo.local")
    alert_id = client.get("/api/v1/alerts", headers=admin).json()["alerts"][0]["id"]

    acked = client.post(f"/api/v1/alerts/{alert_id}/ack", headers=admin)
    assert acked.status_code == 200
    body = acked.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None
    assert body["acknowledged_by"]

    # Idempotent: the second ack must not move the timestamp or add an event.
    again = client.post(f"/api/v1/alerts/{alert_id}/ack", headers=admin)
    assert again.json()["acknowledged_at"] == body["acknowledged_at"]

    # Closing demands a reason — an alert must not vanish without explanation.
    bare = client.post(
        f"/api/v1/alerts/{alert_id}/close", headers=admin, json={"reason": "   "}
    )
    assert bare.status_code == 422

    closed = client.post(
        f"/api/v1/alerts/{alert_id}/close",
        headers=admin,
        json={"reason": "Evidence uploaded and checked."},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["close_reason"] == "Evidence uploaded and checked."

    from app.models import AuditEvent

    actions = list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id == alert_id)
            .order_by(AuditEvent.seq)
        )
    )
    # The sweep's own "fired" event comes first, then the two officer actions
    # in the order they happened.
    assert actions == ["alert.fired", "alert.acknowledged", "alert.closed"]


def test_firing_an_alert_writes_an_audit_event(db):
    result = deadline_service.sweep(db, NOW)
    assert result.created > 0

    from app.models import AuditEvent

    fired = db.scalars(
        select(AuditEvent).where(AuditEvent.action.in_(("alert.fired", "alert.escalated")))
    ).all()
    assert len(fired) == result.created
    for event in fired:
        assert event.actor_role == "system"
        assert event.outcome == "accepted"
        assert event.after["application_id"]


def test_a_closed_alert_is_not_re_delivered(db):
    deadline_service.sweep(db, NOW)
    alert = db.scalars(select(Alert).where(Alert.status == "delivered")).first()
    assert alert is not None
    alert.status = "closed"
    db.commit()

    result = deadline_service.sweep(db, NOW)
    assert result.suppressed >= 1
    assert result.failed == 0
    # Nothing new went out for the alert we closed.
    closed_entry = next(
        entry for entry in result.alerts if entry["alert_id"] == alert.id
    )
    assert closed_entry["delivery"]["suppressed"] is True


def test_alerts_outside_your_scope_look_missing(db, client, as_user):
    """An officer must not be able to probe alerts on cases they cannot see."""
    deadline_service.sweep(db, NOW)
    admin = as_user("admin@demo.local")
    alert_id = client.get("/api/v1/alerts", headers=admin).json()["alerts"][0]["id"]

    # The EVC member is scoped to their committee and cannot read monitoring.
    evc = as_user("evc@demo.local")
    denied = client.post(f"/api/v1/alerts/{alert_id}/ack", headers=evc)
    assert denied.status_code == 403

    missing = client.post("/api/v1/alerts/no-such-alert/ack", headers=admin)
    assert missing.status_code == 404
