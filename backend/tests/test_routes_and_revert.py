"""The four approval paths, automatic stage movement, and undoing a step."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Application, AuditEvent, EvcVisit, WorkflowTransition
from app.services import deadline_service

NOW_TODAY = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def _routes(client, headers) -> dict:
    return {r["key"]: r for r in client.get("/api/v1/workflow/routes", headers=headers).json()}


def test_the_catalogue_lists_the_four_approval_paths(client, as_user):
    routes = _routes(client, as_user("admin@demo.local"))
    assert set(routes) == {"new_technical", "existing_technical", "evc_only", "evc_sac_shc"}

    # The EVC-only path never mentions scrutiny; the committee path ends at SAC/SHC.
    assert "scrutiny" not in routes["evc_only"]["states"]
    assert "sac_review" in routes["evc_sac_shc"]["states"]


def test_every_route_starts_at_draft_and_ends_in_a_decision(client, as_user):
    routes = _routes(client, as_user("admin@demo.local"))
    for key, route in routes.items():
        assert "draft" in route["states"], key
        assert {"approved", "rejected"} <= set(route["states"]), key


# ---------------------------------------------------------------------------
# Automatic stage movement
# ---------------------------------------------------------------------------


def test_booking_a_visit_moves_the_case_when_the_route_allows_it(db, client, as_user):
    """Scheduling a committee visit should carry the case to the EVC stage."""
    college = as_user("institution@demo.local")
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

    # The regional officer books the visit; on this route that implies the
    # committee stage, so the case moves with the booking.
    officer = as_user("regional@demo.local")
    booked = client.post(
        f"/api/v1/applications/{application_id}/evc/visits",
        headers=officer,
        json={"scheduled_date": "2026-11-05", "venue": "Institute campus"},
    )
    assert booked.status_code == 201
    assert booked.json()["case_advanced_to"] == "evc_scheduled"

    application = db.get(Application, application_id)
    assert application.current_state == "evc_scheduled"

    # The advance is a real, audited workflow step — not a silent field flip.
    actions = list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id == application_id)
            .order_by(AuditEvent.seq)
        )
    )
    assert "workflow.schedule_evc" in actions


def test_booking_does_not_force_a_move_when_the_guards_are_unmet(db, client, as_user):
    """app-second-0002 is still in 'submitted' — schedule_evc needs scrutiny first,
    and an administrator's role is not on the allowed list for that step."""
    headers = as_user("admin@demo.local")

    booked = client.post(
        "/api/v1/applications/app-second-0002/evc/visits",
        headers=headers,
        json={"scheduled_date": "2026-11-05", "venue": "Campus"},
    )
    assert booked.status_code == 201
    assert booked.json()["case_advanced_to"] is None
    assert db.get(Application, "app-second-0002").current_state == "submitted"


# ---------------------------------------------------------------------------
# Revert / undo
# ---------------------------------------------------------------------------


def test_a_step_can_be_undone_with_a_reason(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    moved = client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=headers,
        json={
            "action": "return_for_clarification",
            "reason": "Lease dates do not match the ownership record.",
        },
    )
    assert moved.json()["to_state"] == "returned"

    undone = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "Opened by mistake — the dates were checked and match."},
    )
    assert undone.status_code == 200
    body = undone.json()
    assert body["accepted"] is True
    assert body["action"] == "revert"
    assert body["from_state"] == "returned"
    assert body["to_state"] == "scrutiny"

    assert db.get(Application, "app-main-0001").current_state == "scrutiny"

    # The undone step is marked, not deleted; the undo is a new step on top.
    undone_row = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.action == "return_for_clarification",
            WorkflowTransition.application_id == "app-main-0001",
        )
    ).first()
    assert undone_row.reverted_at is not None
    assert undone_row.reverted_by

    actions = list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id == "app-main-0001")
            .order_by(AuditEvent.seq)
        )
    )
    assert actions[-1] == "workflow.revert"


def test_undoing_needs_a_reason(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=headers,
        json={"action": "return_for_clarification", "reason": "Evidence incomplete."},
    )
    bare = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "   "},
    )
    assert bare.status_code == 200
    assert bare.json()["accepted"] is False
    assert any("reason" in reason for reason in bare.json()["reasons"])
    assert db.get(Application, "app-main-0001").current_state == "returned"


