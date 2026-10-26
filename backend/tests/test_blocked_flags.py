"""FR-03 blocked-application flags: five advisory rules, officer clear/hold.

PRD FR-03 (P0): "Flag blocked applications: Closure applicants applying for
other categories; no EoA for 6 years; standalone PGDM/PGCM without full
student data; intake increase during Central/State inquiry; partial approval
of programmes" (APH cl. 2.21f, 2.16.1a, 2.3.1, 2.6e, 2.27). PRD §7:
"Regional officer clears flags ... All pass, or official clears/holds each
flag."

Safety properties under test:

- **Nothing gates anything.** Evaluating flags is a read: no state changes,
  no workflow effect, no "rejected"/"blocked" value anywhere (DEC-0003,
  PRD §0). Only an officer's recorded decision changes a case, and that
  decision is audited.
- **Nothing is guessed.** Every rule's inputs except one are not modelled in
  this repo, so the honest answer for a real case is ``needs_review`` —
  never a confident ``clear``. ``clear`` is only ever returned when a
  *recorded* input provably fails a condition (the rule cannot apply), and
  ``flagged`` only when every input is recorded and matches.
- **Absent data is unknown, never false.** A case with no Table 2.3 items
  must not read as "not an intake increase" (same precedent as
  ``test_sequencing.py``: a single-category case is never blocked by absent
  items).
- **The clause mapping is positional from the PRD's parallel lists** and is
  recorded as Unverified in config, except bf-02 <-> 2.16.1a and bf-04 <->
  cl. 2.6, which the PRD's own text cross-confirms.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import Application, ApplicationItem, AuditEvent, ReadinessFlag
from app.schemas.api import BlockedFlagDecision
from app.services import readiness

PRD_RULES = [
    ("bf-01", "Closure applicants applying for other categories", "2.21f"),
    ("bf-02", "No EoA for 6 years", "2.16.1a"),
    ("bf-03", "Standalone PGDM/PGCM without full student data", "2.3.1"),
    ("bf-04", "Intake increase during Central/State inquiry", "2.6e"),
    ("bf-05", "Partial approval of programmes", "2.27"),
]


def _policy() -> dict:
    return readiness.blocked_flags_policy()


def _app(category_ids: list[str] | None = None) -> Application:
    """A transient case (no DB) carrying optional Table 2.3 items."""
    application = Application(
        id="transient",
        institution_id="transient-inst",
        category="new_technical",
        route_key="new_technical",
        cycle="2027-28",
    )
    for category_id in category_ids or []:
        application.items.append(
            ApplicationItem(category_id=category_id, route="SCR+EVC+AA")
        )
    return application


def _by_id(results: list[dict], flag_id: str) -> dict:
    return next(row for row in results if row["flag_id"] == flag_id)


# ------------------------------------------------------------- the config


def test_the_blocked_flags_section_loads_unverified_and_advisory():
    policy = _policy()
    assert policy["status"] == "unverified"
    assert policy["advisory_only"] is True


def test_it_cites_fr_03_and_all_five_clauses():
    source = _policy()["source"]
    assert "FR-03" in source
    for clause in ("2.21f", "2.16.1a", "2.3.1", "2.6e", "2.27"):
        assert clause in source, f"clause {clause} missing from the source citation"
    assert "clears" in _policy()["source"] or "holds" in _policy()["source"]


def test_it_ships_exactly_the_five_fr_03_rules_with_their_clauses():
    """The PRD's own rule wordings and clause list, positionally mapped."""
    shipped = [(f["flag_id"], f["rule"], f["clause"]) for f in _policy()["flags"]]
    assert shipped == PRD_RULES


def test_the_positional_clause_mapping_caveat_is_written_down():
    """The mapping is an interpretation — it must be labelled, not silent."""
    note = _policy()["clause_mapping_note"]
    assert "position" in note or "parallel" in note
    assert "2.16.1a" in note  # the cross-confirmation the PRD itself gives


def test_every_flag_is_unverified_advisory_and_cites_its_own_clause():
    for flag in _policy()["flags"]:
        assert flag["status"] == "unverified"
        assert flag["advisory_only"] is True
        assert flag["clause"] in flag["source"]
        assert flag["source"].startswith("md/1_PRD.md")


