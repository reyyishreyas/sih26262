"""Scrutiny result per checklist item and overall (Plan 4.3, FR-14).

PRD FR-14 (line 186): *"Result per checklist item and overall (Nil
Deficiency / Deficiency) with remarks"*, APH cl. 2.4. Phase 4.2 generates the
advisory Annexure-2 checklist; this suite pins down the recording of the
officer's own verdict on its lines and overall.

The safety properties — each one is a way the record could quietly lie:

- **The vocabulary is the PRD's, via configuration** — "nil_deficiency" /
  "deficiency" come from ``aa_gate.scrutiny_results`` (FR-14's wording,
  already carried by the FR-10 gate); nothing here invents a third value.
- **A result cannot attach to a checklist line that does not exist** — the
  category must be recorded on the case and the item must be in that
  category's configured list; an untranscribed list is missing data and is
  refused as "needs review", never accepted as an empty list.
- **The record cannot contradict itself** — overall "nil_deficiency" is
  refused while any item result is "deficiency". The reverse (overall
  "deficiency" with all items clean) is allowed, because a deficiency may
  exist outside the checklist.
- **Recording is never a workflow action** — it moves no case, gates
  nothing, and every recording is audited (DEC-0003).
- **Nothing disappears** — a recorded result whose item no longer exists in
  configuration is kept and flagged, never silently dropped.
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy import select

from app.models import (
    Application,
    ApplicationItem,
    AuditEvent,
    ScrutinyItemResult,
    ScrutinyOverallResult,
    User,
    WorkflowTransition,
)
from app.services import routing, scrutiny_results

EXISTING = "app-existing-0003"  # seeded: existing_technical, scrutiny
DRAFT = "app-draft-0004"  # seeded case with no documents

NIL = "nil_deficiency"
DEFICIENCY = "deficiency"


def _user_id(db, email: str = "scrutiny@demo.local") -> str:
    """`recorded_by` is a real FK to users — no placeholder ids here."""
    return db.scalar(select(User.id).where(User.email == email))


def _record_category(db, app_id: str, category_id: str) -> None:
    db.add(
        ApplicationItem(
            application_id=app_id,
            category_id=category_id,
            route="SCR+EVC+AA",
        )
    )
    db.commit()


# ------------------------------------------------------------- the vocabulary


def test_the_vocabulary_is_the_gates_not_ours():
    """FR-14's own wording, carried by the FR-10 gate configuration."""
    vocabulary = scrutiny_results.result_vocabulary()
    assert vocabulary == routing.aa_gate()["scrutiny_results"]
    assert vocabulary["clean"] == [NIL]
    assert vocabulary["negative"] == [DEFICIENCY]


def test_an_unknown_result_value_is_refused_loudly(db):
    application = db.get(Application, EXISTING)
    try:
        scrutiny_results.record_item_result(
            db,
            application,
            category_id="t23-13",
            item_id="noc_format_2",
            result="approved",
            actor_id="user-x",
        )
    except ValueError as exc:
        assert "unknown scrutiny result" in str(exc)
    else:
        raise AssertionError("an unconfigured result value must be refused")


# --------------------------------------------------------- per-item results


def test_an_item_result_is_recorded_with_remarks(db):
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)

    row = scrutiny_results.record_item_result(
        db,
        application,
        category_id="t23-13",
        item_id="noc_format_2",
        result=DEFICIENCY,
        remarks="NOC names the old campus",
        actor_id=_user_id(db),
    )
    db.commit()

    stored = db.scalars(
        select(ScrutinyItemResult).where(
            ScrutinyItemResult.application_id == EXISTING
        )
    ).all()
    assert len(stored) == 1
    assert stored[0].result == DEFICIENCY
    assert stored[0].remarks == "NOC names the old campus"
    assert stored[0].recorded_by == _user_id(db)
    assert row.item_id == "noc_format_2"