def test_undoing_twice_walks_back_one_step_at_a_time(db, client, as_user):
    headers = as_user("scrutiny@demo.local")
    client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=headers,
        json={"action": "return_for_clarification", "reason": "Evidence incomplete."},
    )

    first = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "Wrong queue."},
    )
    assert first.json()["accepted"] is True
    assert first.json()["to_state"] == "scrutiny"

    # One step at a time: before that was the review being opened.
    second = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "And that was opened by the wrong officer too."},
    )
    assert second.json()["accepted"] is True
    assert second.json()["to_state"] == "submitted"

    # Back to the submission itself — that can be undone too, back to draft.
    third = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "Back to square one."},
    )
    assert third.json()["accepted"] is True
    assert third.json()["to_state"] == "draft"

    # And now there is genuinely nothing left to undo.
    fourth = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "One more."},
    )
    assert fourth.json()["accepted"] is False
    assert any("nothing to undo" in reason for reason in fourth.json()["reasons"])


def _evc_only_case_in_committee_stage(
    client, college_headers, officer_headers
) -> str:
    """Create an EVC-only case, submit it, and book the visit (which carries it
    to the committee stage). Returns the application id."""
    institution = client.get(
        "/api/v1/institutions", headers=college_headers
    ).json()[0]
    created = client.post(
        "/api/v1/applications",
        headers=college_headers,
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
        headers=college_headers,
        json={"action": "submit", "reason": ""},
    )
    booked = client.post(
        f"/api/v1/applications/{application_id}/evc/visits",
        headers=officer_headers,
        json={"scheduled_date": "2026-11-05", "venue": "Campus"},
    )
    assert booked.json()["case_advanced_to"] == "evc_scheduled"
    return application_id


def test_undoing_a_committee_booking_cancels_the_visit(db, client, as_user):
    headers = as_user("regional@demo.local")
    college = as_user("institution@demo.local")
    application_id = _evc_only_case_in_committee_stage(client, college, headers)
    visit = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == application_id)
    ).first()
    assert visit.status == "scheduled"

    undone = client.post(
        f"/api/v1/applications/{application_id}/revert",
        headers=headers,
        json={"reason": "Booked before the paperwork was complete."},
    )
    assert undone.json()["accepted"] is True
    assert undone.json()["to_state"] == "submitted"
    assert any("cancelled" in note for note in undone.json()["notes"])

    db.refresh(visit)
    assert visit.status == "cancelled"
    assert db.get(Application, application_id).current_state == "submitted"


def test_the_college_cannot_undo_an_officer_step(db, client, as_user):
    officer = as_user("scrutiny@demo.local")
    client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=officer,
        json={"action": "return_for_clarification", "reason": "Evidence incomplete."},
    )
    college = as_user("institution@demo.local")
    attempt = client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=college,
        json={"reason": "We do not like this."},
    )
    # The college can see their own case, but holds no transition permission:
    # the refusal names it, and nothing moves.
    assert attempt.status_code == 200
    assert attempt.json()["accepted"] is False
    assert any("permission" in reason for reason in attempt.json()["reasons"])
    assert db.get(Application, "app-main-0001").current_state == "returned"
    # The refused attempt is still audited.
    rejected = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "workflow.revert",
            AuditEvent.outcome == "rejected",
        )
    ).first()
    assert rejected is not None


def test_sweep_and_revert_coexist(db, client, as_user):
    """A reverted case must not produce phantom ageing from the old stage."""
    headers = as_user("scrutiny@demo.local")
    client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=headers,
        json={"action": "return_for_clarification", "reason": "Evidence incomplete."},
    )
    client.post(
        "/api/v1/applications/app-main-0001/evc/visits",
        headers=headers,
        json={"scheduled_date": "2026-11-05", "venue": "Campus"},
    )
    client.post(
        "/api/v1/applications/app-main-0001/revert",
        headers=headers,
        json={"reason": "Not ready."},
    )
    result = deadline_service.sweep(db, NOW_TODAY)
    # The case is back in scrutiny with a fresh state timestamp: the sweep
    # finds nothing new about the visit that no longer applies.
    application = db.get(Application, "app-main-0001")
    assert application.current_state == "scrutiny"
    visit_items = [
        item for item in result.alerts if item["alert_type"] == "evc_visit"
    ]
    assert visit_items == []
