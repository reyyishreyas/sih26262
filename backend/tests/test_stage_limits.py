"""Stage limits: placeholder day counts and per-stage due dates.

Plan 3.3: `stage_limits.json` with **placeholder** day counts, clearly
labelled; per-stage due dates. PRD §19 Q1 asks AICTE for the official
"Target days for Scrutiny, Re-Scrutiny, EVC scheduling, SHC, Executive
Committee" — so the day counts ship as a clearly-labelled placeholder
(the same pattern as the FR-28 reason-code vocabulary), and PRD line 12
records that operational thresholds are project proposals, not AICTE
rules.

Safety properties under test:

- **The counts are labelled placeholders, never verified days.** The
  config loads `unverified` + `placeholder` and cites the open question
  that keeps it a placeholder.
- **Nothing is invented.** Every stage listed must exist in that route's
  own stage graph (cross-config); unmapped-state day counts may only
  name states that route actually defines but no stage owns (today:
  `sac_review`, whose PRD-stage mapping is an open question from 3.1);
  an unknown route or state answers no limit rather than a default.
- **No behaviour change.** The day counts were moved out of
  `workflow_routes.json` unchanged — `policy.stage_sla_days()` must
  answer exactly the values it answered before, for every route and
  state (pinned below), and `workflow_routes.json` must no longer carry
  them (one source of truth).
- **Due dates are computed, never stored.** A per-stage due date is
  derived on read from the active stage's start + the configured days;
  nothing persists a verdict (the same principle as the deadline
  clocks and the FR-03 evaluations).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from app.core.clock import to_utc
from app.models import Application, StageInstance
from app.services import policy, stages
from app.services.policy import RULES_DIR, stage_limits_policy, workflow_routes

ROUTES = ("new_technical", "existing_technical", "evc_only", "evc_sac_shc")

# The values that lived inline in workflow_routes.json before this task,
# pinned so the move provably changes nothing.
PRE_3_3_VALUES = {
    ("new_technical", "submitted"): 5,
    ("new_technical", "scrutiny"): 15,
    ("new_technical", "evc_scheduled"): 30,
    ("new_technical", "evc_completed"): 10,
    ("existing_technical", "submitted"): 5,
    ("existing_technical", "scrutiny"): 10,
    ("evc_only", "submitted"): 5,
    ("evc_only", "evc_scheduled"): 30,
    ("evc_only", "evc_completed"): 10,
    ("evc_sac_shc", "submitted"): 5,
    ("evc_sac_shc", "scrutiny"): 15,
    ("evc_sac_shc", "evc_scheduled"): 30,
    ("evc_sac_shc", "evc_completed"): 10,
    ("evc_sac_shc", "sac_review"): 20,
}


def _limits() -> dict:
    return stage_limits_policy()


# ------------------------------------------------------------- the config


def test_the_limits_load_unverified_and_placeholder():
    config = _limits()
    assert config["status"] == "unverified"
    # The counts are project proposals until AICTE answers §19 Q1 — they
    # must never read as official target days.
    assert config["placeholder"] is True


def test_it_cites_the_open_question_that_keeps_it_a_placeholder():
    source = _limits()["source"]
    assert source.startswith("md/1_PRD.md")
    # §19 Q1 asks for the official target days; until the answer arrives,
    # every number here is a labelled placeholder (PRD line 12: operational
    # thresholds are project proposals, not AICTE rules).
    assert "§19" in source and "Q1" in source


def test_every_route_lists_exactly_the_stages_of_its_stage_graph():
    """Cross-config: the limits may not invent or omit a stage."""
    graph = stages.stage_graph_policy()["routes"]
    for route_key in ROUTES:
        expected = {stage["stage_key"] for stage in graph[route_key]}
        listed = set(_limits()["routes"][route_key])
        assert listed == expected, route_key


def test_day_counts_are_positive_integers_or_explicitly_null():
    for route_key, route in _limits()["routes"].items():
        for stage_key, entry in route.items():
            days = entry["days"]
            if days is None:
                # A null limit must explain itself — never silently absent.
                assert entry.get("note"), f"{route_key}/{stage_key} has no days and no note"
            else:
                assert isinstance(days, int) and days > 0, f"{route_key}/{stage_key}"
            for state, override in entry.get("state_overrides", {}).items():
                assert isinstance(override, int) and override > 0
                assert entry.get("state_overrides_note"), (
                    f"{route_key}/{stage_key} overrides a day count without a note"
                )
                # An override only makes sense for a state the stage owns.
                owned = next(
                    stage
                    for stage in stages.stage_graph_policy()["routes"][route_key]
                    if stage["stage_key"] == stage_key
                )["active_states"]
                assert state in owned, f"{route_key}/{stage_key}/{state}"


def test_unmapped_state_counts_may_only_name_states_no_stage_owns():
    """Cross-config: sac_review's 20 days ride outside the stage list.

    The state exists in the route's transitions but maps to no PRD stage
    (3.1's open mapping question) — its day count must not pretend
    otherwise, and may not name a state the route does not define.
    """
    graph_routes = stages.stage_graph_policy()["routes"]
    transition_states = {
        route_key: {
            transition["from_state"]
            for transition in workflow_routes()["routes"][route_key]["transitions"]
        }
        | {
            transition["to_state"]
            for transition in workflow_routes()["routes"][route_key]["transitions"]
        }
        for route_key in ROUTES
    }
    for route_key, route in _limits()["routes"].items():
        owned_by_stages = {
            state
            for stage in graph_routes[route_key]
            for state in stage["active_states"]
        }
        for state, days in route.get("unmapped_state_days", {}).items():
            assert state in transition_states[route_key], f"{route_key}/{state}"
            assert state not in owned_by_stages, f"{route_key}/{state} has a stage"
            assert isinstance(days, int) and days > 0
    # And the note says why these sit outside the stage list.
    assert _limits().get("unmapped_state_days_note")


def test_the_day_counts_did_not_change_when_they_moved():
    """The relocation out of workflow_routes.json is behaviour-preserving."""
    for (route_key, state), days in PRE_3_3_VALUES.items():
        assert policy.stage_sla_days(route_key, state) == days, (route_key, state)


def test_states_without_a_limit_answer_none_not_a_default():
    # 'returned' (the compliance cycle) has no clock, before or after.
    assert policy.stage_sla_days("new_technical", "returned") is None
    assert policy.stage_sla_days("new_technical", "draft") is None
    assert policy.stage_sla_days("no_such_route", "scrutiny") is None
    assert policy.stage_sla_days("new_technical", "no_such_state") is None


def test_workflow_routes_no_longer_carries_the_day_counts():
    """One source of truth: the limits live in stage_limits.json only."""
    for route in workflow_routes()["routes"].values():
        assert "stage_sla_days" not in route


def test_the_limits_file_is_readable_json_in_the_rules_dir():
    parsed = json.loads((Path(RULES_DIR) / "stage_limits.json").read_text())
    assert parsed["routes"]


# -------------------------------------------------------- per-stage due dates


def _seed_stage(db, app_id: str, stage_key: str, status: str, started_at) -> None:
    db.add(
        StageInstance(
            application_id=app_id,
            stage_key=stage_key,
            sequence=0,
            status=status,
            started_at=started_at,
        )
    )
    db.commit()


def test_the_active_stage_gets_a_due_date_from_its_configured_days(db, clock):
    now = clock.now()
    _seed_stage(db, "app-main-0001", "scrutiny", "active", now)
    application = db.get(Application, "app-main-0001")

    rows = {row["stage_key"]: row for row in stages.due_dates(db, application)}
    scrutiny = rows["scrutiny"]
    assert scrutiny["status"] == "active"
    assert scrutiny["days"] == 15  # new_technical/scrutiny, the placeholder
    assert scrutiny["due_at"] is not None
    # due_at = the stage's start + the configured days (placeholder counts
    # drive a visible clock, exactly as the pre-3.3 state SLA did).
    assert scrutiny["due_at"] == now + timedelta(days=15)
    assert scrutiny["placeholder"] is True


def test_the_due_date_follows_the_state_the_case_is_actually_in(db, clock):
    """The evc stage counts differently for a booked vs a held visit."""
    now = clock.now()
    _seed_stage(db, "app-main-0001", "evc", "active", now)
    application = db.get(Application, "app-main-0001")
    # Seeded case sits in 'scrutiny', not an EVC state: the EVC stage is
    # not the live stage for it, and the override does not apply.
    rows = {row["stage_key"]: row for row in stages.due_dates(db, application)}
    evc = rows["evc"]
    assert evc["days"] == 30  # the stage's base count
    assert evc["due_at"] == now + timedelta(days=30)


def test_pending_and_completed_stages_have_no_due_date(db, clock):
    now = clock.now()
    _seed_stage(db, "app-main-0001", "readiness", "pending", None)
    _seed_stage(db, "app-main-0001", "grant", "completed", now)
    application = db.get(Application, "app-main-0001")

    rows = {row["stage_key"]: row for row in stages.due_dates(db, application)}
    assert rows["readiness"]["due_at"] is None  # the clock starts on entry
    assert rows["grant"]["due_at"] is None  # and stops on completion


def test_a_stage_without_a_limit_has_no_due_date_and_says_so(db, clock):
    now = clock.now()
    _seed_stage(db, "app-main-0001", "compliance_cycle", "active", now)
    application = db.get(Application, "app-main-0001")

    rows = {row["stage_key"]: row for row in stages.due_dates(db, application)}
    cycle = rows["compliance_cycle"]
    assert cycle["days"] is None
    assert cycle["due_at"] is None
    assert cycle["note"]  # the null limit explains itself, per the config test


def test_due_dates_are_computed_on_read_and_store_nothing(db, clock):
    """Derived like everything else: reading twice changes nothing."""
    now = clock.now()
    _seed_stage(db, "app-main-0001", "scrutiny", "active", now)
    application = db.get(Application, "app-main-0001")
    version_before = application.baseline_version
    state_before = application.current_state

    first = stages.due_dates(db, application)
    second = stages.due_dates(db, application)
    assert first == second
    db.expire_all()
    assert db.get(Application, "app-main-0001").baseline_version == version_before
    assert db.get(Application, "app-main-0001").current_state == state_before
    # And no new column was needed: the row keeps only what 3.1 stored.
    scrutiny_row = next(row for row in first if row["stage_key"] == "scrutiny")
    stored = db.get(StageInstance, scrutiny_row["id"])
    assert stored is not None
    # SQLite round-trips naive datetimes; compare through to_utc like the
    # service does, so the assertion is about the instant, not the repr.
    assert to_utc(stored.started_at) == now


def test_every_listed_stage_appears_in_the_due_date_view(db, clock):
    """The view covers the whole stage list, so a dashboard can render it."""
    now = clock.now()
    _seed_stage(db, "app-main-0001", "scrutiny", "active", now)
    application = db.get(Application, "app-main-0001")
    listed = [row["stage_key"] for row in stages.due_dates(db, application)]
    expected = [
        stage["stage_key"]
        for stage in stages.stage_graph_policy()["routes"][application.route_key]
    ]
    assert listed == expected