def test_every_flag_declares_inputs_and_a_condition():
    for flag in _policy()["flags"]:
        assert flag["inputs"], f"{flag['flag_id']} declares no inputs"
        assert flag["condition"], f"{flag['flag_id']} declares no condition"
        input_fields = {entry["field"] for entry in flag["inputs"]}
        for conjunct in flag["condition"]:
            assert conjunct["field"] in input_fields, (
                f"{flag['flag_id']} conditions on {conjunct['field']!r} "
                "which is not a declared input"
            )
        for entry in flag["inputs"]:
            assert isinstance(entry["modelled"], bool)
            assert entry["description"]


def test_every_condition_uses_only_the_supported_operators():
    """Config contract: a typo'd operator can never reach evaluation."""
    for flag in _policy()["flags"]:
        for conjunct in flag["condition"]:
            operators = set(conjunct) - {"field"}
            assert operators, f"{flag['flag_id']} conjunct has no operator"
            assert operators <= {"equals", "contains", "gte"}, operators


def test_most_inputs_are_labelled_as_not_modelled():
    """Honesty check: the placeholder inputs must admit what is missing."""
    flags = {f["flag_id"]: f for f in _policy()["flags"]}
    for flag_id in ("bf-01", "bf-02", "bf-03", "bf-05"):
        for entry in flags[flag_id]["inputs"]:
            assert entry["modelled"] is False, (
                f"{flag_id} claims {entry['field']!r} is modelled — integrate "
                "it and flip the flag instead of pretending"
            )


def test_the_decisions_vocabulary_is_cleared_or_held():
    assert set(readiness.decision_vocabulary()) == {"cleared", "held"}


def test_the_decision_schema_accepts_only_that_vocabulary():
    assert BlockedFlagDecision(decision="cleared").decision == "cleared"
    assert BlockedFlagDecision(decision="held").decision == "held"
    for not_a_decision in ("rejected", "blocked", "open", ""):
        with pytest.raises(ValidationError):
            BlockedFlagDecision(decision=not_a_decision)


# ------------------------------------------- evaluation: nothing is guessed


def test_a_real_case_with_nothing_modelled_needs_review_on_all_five():
    """The shipped state: inputs are not recorded, so no flag is guessed."""
    results = readiness.evaluate_blocked_flags(_app())
    assert [row["flag_id"] for row in results] == [f[0] for f in PRD_RULES]
    for row in results:
        assert row["evaluation"] == "needs_review", row
        assert row["state"] == "needs_review"
        assert row["missing_inputs"], row
        assert row["reason"]


def test_the_evaluation_vocabulary_has_no_rejection_and_no_automatic_block():
    results = readiness.evaluate_blocked_flags(_app())
    for row in results:
        assert row["evaluation"] in {"flagged", "clear", "needs_review"}
        assert row["evaluation"] not in {"rejected", "blocked", "pass", "fail"}
        assert row["advisory_only"] is True
        assert row["decision"] is None  # no decision exists until an officer acts


def test_a_case_without_items_is_unknown_not_clear_for_the_inquiry_flag():
    """Absent Table 2.3 items must never read as 'not an intake increase'."""
    row = _by_id(readiness.evaluate_blocked_flags(_app()), "bf-04")
    assert row["evaluation"] == "needs_review"


def test_a_non_intake_case_with_items_is_clear_because_the_rule_cannot_apply():
    """A recorded input provably failing a condition => clear (not guessed)."""
    row = _by_id(
        readiness.evaluate_blocked_flags(_app(["t23-01"])), "bf-04"
    )
    assert row["evaluation"] == "clear"
    assert row["state"] == "clear"


def test_an_intake_case_with_items_still_needs_review_the_inquiry_is_unknown():
    row = _by_id(
        readiness.evaluate_blocked_flags(_app(["t23-09"])), "bf-04"
    )
    assert row["evaluation"] == "needs_review"
    assert "institution.under_central_state_inquiry" in row["missing_inputs"]


def test_missing_inputs_are_named_rather_than_assumed_false():
    row = _by_id(readiness.evaluate_blocked_flags(_app()), "bf-02")
    assert row["evaluation"] == "needs_review"
    assert "institution.consecutive_years_without_eoa" in row["missing_inputs"]


# ------------------------------------- evaluation: the other two branches


