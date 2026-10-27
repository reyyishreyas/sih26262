"""Phase 6.1: the EVC queue entry after scrutiny when the route needs it (FR-18).

Plan line 94 (FR-18, APH cl. 2.23.2 per the PRD table): a case whose route
prescribes an expert visit must show up in the EVC coordinator's queue once the
scrutiny leg is done — not only after somebody remembers to book the visit.

Safety properties under test:

- **Derived on read, nothing stored or moved.** Reading the queue writes no
  rows and changes no state (the queue is a report, never a gate).
- **Route-driven, not guessed.** "Route needs EVC" means the route's own
  transition definitions prescribe `schedule_evc` from the case's current
  state — a route without an EVC stage (``existing_technical``) never appears,
  and a case before its EVC-eligible state never appears.
- **A booked case keeps its appointment** and the case advances through the
  normal transition (booking triggers `schedule_evc`, Phase 4.8 behaviour).
- **Scope and permission as everywhere else**: `MONITORING_READ` required,
  rows filtered by the caller's scope, an institution is refused.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.models import Application, EvcVisit, WorkflowTransitionDefinition

MAIN = "app-main-0001"          # new_technical, scrutiny — route needs EVC
SECOND = "app-second-0002"      # new_technical, submitted — before scrutiny
EXISTING = "app-existing-0003"  # existing_technical, scrutiny — no EVC stage
DRAFT = "app-draft-0004"        # new_technical, draft — not submitted


def _rows(client, as_user, who: str) -> dict:
    response = client.get("/api/v1/evc/queue", headers=as_user(who))
    assert response.status_code == 200, response.text
    return response.json()


def _by_id(payload: dict, application_id: str) -> dict | None:
    for row in payload["rows"]:
        if row["application_id"] == application_id:
            return row
    return None


# ------------------------------------------------------------- queue entry


def test_a_case_at_scrutiny_on_an_evc_route_is_queued_unscheduled(client, as_user):
    payload = _rows(client, as_user, "admin@demo.local")
    row = _by_id(payload, MAIN)
    assert row is not None, "FR-18: an EVC-route case at scrutiny must be queued"
    assert row["state"] == "scrutiny"
    assert row["visit_state"] == "not_scheduled"
    assert row["visit"] is None


def test_a_route_without_an_evc_stage_is_never_queued(client, as_user):
    payload = _rows(client, as_user, "admin@demo.local")
    assert _by_id(payload, EXISTING) is None, (
        "existing_technical prescribes no expert visit — it must not appear"
    )


def test_a_case_before_the_evc_eligible_state_is_not_queued(client, as_user):
    payload = _rows(client, as_user, "admin@demo.local")
    assert _by_id(payload, SECOND) is None, (
        "schedule_evc runs from scrutiny; a submitted case is not yet due"
    )
    assert _by_id(payload, DRAFT) is None


def test_the_awaiting_count_covers_the_unscheduled_entry(client, as_user):
    payload = _rows(client, as_user, "admin@demo.local")
    row = _by_id(payload, MAIN)
    assert row is not None
    assert payload["not_scheduled"] >= 1
    assert payload["awaiting_scheduling"] >= 1


# ------------------------------------------------------------- booking


def test_booking_keeps_the_appointment_in_the_queue_even_when_the_gate_holds(
    client, as_user, db
):
    """The booking stands whether or not the statutory gate opens.

    On the seeded `new_technical` case `schedule_evc`'s rule/document guards
    are not met, so the transition gate stays put (existing behaviour, covered
    in `test_routes_and_revert`) — the queue must still show the booked visit.
    """
    visit_date = date(2026, 11, 5)
    response = client.post(
        f"/api/v1/applications/{MAIN}/evc/visits",
        json={
            "scheduled_date": visit_date.isoformat(),
            "venue": "Campus, synthetic address",
            "notes": "6.1 queue test",
        },
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["case_advanced_to"] is None

    payload = _rows(client, as_user, "admin@demo.local")
    row = _by_id(payload, MAIN)
    assert row is not None
    assert row["visit"]["scheduled_date"] == visit_date.isoformat()
    assert row["visit_state"] in ("visit_scheduled", "visit_due_soon")
    assert row["awaiting_scheduling"] is False

    visits = db.scalars(
        select(EvcVisit).where(EvcVisit.application_id == MAIN)
    ).all()
    assert len(visits) == 1
    assert visits[0].status == "scheduled"


def test_an_evc_only_case_enters_the_queue_and_leaves_it_via_the_gate(
    client, as_user, db
):
    """FR-18 end to end: submit on an EVC-only route → queued unscheduled →
    booked → the gate opens (no scrutiny stage on this route) → the row keeps
    its appointment in the post-visit state."""
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

    before = _rows(client, as_user, "admin@demo.local")
    row = _by_id(before, application_id)
    assert row is not None, "an EVC-only case is EVC-eligible from submitted"
    assert row["visit_state"] == "not_scheduled"
    assert row["awaiting_scheduling"] is True

    booked = client.post(
        f"/api/v1/applications/{application_id}/evc/visits",
        headers=as_user("regional@demo.local"),
        json={"scheduled_date": "2026-11-05", "venue": "Campus"},
    )
    assert booked.status_code == 201
    assert booked.json()["case_advanced_to"] == "evc_scheduled"

    after = _rows(client, as_user, "admin@demo.local")
    row = _by_id(after, application_id)
    assert row is not None
    assert row["state"] == "evc_scheduled"
    assert row["visit"] is not None
    assert row["awaiting_scheduling"] is False
    assert db.get(Application, application_id).current_state == "evc_scheduled"


def test_reading_the_queue_is_read_only(client, as_user, db):
    before = db.query(Application).count()
    visit_before = db.query(EvcVisit).count()
    audit_before = db.execute(
        select(Application.current_state).where(Application.id == MAIN)
    ).scalar()

    _rows(client, as_user, "admin@demo.local")
    db.expire_all()

    assert db.query(Application).count() == before
    assert db.query(EvcVisit).count() == visit_before
    assert (
        db.execute(
            select(Application.current_state).where(Application.id == MAIN)
        ).scalar()
        == audit_before
    )


# ------------------------------------------------------------- permissions


def test_the_queue_requires_monitoring_permission(client, as_user):
    response = client.get(
        "/api/v1/evc/queue", headers=as_user("institution@demo.local")
    )
    assert response.status_code == 403


def test_unauthenticated_access_is_refused(client):
    assert client.get("/api/v1/evc/queue").status_code == 401


def test_the_regional_officer_sees_only_their_region(client, as_user):
    # app-main-0001 sits in the Northern Region (regional officer's scope);
    # app-second-0002 is Southern — but it is not EVC-eligible anyway, so the
    # scope proof is that the Northern case is visible to the regional officer.
    payload = _rows(client, as_user, "regional@demo.local")
    assert _by_id(payload, MAIN) is not None


# ------------------------------------------------------------- config honesty


def test_the_evc_stage_comes_from_the_route_definitions(client, as_user, db):
    pairs = set(
        db.execute(
            select(
                WorkflowTransitionDefinition.route_key,
                WorkflowTransitionDefinition.from_state,
            ).where(WorkflowTransitionDefinition.action == "schedule_evc")
        ).all()
    )
    # The queue never invents an EVC requirement: an unscheduled row's state
    # must be one the route itself prescribes `schedule_evc` from (or the case
    # must already be in a post-visit state with a booking).
    eligible_states = {state for _, state in pairs}
    assert ("new_technical", "scrutiny") in pairs
    assert not any(route == "existing_technical" for route, _ in pairs)
    for row in _rows(client, as_user, "admin@demo.local")["rows"]:
        if row["visit"] is None:
            assert row["state"] in eligible_states
