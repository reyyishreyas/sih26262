"""FR-09 stage graph: authorised completion auto-advances the stage list.

PRD FR-09 (P0): "Auto-advance when authorised user marks stage complete"
(PS A). PRD §7 lists the lifecycle stages (Readiness, Routing, Scrutiny /
Re-Scrutiny, Compliance cycle, EVC, SHC, Executive Committee, Appeal,
Grant) and line 20 records that the prototype's workflow states are the
**baseline subset** the PRD stages extend.

Safety properties under test:

- **Stages are derived, never decision-making.** A StageInstance row is a
  record of where an already-authorised transition left the case; the
  stage service never moves a case, gates a transition or changes
  `baseline_version` (DEC-0003, PRD §0: people decide, the system routes).
- **Only authorised completions advance stages.** A refused transition
  (missing permission) changes no stage row.
- **Nothing is invented.** The per-route stage list and each stage's
  state mapping live in `rules/stage_graph.json`; every `active_states`
  entry must be a state that route's own transition config actually
  defines (cross-config test below); stages the prototype state machine
  cannot yet reach (SHC, Appeal, Grant…) ship with empty `active_states`
  and a label, and are never marked completed by a state they were never
  in — a terminal decision completes only stages the case actually
  entered.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app.models import Application, StageInstance, WorkflowTransition
from app.services import stages, workflow_service
from app.services.policy import RULES_DIR, workflow_routes

ROUTES = ("new_technical", "existing_technical", "evc_only", "evc_sac_shc")

# PRD §7 stage keys, in lifecycle order.
PRD_STAGES = [
    "readiness",
    "scrutiny",
    "compliance_cycle",
    "evc",
    "shc",
    "executive_committee",
    "appeal",
    "grant",
]


def _graph() -> dict:
    return stages.stage_graph_policy()


def _rows(db, app_id: str) -> list[StageInstance]:
    return list(
        db.scalars(
            select(StageInstance)
            .where(StageInstance.application_id == app_id)
            .order_by(StageInstance.sequence)
        ).all()
    )


def _by_key(db, app_id: str, stage_key: str) -> StageInstance | None:
    return next((row for row in _rows(db, app_id) if row.stage_key == stage_key), None)


# ------------------------------------------------------------- the config


def test_the_stage_graph_loads_unverified_and_advisory():
    graph = _graph()
    assert graph["status"] == "unverified"
    assert graph["advisory_only"] is True


def test_it_cites_fr_09_and_the_prd_stage_table():
    source = _graph()["source"]
    assert "FR-09" in source
    assert "§7" in source or "7" in source
    assert source.startswith("md/1_PRD.md")


def test_every_route_lists_the_prd_stage_keys_in_order():
    """The PRD's own stage vocabulary, per route, no renamed stages."""
    for route_key in ROUTES:
        shipped = [s["stage_key"] for s in _graph()["routes"][route_key]]
        assert shipped == PRD_STAGES, route_key


def test_every_stage_cites_a_source_and_labels_reachability():
    for route_key in ROUTES:
        for stage in _graph()["routes"][route_key]:
            assert stage["source"], (route_key, stage["stage_key"])
            if not stage["active_states"]:
                # Unreachable in the prototype state machine: say so.
                assert stage.get("note"), (route_key, stage["stage_key"])


def test_no_active_state_is_invented_beyond_the_routes_own_transitions():
    """Cross-config: stage mapping may only use real states of that route."""
    routes = workflow_routes()["routes"]
    for route_key in ROUTES:
        real_states: set[str] = set()
        for transition in routes[route_key]["transitions"]:
            real_states.add(transition["from_state"])
            real_states.add(transition["to_state"])
        for stage in _graph()["routes"][route_key]:
            for state in stage["active_states"]:
                assert state in real_states, (
                    f"{route_key}/{stage['stage_key']} maps state {state!r} "
                    "which that route's transitions never define"
                )


def test_one_stage_owns_each_state_within_a_route():
    """No state may mean two stages are active at once (config contract)."""
    for route_key in ROUTES:
        seen: dict[str, str] = {}
        for stage in _graph()["routes"][route_key]:
            for state in stage["active_states"]:
                assert state not in seen, (route_key, state)
                seen[state] = stage["stage_key"]


def test_the_status_vocabulary_is_pending_active_completed():
    assert set(stages.statuses()) == {"pending", "active", "completed"}


# ------------------------------------- derivation from authorised moves


def test_submit_opens_the_readiness_stage_only(db, access_for):
    access = access_for("institution@demo.local")
    decision = workflow_service.request_transition(
        db, access, "app-draft-0004", "submit"
    )
    assert decision.accepted is True
    rows = _rows(db, "app-draft-0004")
    active = [r for r in rows if r.status == "active"]
    assert [r.stage_key for r in active] == ["readiness"]
    assert active[0].started_at is not None
    assert active[0].completed_at is None
    # The other PRD stages exist as pending records, not silent absences.
    assert {r.stage_key for r in rows} >= {"readiness", "scrutiny", "evc", "grant"}


def test_an_authorised_completion_auto_advances_to_the_next_stage(db, access_for):
    access = access_for("institution@demo.local")
    workflow_service.request_transition(db, access, "app-draft-0004", "submit")
    scrutiny = access_for("scrutiny@demo.local")

    decision = workflow_service.request_transition(
        db, scrutiny, "app-draft-0004", "start_scrutiny"
    )
    assert decision.accepted is True

    readiness = _by_key(db, "app-draft-0004", "readiness")
    assert readiness.status == "completed"
    assert readiness.completed_at is not None
    assert readiness.completed_by == scrutiny.user_id
    scrutiny_stage = _by_key(db, "app-draft-0004", "scrutiny")
    assert scrutiny_stage.status == "active"
    assert scrutiny_stage.started_at is not None


