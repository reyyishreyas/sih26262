"""Escalation chain: L0–L3 roles, the §11 percentage ladder, unassigned rules.

Plan 3.4 builds `escalation_chain.json` + `escalation.py`: the PRD §11
escalation chain (L0 assignee → L1 Regional officer → L2 Regulation Bureau
→ L3 competent authority), the near-limit percentage ladder (70/90/100/125%
of the stage limit), and the "unassigned in queue" rules (Regional after 1
working day, L2 after 3).

Safety properties under test:

- **Thresholds are labelled placeholders, never AICTE rules.** PRD line 12
  records that the §11 operational thresholds (70/90/100/125%, the 1-/3-day
  escalation) are *project proposals*, and §19 Q5 asks who the designated
  authority at each level is, by Region — so the chain and the ladder ship
  as clearly-labelled placeholder configuration (the same pattern as the
  3.3 day counts and the 3.2 reason-code vocabulary).
- **The chain maps ROLES, not invented people.** L1 maps to the
  `regional_officer` role; L2's "Regulation Bureau" has no explicit role in
  the prototype and maps to `supervisory_officer` as a labelled placeholder;
  L3 "competent authority" has **no role at all** and is `unmapped` — it
  resolves to zero recipients rather than inventing an authority (§19 Q5).
- **Nothing is gated.** The escalation snapshot is advisory and read-only:
  it computes a level and a recipient list for display, moves no case,
  changes no state, and writes nothing (DEC-0003).
- **The percentages are relative to the configured stage limit** — the same
  `stage_limits.json` day counts the ageing sweep uses, never a second clock.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from app.models import Alert, Application, AuditEvent, Institution, User
from app.services import alert_service, escalation, working_calendar
from app.services.policy import RULES_DIR, escalation_chain_policy

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)  # Thursday; matches DEMO_NOW

# Seeded cases (see seed.py): region north = Example Institute of Technology,
# region south = Sample Polytechnic College.
MAIN = "app-main-0001"          # scrutiny, assigned, in state 6d, sla 15d
EXISTING = "app-existing-0003"  # scrutiny, assigned, in state 12d, sla 10d
SECOND = "app-second-0002"      # submitted, UNASSIGNED, in state 2d, region south


def _config() -> dict:
    return escalation_chain_policy()


def _chain() -> list[dict]:
    return list(_config()["chain"])


def _levels() -> list[str]:
    return [entry["level"] for entry in _chain()]


def _ladder() -> list[dict]:
    return list(_config()["percentage_thresholds"])


def _user_id(db, email: str) -> str:
    return db.scalar(select(User.id).where(User.email == email))


# ------------------------------------------------------------- the config


def test_the_chain_loads_unverified_and_placeholder():
    config = _config()
    assert config["status"] == "unverified"
    # The chain and its thresholds are project proposals until AICTE answers
    # §19 Q5 — they must never read as verified operational rules.
    assert config["placeholder"] is True


def test_it_cites_the_section_11_table_and_the_project_proposal_caveat():
    source = _config()["source"]
    assert source.startswith("md/1_PRD.md")
    # §11 lines 274-293 hold the escalation table; line 12 records that these
    # operational thresholds are project proposals, not AICTE rules.
    assert "§11" in source
    assert "project proposals" in source or "§19 Q5" in source


def test_the_chain_is_the_ordered_L0_to_L3_from_the_prd():
    assert _levels() == ["L0", "L1", "L2", "L3"]
    labels = [entry["label"] for entry in _chain()]
    # PRD §11 line 274 names the chain: assignee, Regional officer, Regulation
    # Bureau, competent authority.
    assert "Assignee" in labels[0]
    assert "Regional" in labels[1]
    assert "Bureau" in labels[2] or "Regulation" in labels[2]
    assert "authority" in labels[3].lower() or "Competent" in labels[3]


def test_every_chain_entry_has_a_recipient_kind_and_a_source():
    for entry in _chain():
        assert entry["level"]
        assert entry["label"]
        assert entry["recipient_kind"]
        assert entry["source"]  # every entry cites where it comes from


def test_the_percentage_ladder_is_the_prd_70_90_100_125_in_order():
    percents = [entry["percent"] for entry in _ladder()]
    assert percents == [70, 90, 100, 125]
    # Near-limit (70/90) notifies the owner; 100 escalates to L1, 125 to L2.
    levels = [entry["level"] for entry in _ladder()]
    assert levels[0] == levels[1] == "L0"
    assert levels[2] == "L1"
    assert levels[3] == "L2"


def test_the_unassigned_rules_are_1_day_then_3_days():
    rules = _config()["unassigned_in_queue"]
    assert [r["after_working_days"] for r in rules] == [1, 3]
    # "Unassigned in queue | Regional | After 1 working day | L2 after 3 days".
    assert rules[0]["notifies"] == ["L1"]
    assert rules[1]["notifies"] == ["L2"]


def test_L2_maps_to_a_role_as_a_labelled_placeholder():
    """§19 Q5 leaves the designated authority per level/Region open.

    L2's "Regulation Bureau" has no explicit role in the prototype, so it
    maps to `supervisory_officer` and says so — a placeholder, not a claim.
    """
    l2 = next(entry for entry in _chain() if entry["level"] == "L2")
    assert l2["recipient_kind"] == "supervisory_officer"
    assert l2.get("placeholder") is True
    assert l2.get("note")  # explains the placeholder mapping


def test_L3_is_unmapped_because_no_competent_authority_role_exists():
    """The competent authority has no role in the prototype (§19 Q5 open).

    It is `unmapped`, so it resolves to no recipients rather than inventing
    an authority — the honest answer, never a guessed person.
    """
    l3 = next(entry for entry in _chain() if entry["level"] == "L3")
    assert l3["recipient_kind"] == "unmapped"
    assert l3.get("placeholder") is True


def test_the_chain_file_is_readable_json_in_the_rules_dir():
    parsed = json.loads((Path(RULES_DIR) / "escalation_chain.json").read_text())
    assert parsed["chain"]
    assert parsed["percentage_thresholds"]


# ------------------------------------------------- the percentage ladder


def test_below_the_first_threshold_there_is_no_escalation():
    # 40% of the limit (6/15, the seeded main case) is under 70%.
    assert escalation.level_for_percentage(6, 15) is None


def test_70_and_90_percent_notify_the_owner():
    assert escalation.level_for_percentage(11, 15) == "L0"  # ~73%
    assert escalation.level_for_percentage(14, 15) == "L0"  # ~93%


def test_100_percent_escalates_to_L1():
    assert escalation.level_for_percentage(15, 15) == "L1"


def test_125_percent_escalates_to_L2():
    assert escalation.level_for_percentage(19, 15) == "L2"  # ~127%


def test_the_highest_crossed_threshold_wins():
    # 20/15 = 133% clears 70, 90, 100 and 125 — the top of the ladder.
    assert escalation.level_for_percentage(20, 15) == "L2"


def test_a_case_over_the_limit_but_under_125_is_L1():
    """The seeded existing case: 12 days in a 10-day stage = 120%."""
    assert escalation.level_for_percentage(12, 10) == "L1"


def test_a_missing_limit_answers_none_not_a_guess():
    # No configured stage limit (e.g. the compliance cycle) → no percentage.
    assert escalation.level_for_percentage(6, None) is None
    assert escalation.level_for_percentage(6, 0) is None


# -------------------------------------------------- the unassigned rules


def test_unassigned_for_under_a_day_is_not_escalated():
    assert escalation.unassigned_level(0) is None


def test_unassigned_for_one_working_day_notifies_L1():
    assert escalation.unassigned_level(1) == "L1"


def test_unassigned_for_three_working_days_notifies_L2():
    assert escalation.unassigned_level(3) == "L2"
    assert escalation.unassigned_level(5) == "L2"


def test_working_day_arithmetic_skips_weekends():
    # Mon 2026-10-19 → Thu 2026-10-22: Tue, Wed, Thu are 3 working days.
    assert (
        escalation.working_days_between(date(2026, 10, 19), date(2026, 10, 22)) == 3
    )
    # Fri 2026-10-16 → Mon 2026-10-19: only Mon counts (Sat/Sun skipped).
    assert escalation.working_days_between(date(2026, 10, 16), date(2026, 10, 19)) == 1


def test_working_day_arithmetic_uses_the_configured_calendar():
    """The weekend convention comes from calendars.json, never hard-coded."""
    config = dict(working_calendar.calendars())
    # A calendar with no weekend marks every day a working day.
    always = {**config, "weekend_days": []}
    assert (
        escalation.working_days_between(date(2026, 10, 16), date(2026, 10, 19), cfg=always)
        == 3
    )


# ---------------------------------------------------- recipient resolution


def test_L0_resolves_to_the_assigned_officer(db):
    application = db.get(Application, MAIN)
    assert application.assigned_officer_id  # seeded to the scrutiny officer
    assert escalation.recipients_for_level(db, application, "L0") == [
        application.assigned_officer_id
    ]


def test_L1_resolves_to_the_regions_regional_officers(db):
    application = db.get(Application, MAIN)
    institution = db.get(Institution, application.institution_id)
    resolved = escalation.recipients_for_level(db, application, "L1")
    assert resolved == alert_service.regional_officers(db, institution.region_id)
    # The seeded regional officer is scoped to region north.
    assert _user_id(db, "regional@demo.local") in resolved


def test_L2_resolves_to_the_regions_supervisory_officers(db):
    application = db.get(Application, MAIN)
    institution = db.get(Institution, application.institution_id)
    resolved = escalation.recipients_for_level(db, application, "L2")
    assert resolved == alert_service.supervisory_officers(db, institution.region_id)
    # The seeded supervisory officer is scoped to region north.
    assert _user_id(db, "supervisor@demo.local") in resolved


def test_L3_resolves_to_nobody_because_it_is_unmapped(db):
    """No competent-authority role exists (§19 Q5 open) — never invent one."""
    application = db.get(Application, MAIN)
    assert escalation.recipients_for_level(db, application, "L3") == []


def test_an_unknown_level_resolves_to_nobody(db):
    application = db.get(Application, MAIN)
    assert escalation.recipients_for_level(db, application, "L9") == []


# ------------------------------------------------------- the snapshot


def test_the_snapshot_reports_the_percentage_level_and_its_recipients(db):
    """The seeded existing case: 12 days in a 10-day stage = 120% → L1."""
    application = db.get(Application, EXISTING)
    snapshot = escalation.escalation_snapshot(db, application, NOW)
    assert snapshot["stage_limit_days"] == 10
    assert snapshot["days_in_stage"] == 12
    assert snapshot["percent_used"] == 120
    assert snapshot["level"] == "L1"
    assert snapshot["recipients"]  # the region's regional officers
    assert snapshot["placeholder"] is True


def test_the_snapshot_is_advisory_and_writes_nothing(db):
    application = db.get(Application, EXISTING)
    version_before = application.baseline_version
    state_before = application.current_state
    audit_before = db.scalar(select(AuditEvent.id).limit(1))

    escalation.escalation_snapshot(db, application, NOW)
    db.expire_all()

    assert db.get(Application, EXISTING).baseline_version == version_before
    assert db.get(Application, EXISTING).current_state == state_before
    # No audit event was appended — a read-only computation changes nothing.
    assert db.scalar(select(AuditEvent.id).limit(1)) == audit_before


def test_the_snapshot_reports_unassigned_escalation_for_a_queue_case(db):
    """The seeded second case: unassigned, region south, in state 2 days."""
    application = db.get(Application, SECOND)
    assert application.assigned_officer_id is None
    snapshot = escalation.escalation_snapshot(db, application, NOW)
    assert snapshot["unassigned"] is True
    # 2 calendar days in state from Tue 2026-10-20 to Thu 2026-10-22 = 2
    # working days → the 1-day rule fires (L1) but not the 3-day rule.
    assert snapshot["unassigned_working_days"] == 2
    assert snapshot["unassigned_level"] == "L1"


def test_an_assigned_case_is_not_flagged_unassigned(db):
    application = db.get(Application, MAIN)
    snapshot = escalation.escalation_snapshot(db, application, NOW)
    assert snapshot["unassigned"] is False
    assert snapshot["unassigned_level"] is None


def test_a_case_with_no_limit_reports_no_percentage(db):
    """A stage with no configured day count yields no percentage, no level."""
    application = db.get(Application, MAIN)
    # Force a state whose stage has no limit (returned = compliance cycle).
    application.current_state = "returned"
    db.flush()
    snapshot = escalation.escalation_snapshot(db, application, NOW)
    assert snapshot["stage_limit_days"] is None
    assert snapshot["percent_used"] is None
    assert snapshot["level"] is None


def test_the_sweep_carries_the_escalation_level_on_stage_ageing_alerts(db):
    """The §11 level rides the sweep's own clock — no second time source.

    The seeded existing case is 12 days into a 10-day stage (120% → L1), so
    its stage-ageing alert payload records that level alongside sla_days and
    days_in_state. This is additive: the alert set, dedupe keys and
    recipients are unchanged (tested in test_alerts.py).
    """
    from app.services import deadline_service

    deadline_service.sweep(db, NOW)
    alert = db.scalars(
        select(Alert).where(
            Alert.alert_type == "stage_ageing",
            Alert.entity_id == EXISTING,
        )
    ).first()
    assert alert is not None
    assert alert.payload["sla_days"] == 10
    assert alert.payload["days_in_state"] == 12
    assert alert.payload["escalation_level"] == "L1"


# ----------------------------------------------------------- the API


def test_the_escalation_endpoint_is_served_to_signed_in_users(client, as_user):
    body = client.get(
        f"/api/v1/applications/{EXISTING}/escalation",
        headers=as_user("scrutiny@demo.local"),
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["placeholder"] is True
    assert payload["level"] == "L1"
    assert [entry["level"] for entry in payload["chain"]] == ["L0", "L1", "L2", "L3"]


def test_the_escalation_endpoint_needs_a_token(client):
    assert client.get(f"/api/v1/applications/{EXISTING}/escalation").status_code == 401


def test_the_escalation_endpoint_respects_application_scope(client, as_user):
    """The college sees only its own case, never another institution's."""
    headers = as_user("institution@demo.local")
    allowed = client.get(f"/api/v1/applications/{MAIN}/escalation", headers=headers)
    assert allowed.status_code == 200
    denied = client.get(f"/api/v1/applications/{SECOND}/escalation", headers=headers)
    assert denied.status_code in (403, 404)