SECTION = {
    "status": "unverified",
    "advisory_only": True,
    "flags": [
        {
            "flag_id": "x-01",
            "rule": "synthetic rule",
            "clause": "0.0",
            "source": "test fixture",
            "status": "unverified",
            "advisory_only": True,
            "inputs": [
                {"field": "ctx.a", "modelled": True, "description": "a"},
                {"field": "ctx.b", "modelled": True, "description": "b"},
            ],
            "condition": [
                {"field": "ctx.a", "equals": True},
                {"field": "ctx.b", "equals": True},
            ],
        },
        {
            "flag_id": "x-02",
            "rule": "synthetic contains rule",
            "clause": "0.0",
            "source": "test fixture",
            "status": "unverified",
            "advisory_only": True,
            "inputs": [
                {"field": "ctx.ids", "modelled": True, "description": "ids"},
            ],
            "condition": [{"field": "ctx.ids", "contains": "t23-09"}],
        },
        {
            "flag_id": "x-03",
            "rule": "synthetic gte rule",
            "clause": "0.0",
            "source": "test fixture",
            "status": "unverified",
            "advisory_only": True,
            "inputs": [
                {"field": "ctx.years", "modelled": True, "description": "years"},
            ],
            "condition": [{"field": "ctx.years", "gte": 6}],
        },
    ],
}

# Deliberately broken (unsupported operator) — kept out of SECTION so the
# helpers above can evaluate the whole section without tripping it.
SECTION_BAD_OPERATOR = {
    "status": "unverified",
    "advisory_only": True,
    "flags": [
        {
            "flag_id": "x-04",
            "rule": "synthetic unknown-operator rule",
            "clause": "0.0",
            "source": "test fixture",
            "status": "unverified",
            "advisory_only": True,
            "inputs": [
                {"field": "ctx.a", "modelled": True, "description": "a"},
            ],
            "condition": [{"field": "ctx.a", "lies_about": True}],
        },
    ],
}


def _evaluate(context: dict, flag_id: str) -> str:
    rows = readiness.evaluate_blocked_flags(_app(), cfg=SECTION, context=context)
    return _by_id(rows, flag_id)["evaluation"]


def test_every_recorded_input_matching_is_flagged():
    assert _evaluate({"ctx.a": True, "ctx.b": True}, "x-01") == "flagged"


def test_one_recorded_input_failing_is_clear_even_with_an_unknown_other():
    """3-valued AND: a provably-false conjunct decides alone."""
    assert _evaluate({"ctx.a": False}, "x-01") == "clear"


def test_only_unknowns_is_never_a_clear():
    assert _evaluate({}, "x-01") == "needs_review"
    assert _evaluate({"ctx.a": True}, "x-01") == "needs_review"


def test_the_contains_operator_works_on_recorded_sets():
    assert _evaluate({"ctx.ids": {"t23-09"}}, "x-02") == "flagged"
    assert _evaluate({"ctx.ids": {"t23-01"}}, "x-02") == "clear"
    assert _evaluate({}, "x-02") == "needs_review"


def test_the_gte_operator_works_on_recorded_numbers():
    assert _evaluate({"ctx.years": 6}, "x-03") == "flagged"
    assert _evaluate({"ctx.years": 7}, "x-03") == "flagged"
    assert _evaluate({"ctx.years": 5}, "x-03") == "clear"
    assert _evaluate({}, "x-03") == "needs_review"


def test_an_unsupported_operator_fails_loudly_rather_than_guessing():
    with pytest.raises(ValueError):
        readiness.evaluate_blocked_flags(
            _app(), cfg=SECTION_BAD_OPERATOR, context={"ctx.a": True}
        )


def test_evaluation_writes_nothing_and_is_reproducible(db):
    application = db.get(Application, "app-main-0001")
    before = db.scalar(select(func.count()).select_from(ReadinessFlag))
    first = readiness.evaluate_blocked_flags(application)
    second = readiness.evaluate_blocked_flags(application)
    after = db.scalar(select(func.count()).select_from(ReadinessFlag))
    assert first == second
    assert before == after == 0


# ----------------------------------------------------------- the endpoints


def test_the_regional_officer_sees_all_five_flags(client, as_user):
    """Phase 2 exit check: 'blocked flags visible to Regional officer'."""
    regional = as_user("regional@demo.local")
    res = client.get("/api/v1/applications/app-main-0001/blocked-flags", headers=regional)
    assert res.status_code == 200
    rows = res.json()
    assert [row["flag_id"] for row in rows] == [f[0] for f in PRD_RULES]
    for row in rows:
        assert row["evaluation"] in {"flagged", "clear", "needs_review"}
        assert row["state"] == row["evaluation"]  # no decision yet
        assert row["decision"] is None
        assert row["advisory_only"] is True
        assert row["status"] == "unverified"
        assert row["clause"]