def test_rerecording_updates_the_row_and_keeps_one_line(db):
    """One row per (case, category, item) — a changed mind moves the row."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)

    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="noc_format_2",
        result=DEFICIENCY, remarks="old campus", actor_id=_user_id(db),
    )
    db.commit()
    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="noc_format_2",
        result=NIL, remarks="corrected after review", actor_id=_user_id(db, "regional@demo.local"),
    )
    db.commit()

    stored = db.scalars(
        select(ScrutinyItemResult).where(
            ScrutinyItemResult.application_id == EXISTING
        )
    ).all()
    assert len(stored) == 1
    assert stored[0].result == NIL
    assert stored[0].remarks == "corrected after review"
    assert stored[0].recorded_by == _user_id(db, "regional@demo.local")


def test_a_result_cannot_attach_to_a_category_the_case_does_not_record(db):
    """No ApplicationItem row → no checklist line → no result (needs review)."""
    application = db.get(Application, EXISTING)
    try:
        scrutiny_results.record_item_result(
            db, application,
            category_id="t23-13", item_id="noc_format_2",
            result=NIL, actor_id=_user_id(db),
        )
    except ValueError as exc:
        assert "needs review" in str(exc)
    else:
        raise AssertionError("an unrecorded category must be refused")


def test_a_result_cannot_attach_to_an_item_outside_the_configured_list(db):
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    try:
        scrutiny_results.record_item_result(
            db, application,
            category_id="t23-13", item_id="made_up_line",
            result=NIL, actor_id=_user_id(db),
        )
    except ValueError as exc:
        assert "unknown checklist item" in str(exc)
    else:
        raise AssertionError("an unconfigured item must be refused")


def test_an_untranscribed_list_is_never_accepted_as_empty(db):
    """t23-01's list is not transcribed (§19 Q8) — that is missing data."""
    _record_category(db, EXISTING, "t23-01")
    application = db.get(Application, EXISTING)
    try:
        scrutiny_results.record_item_result(
            db, application,
            category_id="t23-01", item_id="anything",
            result=NIL, actor_id=_user_id(db),
        )
    except ValueError as exc:
        assert "not transcribed" in str(exc)
        assert "needs review" in str(exc)
    else:
        raise AssertionError("an untranscribed list must be refused")


# ---------------------------------------------------------- the overall row


def test_the_overall_result_is_recorded_with_remarks(db):
    application = db.get(Application, EXISTING)
    scrutiny_results.record_overall_result(
        db, application,
        result=DEFICIENCY, remarks="lease does not match the NOC address",
        actor_id=_user_id(db),
    )
    db.commit()

    stored = db.scalars(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == EXISTING
        )
    ).all()
    assert len(stored) == 1
    assert stored[0].result == DEFICIENCY
    assert stored[0].remarks.startswith("lease does not match")


def test_overall_nil_deficiency_is_refused_while_an_item_is_deficient(db):
    """The record cannot contradict itself: Nil means no deficiency anywhere."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="new_site_proof",
        result=DEFICIENCY, remarks="deed names the old site",
        actor_id=_user_id(db),
    )
    db.commit()

    try:
        scrutiny_results.record_overall_result(
            db, application, result=NIL, actor_id=_user_id(db)
        )
    except ValueError as exc:
        assert "contradicts" in str(exc)
        assert "new_site_proof" in str(exc)
    else:
        raise AssertionError("a self-contradictory overall must be refused")
    assert db.scalars(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == EXISTING
        )
    ).first() is None, "the refused overall must not be stored"


def test_overall_deficiency_with_all_items_clean_is_allowed(db):
    """A deficiency may exist outside the checklist — never the other way."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    for item_id in ("noc_format_2", "resolution_format_3", "new_site_proof"):
        scrutiny_results.record_item_result(
            db, application,
            category_id="t23-13", item_id=item_id,
            result=NIL, actor_id=_user_id(db),
        )
    db.commit()

    row = scrutiny_results.record_overall_result(
        db, application,
        result=DEFICIENCY,
        remarks="fire certificate expired — outside the Annexure-2 list",
        actor_id=_user_id(db),
    )
    db.commit()
    assert row.result == DEFICIENCY


