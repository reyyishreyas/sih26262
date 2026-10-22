"""Workflow transitions: guards, accepted/rejected paths, audited both ways."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Application, AuditEvent, WorkflowTransition
from app.services import workflow_service
from app.services.audit_service import verify_chain


def _app(db, app_id: str) -> Application:
    return db.get(Application, app_id)


def test_valid_transition_changes_state_and_audits(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    before_version = application.baseline_version

    decision = workflow_service.request_transition(
        db, access, application.id, "approve", reason="Scrutiny complete"
    )

    assert decision.accepted is True
    assert decision.to_state == "approved"
    refreshed = _app(db, application.id)
    assert refreshed.current_state == "approved"
    assert refreshed.baseline_version == before_version + 1

    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == application.id)
        .order_by(AuditEvent.seq)
    ).all()
    last = events[-1]
    assert last.action == "workflow.approve"
    assert last.outcome == "accepted"
    assert last.after["state"] == "approved"
    assert last.hash and last.prev_hash
    assert verify_chain(db).ok is True


def test_transition_blocked_by_missing_document_is_audited(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-main-0001")
    state_before = application.current_state

    decision = workflow_service.request_transition(
        db, access, application.id, "schedule_evc", reason=""
    )

    assert decision.accepted is False
    assert any("affidavit" in reason for reason in decision.reasons)
    assert _app(db, application.id).current_state == state_before

    rejected = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == application.id,
            AuditEvent.outcome == "rejected",
        )
    ).all()
    assert rejected, "a rejected transition must be recorded"
    assert rejected[-1].action == "workflow.schedule_evc"
    assert "required document" in rejected[-1].reason.lower()


def test_transition_blocked_by_role_is_audited(db, access_for):
    access = access_for("regional@demo.local")
    application = _app(db, "app-main-0001")

    decision = workflow_service.request_transition(
        db, access, application.id, "start_scrutiny"
    )

    assert decision.accepted is False
    assert "may not perform" in decision.reasons[0].lower()
    rejected = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == application.id,
            AuditEvent.outcome == "rejected",
        )
    ).all()
    assert rejected


def test_transition_requires_a_reason_when_configured(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    decision = workflow_service.request_transition(
        db, access, application.id, "reject", reason="   "
    )
    assert decision.accepted is False
    assert "requires a recorded reason" in decision.reasons[0]


def test_transition_not_defined_for_route_is_rejected(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-existing-0003")
    decision = workflow_service.request_transition(
        db, access, application.id, "schedule_evc"
    )
    assert decision.accepted is False
    assert "not defined for route" in decision.reasons[0]


def test_transition_from_wrong_state_is_rejected(db, access_for):
    access = access_for("institution@demo.local")
    application = _app(db, "app-draft-0004")
    decision = workflow_service.request_transition(
        db, access, application.id, "resubmit"
    )
    assert decision.accepted is False
    assert "requires state" in decision.reasons[0]


def test_rejection_does_not_lose_the_previous_audit_chain(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = _app(db, "app-main-0001")
    for action in ("schedule_evc", "schedule_evc"):
        workflow_service.request_transition(db, access, application.id, action)
    verification = verify_chain(db)
    assert verification.ok is True
    assert db.scalar(select(func.count()).select_from(WorkflowTransition)) == 0