def test_flags_are_readable_but_deciding_requires_officer_rights(client, as_user):
    college = as_user("institution@demo.local")
    read = client.get("/api/v1/applications/app-main-0001/blocked-flags", headers=college)
    assert read.status_code == 200
    decide = client.post(
        "/api/v1/applications/app-main-0001/blocked-flags/bf-01",
        headers=college,
        json={"decision": "cleared", "note": "not a closure applicant"},
    )
    assert decide.status_code == 403


def test_an_officer_clearing_a_flag_persists_and_is_audited(client, as_user, db):
    regional = as_user("regional@demo.local")
    version_before = db.get(Application, "app-main-0001").baseline_version

    res = client.post(
        "/api/v1/applications/app-main-0001/blocked-flags/bf-01",
        headers=regional,
        json={"decision": "cleared", "note": "verified: not a closure applicant"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "cleared"
    assert body["state"] == "cleared"
    assert body["evaluation"] in {"flagged", "clear", "needs_review"}

    # The decision is the officer's, not the evaluation's: GET merges them.
    listed = client.get(
        "/api/v1/applications/app-main-0001/blocked-flags", headers=regional
    ).json()
    bf01 = next(row for row in listed if row["flag_id"] == "bf-01")
    assert bf01["decision"] == "cleared"
    assert bf01["state"] == "cleared"
    assert bf01["note"] == "verified: not a closure applicant"
    others = [row for row in listed if row["flag_id"] != "bf-01"]
    assert all(row["decision"] is None for row in others)

    db.expire_all()
    application = db.get(Application, "app-main-0001")
    assert application.baseline_version == version_before + 1

    events = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "readiness_flag.decided")
    ).all()
    assert len(events) == 1
    assert events[0].outcome == "accepted"
    assert events[0].before["decision"] is None
    assert events[0].after["decision"] == "cleared"
    assert events[0].after["flag_id"] == "bf-01"
    assert events[0].actor_id
    assert events[0].hash and events[0].prev_hash


def test_an_officer_can_hold_a_flag(client, as_user, db):
    regional = as_user("regional@demo.local")
    res = client.post(
        "/api/v1/applications/app-main-0001/blocked-flags/bf-04",
        headers=regional,
        json={"decision": "held", "note": "inquiry status not confirmed"},
    )
    assert res.status_code == 200
    assert res.json()["decision"] == "held"
    assert res.json()["state"] == "held"

    listed = client.get(
        "/api/v1/applications/app-main-0001/blocked-flags", headers=regional
    ).json()
    bf04 = next(row for row in listed if row["flag_id"] == "bf-04")
    assert bf04["state"] == "held"


def test_re_deciding_keeps_one_row_and_audits_both_decisions(client, as_user, db):
    regional = as_user("regional@demo.local")
    url = "/api/v1/applications/app-main-0001/blocked-flags/bf-02"
    first = client.post(
        url, headers=regional, json={"decision": "held", "note": "needs the EoA record"}
    )
    second = client.post(
        url, headers=regional, json={"decision": "cleared", "note": "record checked"}
    )
    assert first.status_code == second.status_code == 200
    assert second.json()["decision"] == "cleared"

    rows = db.scalars(select(ReadinessFlag)).all()
    assert len(rows) == 1  # one decision row per application + flag
    assert rows[0].decision == "cleared"

    events = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "readiness_flag.decided")
    ).all()
    assert len(events) == 2
    assert events[0].after["decision"] == "held"
    assert events[1].before["decision"] == "held"
    assert events[1].after["decision"] == "cleared"


def test_an_unknown_flag_id_is_404_not_a_silent_no_op(client, as_user):
    regional = as_user("regional@demo.local")
    res = client.post(
        "/api/v1/applications/app-main-0001/blocked-flags/bf-99",
        headers=regional,
        json={"decision": "cleared", "note": "does not exist"},
    )
    assert res.status_code == 404
    assert client.get(
        "/api/v1/applications/app-main-0001/blocked-flags", headers=regional
    ).json()


def test_recording_a_rejection_is_a_validation_error(client, as_user):
    """The decision vocabulary has no 'rejected' — FR-02/§0 carry over."""
    regional = as_user("regional@demo.local")
    res = client.post(
        "/api/v1/applications/app-main-0001/blocked-flags/bf-01",
        headers=regional,
        json={"decision": "rejected", "note": "not allowed"},
    )
    assert res.status_code == 422


def test_an_out_of_scope_case_is_hidden_from_a_region_officer(client, as_user):
    """Scope failure is 404, never 403 — record existence must not leak."""
    regional = as_user("regional@demo.local")
    res = client.get(
        "/api/v1/applications/app-second-0002/blocked-flags", headers=regional
    )
    assert res.status_code == 404