def test_overall_nil_deficiency_is_allowed_when_no_item_is_deficient(db):
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    for item_id in ("noc_format_2", "resolution_format_3", "new_site_proof"):
        scrutiny_results.record_item_result(
            db, application,
            category_id="t23-13", item_id=item_id,
            result=NIL, actor_id=_user_id(db),
        )
    db.commit()

    row = scrutiny_results.record_overall_result(
        db, application, result=NIL, remarks="all lines clean", actor_id=_user_id(db)
    )
    db.commit()
    assert row.result == NIL


def test_rerecording_the_overall_result_updates_the_single_row(db):
    application = db.get(Application, EXISTING)
    scrutiny_results.record_overall_result(
        db, application, result=NIL, actor_id=_user_id(db)
    )
    db.commit()
    scrutiny_results.record_overall_result(
        db, application, result=DEFICIENCY, remarks="second look", actor_id=_user_id(db, "regional@demo.local")
    )
    db.commit()

    stored = db.scalars(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == EXISTING
        )
    ).all()
    assert len(stored) == 1
    assert stored[0].result == DEFICIENCY
    assert stored[0].remarks == "second look"


# ------------------------------------------------------------- the read view


def test_the_view_joins_the_checklist_with_the_recorded_results(db):
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="noc_format_2",
        result=DEFICIENCY, remarks="old campus", actor_id=_user_id(db),
    )
    db.commit()

    view = scrutiny_results.results_view(db, application)
    assert view["checklist_status"] == "incomplete"
    by_id = {entry["item_id"]: entry for entry in view["items"]}
    assert by_id["noc_format_2"]["result"] == DEFICIENCY
    assert by_id["noc_format_2"]["remarks"] == "old campus"
    assert by_id["resolution_format_3"]["result"] is None
    assert view["counts"]["items_configured"] == 3
    assert view["counts"]["items_recorded"] == 1
    assert view["counts"]["items_deficiency"] == 1
    assert view["derived_overall"] == DEFICIENCY
    assert view["overall"] is None


def test_the_derived_overall_stays_none_until_every_line_is_decided(db):
    """An undecided overall is never guessed (Master Prompt §2 rule 4)."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="noc_format_2",
        result=NIL, actor_id=_user_id(db),
    )
    db.commit()

    view = scrutiny_results.results_view(db, application)
    assert view["counts"]["items_recorded"] == 1
    assert view["derived_overall"] is None


def test_the_view_composes_the_aa_gate_with_the_recorded_overall(db):
    """FR-10's gate reads the recorded overall result — advisory, never a move."""
    application = db.get(Application, EXISTING)
    assert scrutiny_results.results_view(db, application)["aa_gate"] == "needs_review"

    scrutiny_results.record_overall_result(
        db, application, result=NIL, actor_id=_user_id(db)
    )
    db.commit()
    assert scrutiny_results.results_view(db, application)["aa_gate"] == "closed"

    scrutiny_results.record_overall_result(
        db, application, result=DEFICIENCY, remarks="recheck", actor_id=_user_id(db)
    )
    db.commit()
    assert scrutiny_results.results_view(db, application)["aa_gate"] == "open"


