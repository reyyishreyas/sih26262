"""Officers impose follow-up conditions; a late condition blocks approval."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.clock import get_clock
from app.models import Application, AuditEvent, Undertaking
from app.services import compliance_service, workflow_service
from app.services.evidence_service import build_snapshot


def _undertakings(client, headers, app_id="app-main-0001"):
    return client.get(f"/api/v1/applications/{app_id}/undertakings", headers=headers).json()


# ---------------------------------------------------------------------------
# Creating a condition
# ---------------------------------------------------------------------------


def test_an_officer_creates_a_follow_up_condition(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    created = client.post(
        "/api/v1/applications/app-main-0001/undertakings",
        headers=headers,
        json={
            "title": "Install fire safety equipment",
            "condition_text": "Third-party fire NOC and equipment invoices.",
            "evidence_required": "Fire NOC plus invoices",
            "due_at": "2026-12-31",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["obligation_key"] == "install_fire_safety_equipment"
    assert body["due_at"].startswith("2026-12-31")

    listed = _undertakings(client, headers)
    assert any(item["id"] == body["id"] for item in listed)

    # The creation is audited with the officer as the actor.
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "undertaking.created")
    ).first()
    assert event is not None
    assert event.after["application_id"] == "app-main-0001"


def test_the_college_cannot_impose_conditions_on_itself(client, as_user):
    college = as_user("institution@demo.local")
    attempt = client.post(
        "/api/v1/applications/app-main-0001/undertakings",
        headers=college,
        json={"title": "Ignore our late tasks", "due_at": "2026-12-31"},
    )
    assert attempt.status_code == 403


def test_a_condition_cannot_be_due_in_the_past(client, as_user):
    headers = as_user("scrutiny@demo.local")
    response = client.post(
        "/api/v1/applications/app-main-0001/undertakings",
        headers=headers,
        json={"title": "Retroactive condition", "due_at": "2020-01-01"},
    )
    assert response.status_code == 422


def test_duplicate_keys_on_one_case_are_refused(client, as_user):
    headers = as_user("scrutiny@demo.local")
    payload = {"title": "Submit playground equipment", "due_at": "2026-12-31"}
    first = client.post(
        "/api/v1/applications/app-main-0001/undertakings", headers=headers, json=payload
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/applications/app-main-0001/undertakings", headers=headers, json=payload
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Waiving a condition
# ---------------------------------------------------------------------------


def test_waiving_needs_a_reason(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    items = _undertakings(client, headers)
    pending = next(item for item in items if item["status"] == "pending")

    refused = client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/waive",
        headers=headers,
        json={"reason": "   "},
    )
    assert refused.status_code == 422
    assert db.get(Undertaking, pending["id"]).status == "pending"


def test_waiving_clears_the_condition_with_a_reason(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    items = _undertakings(client, headers)
    pending = next(item for item in items if item["status"] == "pending")

    waived = client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/waive",
        headers=headers,
        json={"reason": "Already covered by the approved lease deed."},
    )
    assert waived.status_code == 200
    assert waived.json()["status"] == "waived"

    event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "undertaking.waived")
    ).first()
    assert event.reason == "Already covered by the approved lease deed."


def test_a_waived_condition_cannot_be_waived_again(client, as_user):
    headers = as_user("scrutiny@demo.local")
    items = _undertakings(client, headers)
    pending = next(item for item in items if item["status"] == "pending")
    client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/waive",
        headers=headers,
        json={"reason": "Not needed."},
    )
    again = client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/waive",
        headers=headers,
        json={"reason": "Not needed."},
    )
    assert again.status_code == 409


# ---------------------------------------------------------------------------
# The approval gate
# ---------------------------------------------------------------------------


def test_the_snapshot_carries_a_verified_overdue_summary(db):
    application = db.get(Application, "app-main-0001")
    snapshot = build_snapshot(db, application)
    summary = snapshot.values["undertakings_summary"]
    # Seed: one condition due in 20 days, one overdue by 10 days, both pending.
    assert summary["total"] == 2
    assert summary["open"] == 2
    assert summary["overdue"] == 1
    assert snapshot.is_verified("undertakings_summary.overdue") is True


def test_the_lateness_rule_passes_when_nothing_is_overdue(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    items = _undertakings(client, headers)
    late = [
        item
        for item in items
        if item["status"] == "pending" and item["due_at"] < "2026-10-23"
    ]
    for item in late:
        client.post(
            f"/api/v1/applications/app-main-0001/undertakings/{item['id']}/waive",
            headers=headers,
            json={"reason": "Cleared before the decision."},
        )

    application = db.get(Application, "app-main-0001")
    snapshot = build_snapshot(db, application)
    assert snapshot.values["undertakings_summary"]["overdue"] == 0

    specs = compliance_service.load_rule_specs(db)
    from app.services.rule_engine import evaluate_rules

    results = {r.rule_key: r for r in evaluate_rules(specs, snapshot)}
    assert results["UNDERTAKING_NO_OVERDUE"].outcome.value == "PASS"


def test_unverified_overdue_rule_is_advisory_for_approval(db, client, as_user, access_for):
    headers = as_user("scrutiny@demo.local")
    created = client.post(
        "/api/v1/applications/app-existing-0003/undertakings",
        headers=headers,
        json={"title": "Top up the library fund", "due_at": "2026-12-31"},
    )
    assert created.status_code == 201

    # Age the condition past its due date so the gate has something to catch.
    item = db.get(Undertaking, created.json()["id"])
    item.due_at = get_clock().now() - timedelta(days=5)
    db.commit()

    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, "app-existing-0003", "approve", reason="All good"
    )
    assert decision.accepted is True
    result = next(row for row in decision.rule_results if row.rule_key == "UNDERTAKING_NO_OVERDUE")
    assert result.outcome.value == "FAIL"
    assert result.regulatory_status == "unverified"
    assert result.blocking is False
    assert db.get(Application, "app-existing-0003").current_state == "approved"


def test_unverified_overdue_rule_does_not_disable_transition_option(db, client, as_user, access_for):
    headers = as_user("scrutiny@demo.local")
    created = client.post(
        "/api/v1/applications/app-existing-0003/undertakings",
        headers=headers,
        json={"title": "Top up the library fund", "due_at": "2026-12-31"},
    )
    item = db.get(Undertaking, created.json()["id"])
    item.due_at = get_clock().now() - timedelta(days=5)
    db.commit()

    access = access_for("scrutiny@demo.local")
    before = next(
        entry
        for entry in workflow_service.available_transitions(
            db, access, db.get(Application, "app-existing-0003")
        )
        if entry["action"] == "approve"
    )
    assert not any("UNDERTAKING_NO_OVERDUE" in item for item in before["blocked_by"])

    # The officer waives it with a reason; the gate reopens on the next check.
    waived = client.post(
        f"/api/v1/applications/app-existing-0003/undertakings/{item.id}/waive",
        headers=headers,
        json={"reason": "Fund credited on 20 Oct; receipt on file."},
    )
    assert waived.status_code == 200
    # The API ran in its own session; expire ours so the next read is fresh.
    db.expire_all()

    after = next(
        entry
        for entry in workflow_service.available_transitions(
            db, access, db.get(Application, "app-existing-0003")
        )
        if entry["action"] == "approve"
    )
    assert not any("UNDERTAKING_NO_OVERDUE" in item for item in after["blocked_by"])