def test_returning_a_case_opens_the_compliance_cycle(db, access_for):
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db,
        access,
        "app-main-0001",
        "return_for_clarification",
        reason="Documents needed",
        reason_code="RC-DOC-MISSING",
    )
    assert decision.accepted is True
    assert _by_key(db, "app-main-0001", "compliance_cycle").status == "active"
    assert _by_key(db, "app-main-0001", "scrutiny").status == "completed"


def test_re_entering_a_stage_keeps_one_row_and_reactivates_it(db, access_for):
    """Re-Scrutiny is the same stage row reactivated, not a duplicate row."""
    scrutiny = access_for("scrutiny@demo.local")
    college = access_for("institution@demo.local")
    workflow_service.request_transition(
        db,
        scrutiny,
        "app-main-0001",
        "return_for_clarification",
        reason="Fix lease",
        reason_code="RC-DOC-MISSING",
    )
    workflow_service.request_transition(db, college, "app-main-0001", "resubmit")
    decision = workflow_service.request_transition(
        db, scrutiny, "app-main-0001", "start_scrutiny"
    )
    assert decision.accepted is True

    rows = _rows(db, "app-main-0001")
    keys = [r.stage_key for r in rows]
    assert len(keys) == len(set(keys)), "one row per application + stage"
    assert _by_key(db, "app-main-0001", "scrutiny").status == "active"
    assert _by_key(db, "app-main-0001", "compliance_cycle").status == "completed"


def test_a_terminal_decision_completes_only_stages_the_case_entered(
    db, access_for
):
    """approved must never mark EVC/Appeal/Grant 'completed' — they never ran."""
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, "app-existing-0003", "approve"
    )
    assert decision.accepted is True

    by_key = {r.stage_key: r for r in _rows(db, "app-existing-0003")}
    assert by_key["readiness"].status == "completed"  # entered at submit (seed)
    assert by_key["scrutiny"].status == "completed"
    for never_entered in ("evc", "shc", "executive_committee", "appeal", "grant"):
        row = by_key[never_entered]
        assert row.status == "pending", never_entered
        assert row.completed_at is None
        assert row.started_at is None


def test_a_refused_transition_changes_no_stage_row(db, access_for):
    college = access_for("institution@demo.local")
    before = [(r.stage_key, r.status) for r in _rows(db, "app-main-0001")]

    decision = workflow_service.request_transition(
        db, college, "app-main-0001", "schedule_evc"
    )
    assert decision.accepted is False  # institution lacks case.transition

    after = [(r.stage_key, r.status) for r in _rows(db, "app-main-0001")]
    assert after == before


def test_a_revert_rewinds_the_stage_graph_with_the_case(db, access_for):
    scrutiny = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db,
        scrutiny,
        "app-main-0001",
        "return_for_clarification",
        reason="Rewind me",
        reason_code="RC-DOC-MISSING",
    )
    assert decision.accepted is True
    assert _by_key(db, "app-main-0001", "compliance_cycle").status == "active"

    undo = workflow_service.revert_last_transition(
        db,
        scrutiny,
        "app-main-0001",
        reason="Visit already held",
        reason_code="RC-SCOPE-ERROR",
    )
    assert undo.accepted is True
    assert _by_key(db, "app-main-0001", "compliance_cycle").status == "pending"
    assert _by_key(db, "app-main-0001", "scrutiny").status == "active"


def test_sync_never_touches_the_case_version_or_state(db, access_for):
    """Stage bookkeeping is not a case action (no baseline_version bump)."""
    access = access_for("scrutiny@demo.local")
    application = db.get(Application, "app-main-0001")
    before_version = application.baseline_version
    before_state = application.current_state
    before_transitions = db.scalar(
        select(func.count()).select_from(WorkflowTransition)
    )

    stages.sync_stage_instances(db, application, actor_id=access.user_id)
    db.expire_all()

    application = db.get(Application, "app-main-0001")
    assert application.baseline_version == before_version
    assert application.current_state == before_state
    assert (
        db.scalar(select(func.count()).select_from(WorkflowTransition))
        == before_transitions
    )


def test_sync_is_idempotent_for_the_same_state(db, access_for):
    access = access_for("scrutiny@demo.local")
    application = db.get(Application, "app-main-0001")
    stages.sync_stage_instances(db, application, actor_id=access.user_id)
    first = [(r.stage_key, r.status) for r in _rows(db, "app-main-0001")]
    stages.sync_stage_instances(db, application, actor_id=access.user_id)
    second = [(r.stage_key, r.status) for r in _rows(db, "app-main-0001")]
    assert first == second


def test_a_case_in_a_state_the_route_never_maps_stays_where_it_is(db, access_for):
    """No mapped stage owns 'draft': sync must not guess an activation."""
    access = access_for("institution@demo.local")
    application = db.get(Application, "app-draft-0004")
    stages.sync_stage_instances(db, application, actor_id=access.user_id)
    rows = _rows(db, "app-draft-0004")
    assert all(row.status == "pending" for row in rows)
    assert all(row.started_at is None for row in rows)


def test_the_graph_file_is_plain_json_in_the_rules_directory():
    path = Path(RULES_DIR) / "stage_graph.json"
    data = json.loads(path.read_text())
    assert set(data["routes"]) == set(ROUTES)