def test_a_result_whose_item_disappeared_is_kept_and_flagged(db):
    """A rule-file edit must never silently erase an officer's judgement."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    db.add(
        ScrutinyItemResult(
            application_id=EXISTING,
            category_id="t23-13",
            item_id="item_removed_from_config",
            result=DEFICIENCY,
            remarks="recorded before the list changed",
            recorded_by=_user_id(db),
        )
    )
    db.commit()

    view = scrutiny_results.results_view(db, application)
    assert view["orphaned_item_results"] == [
        {
            "category_id": "t23-13",
            "item_id": "item_removed_from_config",
            "result": DEFICIENCY,
            "remarks": "recorded before the list changed",
            "recorded_by": _user_id(db),
            "recorded_at": view["orphaned_item_results"][0]["recorded_at"],
        }
    ]
    assert "needs review" in view["note"]


def test_a_case_without_recorded_categories_needs_review(db):
    application = db.get(Application, EXISTING)
    view = scrutiny_results.results_view(db, application)
    assert view["checklist_status"] == "needs_review"
    assert view["items"] == []
    assert view["derived_overall"] is None
    assert view["note"], "the reason must be said out loud, not an empty view"


def test_checking_results_never_moves_the_case(db):
    """Recording is data entry, not a workflow action (DEC-0003)."""
    _record_category(db, EXISTING, "t23-13")
    application = db.get(Application, EXISTING)
    state_before = application.current_state
    version_before = application.baseline_version
    transitions_before = len(
        db.scalars(
            select(WorkflowTransition).where(
                WorkflowTransition.application_id == EXISTING
            )
        ).all()
    )

    scrutiny_results.record_item_result(
        db, application,
        category_id="t23-13", item_id="noc_format_2",
        result=DEFICIENCY, remarks="x", actor_id=_user_id(db),
    )
    scrutiny_results.record_overall_result(
        db, application, result=DEFICIENCY, remarks="x", actor_id=_user_id(db)
    )
    db.commit()
    db.expire_all()

    refreshed = db.get(Application, EXISTING)
    assert refreshed.current_state == state_before
    assert refreshed.baseline_version == version_before
    assert (
        len(
            db.scalars(
                select(WorkflowTransition).where(
                    WorkflowTransition.application_id == EXISTING
                )
            ).all()
        )
        == transitions_before
    )


# ------------------------------------------------------------- the API


def test_the_api_records_item_and_overall_results(client, as_user, db):
    _record_category(db, EXISTING, "t23-13")
    headers = as_user("scrutiny@demo.local")

    item = client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results",
        headers=headers,
        json={
            "category_id": "t23-13",
            "item_id": "noc_format_2",
            "result": "deficiency",
            "remarks": "NOC names the old campus",
        },
    )
    assert item.status_code == status.HTTP_200_OK
    assert item.json()["result"] == "deficiency"

    overall = client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results/overall",
        headers=headers,
        json={"result": "deficiency", "remarks": "one line is deficient"},
    )
    assert overall.status_code == status.HTTP_200_OK
    assert overall.json()["result"] == "deficiency"

    view = client.get(
        f"/api/v1/applications/{EXISTING}/scrutiny-results", headers=headers
    ).json()
    assert view["overall"]["result"] == "deficiency"
    assert view["aa_gate"] == "open"


def test_the_api_refuses_the_contradictory_overall(client, as_user, db):
    _record_category(db, EXISTING, "t23-13")
    headers = as_user("scrutiny@demo.local")
    client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results",
        headers=headers,
        json={
            "category_id": "t23-13",
            "item_id": "new_site_proof",
            "result": "deficiency",
            "remarks": "deed names the old site",
        },
    )
    refused = client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results/overall",
        headers=headers,
        json={"result": "nil_deficiency"},
    )
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "contradicts" in refused.json()["detail"]


def test_every_recording_is_audited(client, as_user, db):
    _record_category(db, EXISTING, "t23-13")
    headers = as_user("scrutiny@demo.local")
    client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results",
        headers=headers,
        json={
            "category_id": "t23-13",
            "item_id": "noc_format_2",
            "result": "deficiency",
            "remarks": "audit me",
        },
    )
    client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results/overall",
        headers=headers,
        json={"result": "deficiency", "remarks": "audit me too"},
    )

    actions = [
        event.action
        for event in db.scalars(
            select(AuditEvent).order_by(AuditEvent.seq)
        ).all()
    ]
    assert "scrutiny.item_result_recorded" in actions
    assert "scrutiny.overall_result_recorded" in actions


def test_the_overall_endpoint_needs_a_token(client):
    assert (
        client.post(
            f"/api/v1/applications/{EXISTING}/scrutiny-results/overall",
            json={"result": "deficiency"},
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )


def test_an_institution_cannot_record_a_scrutiny_result(client, as_user):
    """Recording a verdict is an officer's act, never the applicant's."""
    response = client.post(
        f"/api/v1/applications/{EXISTING}/scrutiny-results",
        headers=as_user("institution@demo.local"),
        json={
            "category_id": "t23-13",
            "item_id": "noc_format_2",
            "result": "nil_deficiency",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_the_results_view_is_scope_filtered(client, as_user):
    """An other-institution case looks absent, never leaked as a result."""
    response = client.get(
        "/api/v1/applications/app-second-0002/scrutiny-results",
        headers=as_user("institution@demo.local"),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
