"""Transaction boundaries (Phase 0.5 H.2).

A workflow action is four writes — the case state, the transition history
row, the hand-off assignment and the audit event — and they must land in
**one** transaction: an audit-write failure fails the whole operation, and a
failure while updating the EVC booking rolls the move back with it. A case
must never be at ``evc_completed`` while its visit row still reads
``scheduled`` (Essentials 17-18; plan H.2).

Fault injection stands in for a database/storage failure at that exact
point: the write that should happen is replaced by one that raises, which
is what a failed write does. If the operation is not atomic, the assertions
below see the leftover half and fail.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import (
    Application,
    AuditEvent,
    CaseAssignment,
    EvcVisit,
    WorkflowTransition,
)
from app.services import audit_service, workflow_service
from app.services.audit_service import verify_chain


def _audit_events(db, app_id: str) -> list[AuditEvent]:
    return db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == app_id)
        .order_by(AuditEvent.seq)
    ).all()


def _transitions(db, app_id: str) -> list[WorkflowTransition]:
    return db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == app_id
        )
    ).all()


def _assignments(db, app_id: str) -> list[CaseAssignment]:
    return db.scalars(
        select(CaseAssignment).where(CaseAssignment.application_id == app_id)
    ).all()


def _evc_case_in_committee_stage(db, client, as_user) -> str:
    """A fresh evc_only case at ``evc_scheduled`` with a live booking."""
    college = as_user("institution@demo.local")
    officer = as_user("regional@demo.local")
    institution = client.get("/api/v1/institutions", headers=college).json()[0]
    created = client.post(
        "/api/v1/applications",
        headers=college,
        json={
            "institution_id": institution["id"],
            "category": "evc_only",
            "route_key": "evc_only",
            "cycle": "2027-28",
            "cycle_end": "2028-03-31",
        },
    )
    application_id = created.json()["id"]
    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "submit", "reason": ""},
    )
    booked = client.post(
        f"/api/v1/applications/{application_id}/evc/visits",
        headers=officer,
        json={"scheduled_date": "2026-11-05", "venue": "Campus"},
    )
    assert booked.status_code == 201
    assert booked.json()["case_advanced_to"] == "evc_scheduled"
    # The API committed in its own session; drop this session's snapshot.
    db.expire_all()
    return application_id


# ---------------------------------------------------------------------------
# The four effects commit together
# ---------------------------------------------------------------------------


def test_one_transition_writes_state_history_assignment_and_audit_together(
    db, access_for
):
    access = access_for("institution@demo.local")
    application = db.get(Application, "app-draft-0004")
    version_before = application.baseline_version

    decision = workflow_service.request_transition(
        db, access, application.id, "submit"
    )
    assert decision.accepted is True

    # All four effects are visible from the database after the single call.
    refreshed = db.get(Application, application.id)
    assert refreshed.current_state == "submitted"
    assert refreshed.baseline_version == version_before + 1
    submitted = [
        row for row in _transitions(db, application.id) if row.action == "submit"
    ]
    assert len(submitted) == 1
    scrutiny_holders = [
        row
        for row in _assignments(db, application.id)
        if row.role_name == "scrutiny_officer" and row.revoked_at is None
    ]
    assert scrutiny_holders, "submitting must hand the case to the reviewers"
    accepted = [
        event
        for event in _audit_events(db, application.id)
        if event.action == "workflow.submit" and event.outcome == "accepted"
    ]
    assert len(accepted) == 1
    assert verify_chain(db).ok is True


# ---------------------------------------------------------------------------
# Audit-write failure fails the operation — no partial write
# ---------------------------------------------------------------------------


def test_audit_write_failure_fails_the_transition_and_leaves_no_partial_write(
    db, access_for, monkeypatch
):
    access = access_for("scrutiny@demo.local")
    application = db.get(Application, "app-existing-0003")
    version_before = application.baseline_version
    transitions_before = len(_transitions(db, application.id))
    assignments_before = len(_assignments(db, application.id))
    audit_before = db.scalar(select(func.count()).select_from(AuditEvent))

    def _explode(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit_service.AuditService, "append", _explode)

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        workflow_service.request_transition(
            db, access, application.id, "approve", reason="Scrutiny complete"
        )

    # Production closes the request session on error (core/db.get_db), which
    # rolls the open transaction back; do the same before asserting.
    db.rollback()
    refreshed = db.get(Application, application.id)
    assert refreshed.current_state == "scrutiny"
    assert refreshed.baseline_version == version_before
    assert len(_transitions(db, application.id)) == transitions_before
    assert len(_assignments(db, application.id)) == assignments_before
    assert (
        db.scalar(select(func.count()).select_from(AuditEvent)) == audit_before
    )
    assert verify_chain(db).ok is True


def test_audit_write_failure_fails_the_revert_and_leaves_no_partial_write(
    db, access_for, monkeypatch
):
    scrutiny = access_for("scrutiny@demo.local")
    application = db.get(Application, "app-existing-0003")
    approved = workflow_service.request_transition(
        db, scrutiny, application.id, "approve", reason="Scrutiny complete"
    )
    assert approved.accepted is True

    admin = access_for("admin@demo.local")
    transitions_before = len(_transitions(db, application.id))

    def _explode(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit_service.AuditService, "append", _explode)

    with pytest.raises(RuntimeError, match="audit store unavailable"):
        workflow_service.revert_last_transition(
            db, admin, application.id, reason="Undo by mistake",
            reason_code="RC-SCOPE-ERROR",
        )

    db.rollback()
    refreshed = db.get(Application, application.id)
    assert refreshed.current_state == "approved"
    assert len(_transitions(db, application.id)) == transitions_before
    assert verify_chain(db).ok is True


def test_http_transition_with_a_broken_audit_store_changes_nothing(
    db, client, as_user, monkeypatch
):
    """Same guarantee at the request boundary: 5xx, and the case is untouched."""
    headers = as_user("scrutiny@demo.local")
    application = db.get(Application, "app-existing-0003")
    version_before = application.baseline_version

    def _explode(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit_service.AuditService, "append", _explode)

    # The middleware turns the failure into a 500 — the officer is told the
    # action did not go through, never that it did.
    failed = client.post(
        f"/api/v1/applications/{application.id}/transitions",
        headers=headers,
        json={"action": "approve", "reason": "Scrutiny complete"},
    )
    assert failed.status_code == 500

    db.expire_all()
    refreshed = db.get(Application, application.id)
    assert refreshed.current_state == "scrutiny"
    assert refreshed.baseline_version == version_before
    assert verify_chain(db).ok is True


# ---------------------------------------------------------------------------
# The EVC booking updates ride in the same transaction as the move
# ---------------------------------------------------------------------------


def test_complete_evc_updates_the_case_and_the_visit_together(
    db, client, as_user, access_for
):
    application_id = _evc_case_in_committee_stage(db, client, as_user)

    decision = workflow_service.request_transition(
        db,
        access_for("evc@demo.local"),
        application_id,
        "complete_evc",
        reason="Visit completed on site",
    )
    assert decision.accepted is True

    db.expire_all()
    assert (
        db.get(Application, application_id).current_state == "evc_completed"
    )
    visit = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == application_id)
    ).one()
    assert visit.status == "completed"
    assert verify_chain(db).ok is True


def test_visit_update_failure_rolls_back_the_whole_evc_completion(
    db, client, as_user, access_for, monkeypatch
):
    """A storage failure on the visit row must not leave the case moved.

    Before the boundary fix the transition was committed first and the visit
    update ran in a second transaction: a failure there left the case at
    ``evc_completed`` with the booking still ``scheduled``.
    """
    application_id = _evc_case_in_committee_stage(db, client, as_user)
    audit_before = len(_audit_events(db, application_id))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("visit storage unavailable")

    monkeypatch.setattr(workflow_service, "_complete_evc_visits", _boom)

    with pytest.raises(RuntimeError, match="visit storage unavailable"):
        workflow_service.request_transition(
            db,
            access_for("evc@demo.local"),
            application_id,
            "complete_evc",
            reason="Visit completed on site",
        )

    db.rollback()
    db.expire_all()
    assert (
        db.get(Application, application_id).current_state == "evc_scheduled"
    )
    visit = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == application_id)
    ).one()
    assert visit.status == "scheduled"
    complete_evc_rows = [
        row
        for row in _transitions(db, application_id)
        if row.action == "complete_evc"
    ]
    assert complete_evc_rows == []
    assert len(_audit_events(db, application_id)) == audit_before
    assert verify_chain(db).ok is True


def test_revert_cancels_the_visit_and_moves_the_case_together(
    db, client, as_user, access_for
):
    application_id = _evc_case_in_committee_stage(db, client, as_user)

    decision = workflow_service.revert_last_transition(
        db,
        access_for("regional@demo.local"),
        application_id,
        reason="Booked before the paperwork was complete.",
        reason_code="RC-SCOPE-ERROR",
    )
    assert decision.accepted is True
    assert any("cancelled" in note for note in decision.notes)

    db.expire_all()
    assert db.get(Application, application_id).current_state == "submitted"
    visit = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == application_id)
    ).one()
    assert visit.status == "cancelled"
    assert verify_chain(db).ok is True


def test_visit_cancellation_failure_rolls_back_the_whole_revert(
    db, client, as_user, access_for, monkeypatch
):
    """Same guarantee for undo: the revert and its cancellation are one step."""
    application_id = _evc_case_in_committee_stage(db, client, as_user)
    transitions_before = len(_transitions(db, application_id))
    audit_before = len(_audit_events(db, application_id))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("visit storage unavailable")

    monkeypatch.setattr(workflow_service, "_cancel_visits_on_revert", _boom)

    with pytest.raises(RuntimeError, match="visit storage unavailable"):
        workflow_service.revert_last_transition(
            db,
            access_for("regional@demo.local"),
            application_id,
            reason="Booked before the paperwork was complete.",
            reason_code="RC-SCOPE-ERROR",
        )

    db.rollback()
    db.expire_all()
    assert db.get(Application, application_id).current_state == "evc_scheduled"
    visit = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == application_id)
    ).one()
    assert visit.status == "scheduled"
    assert len(_transitions(db, application_id)) == transitions_before
    assert len(_audit_events(db, application_id)) == audit_before
    assert verify_chain(db).ok is True
