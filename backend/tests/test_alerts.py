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
