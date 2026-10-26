"""Optimistic concurrency on workflow writes (Phase 0.5 H.1).

A transition (or revert) that carries a stale `expected_baseline_version` is
rejected with a reload message and an audit event, and leaves no partial write
— two officers working from the same snapshot can never silently overwrite
each other (Essentials §14a; rules2 SYS-CONCUR-001).

True parallel requests are simulated deterministically: two sequential calls
that share the same observed version are exactly what concurrency produces
for a SQLite test database, without flaky threads.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Application, AuditEvent, WorkflowTransition
from app.services import workflow_service
from app.services.audit_service import verify_chain


def _app(db, app_id: str) -> Application:
    return db.get(Application, app_id)


def _rejected_events(db, app_id: str) -> list[AuditEvent]:
    return db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == app_id, AuditEvent.outcome == "rejected")
        .order_by(AuditEvent.seq)
    ).all()


def test_matching_expected_version_is_accepted(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")

    decision = workflow_service.request_transition(
        db,
        access,
        application.id,
        "approve",
        reason="Scrutiny complete",
        expected_baseline_version=application.baseline_version,
    )

    assert decision.accepted is True
    assert _app(db, application.id).current_state == "approved"


def test_stale_expected_version_is_rejected_with_reload_message(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    stale = application.baseline_version

    first = workflow_service.request_transition(
        db, access, application.id, "approve", reason="Scrutiny complete"
    )
    assert first.accepted is True

    # The officer's screen still shows the pre-approval version; the case has
    # moved. Even an action that would otherwise be plausible must not apply.
    second = workflow_service.request_transition(
        db,
        access,
        application.id,
        "reject",
        reason="Changed my mind",
        expected_baseline_version=stale,
    )

    assert second.accepted is False
    assert any("reload" in reason for reason in second.reasons)
    refreshed = _app(db, application.id)
    assert refreshed.current_state == "approved"  # no partial write
    rejected = _rejected_events(db, application.id)
    assert rejected, "a stale write must be audited like any rejected action"
    assert "reload" in rejected[-1].reason
    assert verify_chain(db).ok is True


def test_duplicate_request_with_same_version_cannot_double_advance(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    observed = application.baseline_version

    first = workflow_service.request_transition(
        db,
        access,
        application.id,
        "approve",
        reason="Scrutiny complete",
        expected_baseline_version=observed,
    )
    duplicate = workflow_service.request_transition(
        db,
        access,
        application.id,
        "approve",
        reason="Scrutiny complete",
        expected_baseline_version=observed,
    )

    assert first.accepted is True
    assert duplicate.accepted is False
    assert _app(db, application.id).current_state == "approved"
    approvals = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == application.id,
            WorkflowTransition.action == "approve",
        )
    ).all()
    assert len(approvals) == 1, "the duplicate must not create a second step"


def test_omitted_expected_version_keeps_the_existing_contract(db, access_for):
    """Backwards compatibility: clients that do not send the field behave as before."""
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")

    decision = workflow_service.request_transition(
        db, access, application.id, "approve", reason="Scrutiny complete"
    )

    assert decision.accepted is True
    assert _app(db, application.id).current_state == "approved"


def test_invalid_action_with_current_version_leaves_no_partial_write(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    version_before = application.baseline_version
    transitions_before = db.scalar(
        select(func.count()).select_from(WorkflowTransition)
    )

    # schedule_evc is not defined for the existing_technical route: the version
    # is current, so this must fail on the route guard, not the concurrency one.
    decision = workflow_service.request_transition(
        db,
        access,
        application.id,
        "schedule_evc",
        expected_baseline_version=version_before,
    )

    assert decision.accepted is False
    assert "not defined for route" in decision.reasons[0]
    refreshed = _app(db, application.id)
    assert refreshed.current_state == "scrutiny"
    assert refreshed.baseline_version == version_before
    assert (
        db.scalar(select(func.count()).select_from(WorkflowTransition))
        == transitions_before
    )


def test_stale_revert_is_rejected_and_current_version_reverts(db, access_for):
    scrutiny = access_for("scrutiny@demo.local")
    admin = access_for("admin@demo.local")
    application = _app(db, "app-existing-0003")

    approved = workflow_service.request_transition(
        db, scrutiny, application.id, "approve", reason="Scrutiny complete"
    )
    assert approved.accepted is True
    stale = _app(db, application.id).baseline_version - 1

    stale_revert = workflow_service.revert_last_transition(
        db,
        admin,
        application.id,
        reason="Undo by mistake",
        expected_baseline_version=stale,
    )
    assert stale_revert.accepted is False
    assert any("reload" in reason for reason in stale_revert.reasons)
    assert _app(db, application.id).current_state == "approved"

    good_revert = workflow_service.revert_last_transition(
        db,
        admin,
        application.id,
        reason="Undo by mistake",
        expected_baseline_version=_app(db, application.id).baseline_version,
    )
    assert good_revert.accepted is True
    assert _app(db, application.id).current_state == "scrutiny"


def test_transition_endpoint_carries_the_expected_version(db, client, as_user):
    """HTTP contract: the field flows through the endpoint, not just the service."""
    officer = as_user("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")

    accepted = client.post(
        f"/api/v1/applications/{application.id}/transitions",
        headers=officer,
        json={
            "action": "approve",
            "reason": "Scrutiny complete",
            "expected_baseline_version": application.baseline_version,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True

    stale = client.post(
        f"/api/v1/applications/{application.id}/transitions",
        headers=officer,
        json={
            "action": "reject",
            "reason": "Changed my mind",
            "expected_baseline_version": application.baseline_version,
        },
    )
    assert stale.status_code == 200
    body = stale.json()
    assert body["accepted"] is False
    assert any("reload" in reason for reason in body["reasons"])
    # The API commits in its own session; drop this session's cached snapshot
    # before asserting on the database (see BUG-0003).
    db.expire_all()
    assert _app(db, application.id).current_state == "approved"
