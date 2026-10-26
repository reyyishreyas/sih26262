"""Routing service: Table 2.3 category → ordered stage list (Phase 1.2).

`app/services/routing.py` answers two questions from configuration only:

* what route pattern does a Table 2.3 category use?
* which stages does that pattern run, in order, and which of them are
  conditional?

The stage composition is transcribed from the PRD: §6 defines the four
patterns (SD / SCR / SCR+EVC / SCR+EVC+AA) and §7 the end-to-end flow the
stages come from. Everything here is still **advisory** (Unverified rows,
DEC-0003): no routing answer may block, return or reject an application.

The per-row checks for all 21 categories arrive in task 1.3
(`test_routing_table_2_3.py`); these tests pin the service itself.
"""

from __future__ import annotations

import pytest

from app.services import routing

# The mainline stages, in PRD §7 order, for each pattern from PRD §6.
EXPECTED_STAGES: dict[str, list[str]] = {
    "SD": [
        "readiness",
        "nil_deficiency_report",
        "executive_decision",
        "appeal_window",
        "grant",
    ],
    "SCR": ["readiness", "scrutiny", "executive_decision", "appeal_window", "grant"],
    "SCR+EVC": [
        "readiness",
        "scrutiny",
        "evc",
        "executive_decision",
        "appeal_window",
        "grant",
    ],
    "SCR+EVC+AA": [
        "readiness",
        "scrutiny",
        "evc",
        "shc",
        "executive_decision",
        "appeal_window",
        "grant",
    ],
}


@pytest.mark.parametrize("pattern", sorted(EXPECTED_STAGES))
def test_each_pattern_yields_its_stages_in_order(pattern):
    stages = routing.stages(pattern)
    assert [stage["stage"] for stage in stages] == EXPECTED_STAGES[pattern]


def test_stage_conditions_come_from_the_prd_flow():
    """The 'AA' gate and the appeal window are conditional by definition."""
    by_name = {stage["stage"]: stage for stage in routing.stages("SCR+EVC+AA")}
    # PRD §6: AA = SAC/SHC only if the earlier outcome has deficiencies.
    assert by_name["shc"]["when"] == "if_deficiencies"
    # PRD §7: the appeal window follows the decision (Speaking Order).
    assert by_name["appeal_window"]["when"] == "on_decision"
    assert by_name["scrutiny"]["when"] == "always"
    assert by_name["evc"]["when"] == "always"


def test_sd_has_no_scrutiny_and_scr_has_no_evc_or_shc():
    assert "scrutiny" not in [stage["stage"] for stage in routing.stages("SD")]
    assert "evc" not in [stage["stage"] for stage in routing.stages("SCR")]
    assert "shc" not in [stage["stage"] for stage in routing.stages("SCR")]


def test_every_route_used_by_a_table_2_3_row_has_a_stage_list():
    """The 21 rows and the patterns must not drift apart.

    Every route a row uses must be defined (a row may never point at a
    pattern with no stages), and all four PRD §6 patterns must exist —
    plain SCR+EVC is currently used by no Table 2.3 row (the PRD table has
    only SD, SCR and SCR+EVC+AA rows) but the prototype route table and the
    random-EVC add still need it.
    """
    used = {row["route"] for row in routing.table_2_3_rows()}
    defined = set(routing.route_patterns())
    assert used <= defined, used - defined
    assert defined == set(EXPECTED_STAGES), defined


def test_category_lookup_returns_the_row_and_its_pattern():
    row = routing.category("t23-08")
    assert row["route"] == "SCR"
    assert row["evc_not_applicable"] is True
    assert routing.route_pattern("t23-08") == "SCR"
    assert routing.stages_for_category("t23-08") == routing.stages("SCR")


def test_an_unknown_category_or_pattern_fails_loudly_not_silently():
    with pytest.raises(KeyError):
        routing.category("t23-99")
    with pytest.raises(KeyError):
        routing.route_pattern("t23-99")
    with pytest.raises(KeyError):
        routing.stages("SCR+EVC+AA+???")


def test_routing_reports_itself_as_advisory_until_the_clauses_are_verified():
    assert routing.is_advisory() is True


def test_creating_a_case_audits_its_route_decision(client, db, as_user):
    """Phase 1 exit check: the routing decision is written to the audit trail.

    The route is chosen once, at creation, and the `application.created`
    event carries `route_key` + `category` — so "why is this case on this
    route?" is answerable from the audit trail alone. The per-category
    *stage list* is derived from configuration on read (IMPL-0021) and is
    deliberately not a stored decision.
    """
    from sqlalchemy import select

    from app.models import AuditEvent

    headers = as_user("institution@demo.local")
    institution_id = client.get("/api/v1/institutions", headers=headers).json()[0]["id"]
    created = client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "institution_id": institution_id,
            "category": "existing_technical",
            "route_key": "existing_technical",
        },
    )
    assert created.status_code == 201
    application_id = created.json()["id"]

    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == application_id,
            AuditEvent.action == "application.created",
        )
    )
    assert event is not None
    assert event.after["route_key"] == "existing_technical"
    assert event.after["category"] == "existing_technical"
