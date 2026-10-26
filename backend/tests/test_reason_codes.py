"""FR-28 return/revert: structured reason code + free text, both mandatory.

PRD FR-28 (P0, PS A): "Return/revert to prior stage or institution; reason
code + free text mandatory". PRD §11 (line 297) aggregates "rejections and
returns by reason code", so the code is persisted on the transition row —
a metric computed from free text would be a guess.

Safety properties under test:

- **The PRD's mandate is enforced, the vocabulary is not invented.** The
  PRD never enumerates codes and §19 has no vocabulary question, so the
  code list ships as clearly-labelled placeholder configuration
  (`rules/reason_codes.json`, status unverified) — the same pattern as the
  3.3 placeholder day counts. Validation rejects unknown codes: an officer
  cannot invent a code at the keyboard any more than this repo invents an
  APH clause.
- **Free text stays mandatory.** A code without text is refused (the code
  says *what kind*, the text says *what exactly*), and a text without a
  code is refused on the actions that require one.
- **Nothing else changes.** Actions that are not returns/reverts need no
  code; the code rides along on the already-authorised transition and adds
  no new gate of its own (DEC-0003).
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.models import AuditEvent, WorkflowTransition
from app.services import workflow_service
from app.services.policy import RULES_DIR, reason_codes_policy

RETURN_ACTION = "return_for_clarification"
APP = "app-main-0001"  # seeded case in scrutiny, new_technical route


def _config() -> dict:
    return reason_codes_policy()


def _codes() -> list[dict]:
    return list(_config()["codes"])


def _code_for(applies_to: str) -> str:
    """The first placeholder code valid for the given action kind."""
    for code in _codes():
        if applies_to in code["applies_to"]:
            return code["id"]
    raise AssertionError(f"no placeholder code applies to {applies_to!r}")


def _latest_audit(db) -> AuditEvent | None:
    return db.scalars(
        select(AuditEvent).order_by(AuditEvent.seq.desc())
    ).first()


# ------------------------------------------------------------- the config


def test_the_reason_code_vocabulary_loads_unverified_and_placeholder():
    config = _config()
    assert config["status"] == "unverified"
    # The vocabulary ships as a labelled placeholder until AICTE confirms
    # the official list — it must never read as verified.
    assert config["placeholder"] is True


def test_it_cites_fr_28_and_the_section_11_metric():
    source = _config()["source"]
    assert source.startswith("md/1_PRD.md")
    assert "FR-28" in source
    # The metric that consumes the codes: "rejections and returns by
    # reason code" (§11, line 297) — the reason they are persisted.
    assert "reason code" in source


def test_every_code_has_an_id_a_label_and_an_applies_to_set():
    codes = _codes()
    assert codes, "a mandatory vocabulary cannot be empty"
    seen: set[str] = set()
    for code in codes:
        assert code["id"] and code["id"] not in seen
        seen.add(code["id"])
        assert code["label"]
        # A code is only meaningful for the action kinds that use it.
        assert set(code["applies_to"]) <= {"return", "revert"}
        assert code["applies_to"], "a code must apply somewhere"
        assert code["source"]  # every code cites where it comes from


def test_both_action_kinds_have_at_least_one_valid_code():
    assert _code_for("return")
    assert _code_for("revert")


def test_every_mandated_action_exists_and_requires_a_reason():
    """Cross-config: the mandate list must name real return actions."""
    from app.services.policy import workflow_routes

    mandated = _config()["required_for_actions"]
    assert mandated, "FR-28 mandates codes on returns — the list cannot be empty"
    for route in workflow_routes()["routes"].values():
        for transition in route["transitions"]:
            if transition["action"] in mandated:
                # A mandated action must actually demand free text too —
                # FR-28 requires code AND text together.
                assert transition["requires_reason"] is True
    # Every mandated action must appear on at least one route.
    actions = {
        transition["action"]
        for route in workflow_routes()["routes"].values()
        for transition in route["transitions"]
    }
    assert set(mandated) <= actions


def test_the_vocabulary_file_is_readable_json_in_the_rules_dir():
    raw = (Path(RULES_DIR) / "reason_codes.json").read_text()
    parsed = json.loads(raw)
    assert parsed["codes"]


# ------------------------------------------------- the mandate, in service


def test_returning_without_a_reason_code_is_refused_and_audited(db, access_for):
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, APP, RETURN_ACTION, reason="Documents needed"
    )
    assert decision.accepted is False
    assert any("reason code" in text for text in decision.reasons)
    event = _latest_audit(db)
    assert event is not None
    assert event.outcome == "rejected"


def test_returning_with_an_unknown_code_is_refused_listing_the_valid_codes(
    db, access_for
):
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db,
        access,
        APP,
        RETURN_ACTION,
        reason="Documents needed",
        reason_code="NOT-A-REAL-CODE",
    )
    assert decision.accepted is False
    joined = " ".join(decision.reasons)
    assert "NOT-A-REAL-CODE" in joined
    # The refusal teaches the valid vocabulary rather than just saying no.
    for code in _codes():
        if "return" in code["applies_to"]:
            assert code["id"] in joined


def test_a_code_without_free_text_is_still_refused(db, access_for):
    """The code says what kind; the text says what exactly — both mandatory."""
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, APP, RETURN_ACTION, reason="", reason_code=_code_for("return")
    )
    assert decision.accepted is False
    assert any("reason" in text for text in decision.reasons)


def test_a_valid_code_and_text_are_accepted_and_stored(db, access_for):
    access = access_for("scrutiny@demo.local")
    code = _code_for("return")
    decision = workflow_service.request_transition(
        db,
        access,
        APP,
        RETURN_ACTION,
        reason="Lease scan is illegible on page 2.",
        reason_code=code,
    )
    assert decision.accepted is True

    row = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == APP,
            WorkflowTransition.action == RETURN_ACTION,
        )
    ).first()
    assert row is not None
    assert row.reason_code == code
    assert row.reason  # the free text rides along as before


def test_the_audit_event_carries_the_code(db, access_for):
    access = access_for("scrutiny@demo.local")
    code = _code_for("return")
    workflow_service.request_transition(
        db, access, APP, RETURN_ACTION, reason="Missing annexure.", reason_code=code
    )
    event = _latest_audit(db)
    assert event is not None
    assert event.action == f"workflow.{RETURN_ACTION}"
    assert event.outcome == "accepted"
    assert code in (event.reason or "") or code in str(event.after)


def test_a_non_return_action_needs_no_code(db, access_for):
    """submit is not a return: the code mandate stays scoped to returns."""
    access = access_for("institution@demo.local")
    decision = workflow_service.request_transition(db, access, "app-draft-0004", "submit")
    assert decision.accepted is True
    row = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == "app-draft-0004",
            WorkflowTransition.action == "submit",
        )
    ).first()
    assert row.reason_code is None  # no code supplied, none demanded


def test_rejecting_needs_free_text_but_no_code(db, access_for):
    """FR-28 mandates codes on returns/reverts only — reject keeps its
    mandatory text (route config) and must not start demanding a code."""
    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, APP, "reject", reason="No affidavit on record."
    )
    assert decision.accepted is True
    row = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == APP,
            WorkflowTransition.action == "reject",
        )
    ).first()
    assert row.reason_code is None


# --------------------------------------------------------------- reverting


def test_reverting_without_a_reason_code_is_refused_and_audited(db, access_for):
    access = access_for("scrutiny@demo.local")
    moved = workflow_service.request_transition(
        db,
        access,
        APP,
        RETURN_ACTION,
        reason="Documents needed",
        reason_code=_code_for("return"),
    )
    assert moved.accepted is True

    decision = workflow_service.revert_last_transition(db, access, APP, reason="Oops")
    assert decision.accepted is False
    assert any("reason code" in text for text in decision.reasons)
    event = _latest_audit(db)
    assert event is not None
    assert event.outcome == "rejected"


def test_reverting_with_a_valid_code_is_accepted_and_stored(db, access_for):
    access = access_for("scrutiny@demo.local")
    workflow_service.request_transition(
        db,
        access,
        APP,
        RETURN_ACTION,
        reason="Documents needed",
        reason_code=_code_for("return"),
    )
    code = _code_for("revert")
    decision = workflow_service.revert_last_transition(
        db, access, APP, reason="Opened by mistake.", reason_code=code
    )
    assert decision.accepted is True

    undo_row = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == APP,
            WorkflowTransition.action == "revert",
        )
    ).first()
    assert undo_row is not None
    assert undo_row.reason_code == code


def test_using_a_revert_only_code_on_a_return_is_refused(db, access_for):
    """A code scoped to 'revert' cannot silently satisfy a return."""
    access = access_for("scrutiny@demo.local")
    revert_only = next(
        code["id"] for code in _codes() if code["applies_to"] == ["revert"]
    )
    decision = workflow_service.request_transition(
        db,
        access,
        APP,
        RETURN_ACTION,
        reason="Documents needed",
        reason_code=revert_only,
    )
    assert decision.accepted is False
    assert any("reason code" in text for text in decision.reasons)


# ------------------------------------------------------------------- the API


def test_the_vocabulary_is_served_to_signed_in_users(client, as_user):
    body = client.get(
        "/api/v1/workflow/reason-codes", headers=as_user("scrutiny@demo.local")
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["status"] == "unverified"
    served = {code["id"] for code in payload["codes"]}
    assert served == {code["id"] for code in _codes()}


def test_the_vocabulary_endpoint_needs_a_token(client):
    assert client.get("/api/v1/workflow/reason-codes").status_code == 401


def test_the_transition_api_carries_the_code(client, as_user):
    headers = as_user("scrutiny@demo.local")
    code = _code_for("return")
    moved = client.post(
        f"/api/v1/applications/{APP}/transitions",
        headers=headers,
        json={
            "action": RETURN_ACTION,
            "reason": "Lease scan is illegible.",
            "reason_code": code,
        },
    )
    assert moved.status_code == 200
    assert moved.json()["accepted"] is True


def test_the_api_refuses_a_return_without_a_code(client, as_user):
    headers = as_user("scrutiny@demo.local")
    refused = client.post(
        f"/api/v1/applications/{APP}/transitions",
        headers=headers,
        json={"action": RETURN_ACTION, "reason": "Documents needed"},
    )
    assert refused.status_code == 200  # a recorded refusal, not a crash
    body = refused.json()
    assert body["accepted"] is False
    assert any("reason code" in text for text in body["reasons"])


def test_available_transitions_flag_the_code_requirement(client, as_user):
    """The review UI can see which actions will demand a code before posting."""
    headers = as_user("scrutiny@demo.local")
    rows = client.get(f"/api/v1/applications/{APP}/transitions", headers=headers).json()
    entry = next(row for row in rows if row["action"] == RETURN_ACTION)
    assert entry["requires_reason"] is True
    assert entry["requires_reason_code"] is True
    other = next(row for row in rows if row["action"] == "schedule_evc")
    assert other["requires_reason_code"] is False
