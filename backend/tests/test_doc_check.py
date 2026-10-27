"""Phase 4.5: the RULE-DOC-01 document pre-check (FR-06).

PRD FR-06 (line 183): *"Confirm Affidavit 2 and DSC-signed docs; list
missing items as deficiency draft"*, APH cl. 2.3.4 as the PRD cites it.
``md/rules.json`` spells the rule out with a four-value outcome vocabulary,
``status: proposed_unverified`` and *"human_review: Required before issuing
a formal deficiency."* This suite pins the properties that could each
quietly turn the pre-check into a lie:

- **The vocabulary is the spec's own, verbatim** — the four outcome labels
  are compared against ``md/rules.json`` so the config and the spec can
  never drift apart.
- **An unverified leg never produces a pass** — DSC verification is a stub
  (``md/2_ARCHITECTURE.md`` line 117) and no signature field exists, so
  that leg answers needs-review on every evaluation, even when the outcome
  reads "PRE-CHECK PASSED".
- **Affidavit 2 is a labelled placeholder** — the upload vocabulary has one
  generic ``affidavit`` type; present is satisfied-but-unconfirmed, absent
  is a definite FR-06 candidate.
- **Staging is a deliberate, audited officer act** that produces DRAFT rows
  only — never issued, never shown to the institution, never moving the
  case (DEC-0003), and idempotent while a live row covers the line.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import status
from sqlalchemy import func, select

from app.models import (
    Application,
    ApplicationItem,
    AuditEvent,
    Deficiency,
    Document,
)
from app.services import doc_check

MAIN = "app-main-0001"        # new_technical, scrutiny, lease/ownership/fire, NO affidavit
EXISTING = "app-existing-0003"  # existing_technical, scrutiny, HAS an affidavit
SECOND = "app-second-0002"    # other institution's case (scope 404); lease_deed only
DRAFT = "app-draft-0004"      # no documents at all

SCRUTINY_EMAIL = "scrutiny@demo.local"
ADMIN_EMAIL = "admin@demo.local"
INSTITUTION_EMAIL = "institution@demo.local"

# The one transcribed Annexure-2 list (Change of Site): 3 lines, whose
# doc_types are `university_noc`, `format_3_resolution` and
# `lease_deed|lease_agreement|ownership_record`.
T23_13 = "t23-13"


# --------------------------------------------------------------- helpers


def _record_category(db, app_id: str, category_id: str = T23_13) -> None:
    db.add(
        ApplicationItem(
            application_id=app_id, category_id=category_id, route="SCR+EVC+AA"
        )
    )
    db.commit()


def _upload(db, app_id: str, doc_type: str, *, rejected: bool = False) -> None:
    application = db.get(Application, app_id)
    db.add(
        Document(
            institution_id=application.institution_id,
            application_id=app_id,
            doc_type=doc_type,
            file_name=f"{doc_type}.pdf",
            content_type="application/pdf",
            file_sha256=f"sha-{doc_type}-{app_id}",
            storage_ref=f"tests/{app_id}/{doc_type}.pdf",
            status="rejected" if rejected else "processed",
        )
    )
    db.commit()


def _evaluate(db, app_id: str = MAIN) -> dict:
    return doc_check.evaluate(db, db.get(Application, app_id))


def _missing_keys(report: dict) -> set[str]:
    return {row["field_name"] for row in report["missing_items"]}


# ------------------------------------------------------------- the config


def test_the_outcome_vocabulary_is_md_rules_json_verbatim():
    """The four labels are the spec's own words, not paraphrases.

    If ``doc_check_policy.json`` and ``md/rules.json`` ever drift, the
    product would print a "pass/fail" wording the rule never authorised.
    """
    spec_path = Path(__file__).resolve().parents[2] / "md" / "rules.json"
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    rule = next(
        row for row in spec["compliance_rules"] if row["rule_id"] == "RULE-DOC-01"
    )
    assert doc_check.config()["outcomes"] == rule["outcomes"]
    assert doc_check.config()["status"] == rule["status"]
    assert doc_check.config()["human_review"] == rule["human_review"]
    assert doc_check.config()["version"] == rule["version"]


def test_the_config_is_labelled_placeholder_and_advisory():
    config = doc_check.config()
    assert config["placeholder"] is True
    assert config["advisory_only"] is True
    assert "FR-06" in config["source"]
    assert "2.3.4" in config["source"]


def test_the_config_records_the_stub_and_the_placeholder_mapping():
    config = doc_check.config()
    # Affidavit 2 cannot be told apart from Affidavits 1/3 here: labelled
    # placeholder, and an affidavit present is NOT a confirmation.
    assert config["affidavit_2"]["doc_types"] == ["affidavit"]
    assert "PLACEHOLDER MAPPING" in config["affidavit_2"]["note"]
    # The DSC leg is a stub: uncheckable, and its only legal answer is
    # needs_review — never passed, never failed.
    assert config["dsc"]["checkable"] is False
    assert config["dsc"]["status_when_unavailable"] == "needs_review"
    assert "stub" in config["dsc"]["note"].lower()


def test_the_precedence_is_labelled_as_prototype_policy():
    config = doc_check.config()
    assert config["outcome_precedence"][0] == "one_or_more_required_documents_missing"
    assert "prototype policy" in config["precedence_note"]


def test_the_unreachable_outcome_is_kept_in_the_vocabulary():
    """PROCESSING FAILED is md/rules.json's own value for an unreadable
    inventory; the local documents table cannot produce it today, so the
    config says so instead of silently dropping the outcome."""
    labels = doc_check.outcome_labels()
    assert labels["document_inventory_unavailable"] == "PROCESSING FAILED"
    assert "not reachable today" in doc_check.config()["inventory_unavailable_note"]


# ------------------------------------------------------------- the legs


def test_a_case_without_an_affidavit_is_a_deficiency_candidate(db):
    """MAIN ships lease/ownership/fire-safety but no affidavit: FR-06's
    named document is missing, so the outcome is a candidate — and the
    untranscribed inventory is reported beside it as needs review."""
    report = _evaluate(db, MAIN)
    assert report["outcome"] == "one_or_more_required_documents_missing"
    assert report["outcome_label"] == "DEFICIENCY CANDIDATE"
    assert "affidavit_2" in _missing_keys(report)
    assert report["needs_review"] is True
    inventory = next(leg for leg in report["legs"] if leg["leg"] == "required_documents")
    assert inventory["status"] == "needs_review"
    affidavit = next(leg for leg in report["legs"] if leg["leg"] == "affidavit_2")
    assert affidavit["status"] == "missing"


def test_an_affidavit_present_is_satisfied_but_unconfirmed(db):
    """EXISTING has an affidavit upload: the leg is satisfied, but the
    prototype cannot confirm it is *Affidavit 2* — so needs_review stays
    true and the rule can only answer REVIEW REQUIRED."""
    report = _evaluate(db, EXISTING)
    affidavit = next(leg for leg in report["legs"] if leg["leg"] == "affidavit_2")
    assert affidavit["status"] == "satisfied"
    assert affidavit["confirmed"] is False
    assert affidavit["needs_review"] is True
    assert "affidavit_2" not in _missing_keys(report)
    assert report["outcome"] == "checklist_unknown_or_route_unverified"
    assert report["outcome_label"] == "REVIEW REQUIRED"


def test_the_dsc_leg_always_needs_review_even_on_a_pass(db):
    """The DSC signature is a stub: it can never be checked, so it can
    never be part of a clean answer."""
    report = _evaluate(db, EXISTING)
    dsc = next(leg for leg in report["legs"] if leg["leg"] == "dsc_signature")
    assert dsc["status"] == "needs_review"
    assert dsc["needs_review"] is True
    assert dsc["checkable"] is False
    assert report["needs_review"] is True


def test_a_transcribed_checklist_names_each_missing_line(db):
    """A t23-13 case with only the lease uploaded: the two other Annexure-2
    lines are named as candidates with stable line keys."""
    _record_category(db, SECOND)
    report = _evaluate(db, SECOND)
    # Two Annexure-2 lines, plus the affidavit (SECOND uploads none).
    assert _missing_keys(report) == {
        "annexure:t23-13:noc_format_2",
        "annexure:t23-13:resolution_format_3",
        "affidavit_2",
    }
    for row in report["missing_items"]:
        if row["field_name"].startswith("annexure:"):
            assert row["title"]
            assert row["explanation"] and row["corrective_action"]
            assert row["existing_deficiency"] is None


def test_a_complete_inventory_and_affidavit_still_needs_review(db):
    """Everything uploaded that can be uploaded: PRE-CHECK PASSED — but
    needs_review stays true (unconfirmed affidavit + stub DSC), so the
    response can never read as a regulatory all-clear."""
    _record_category(db, MAIN)
    _upload(db, MAIN, "university_noc")
    _upload(db, MAIN, "format_3_resolution")  # lease_deed is already seeded
    _upload(db, MAIN, "affidavit")
    report = _evaluate(db, MAIN)
    assert report["outcome"] == "all_required_documents_present"
    assert report["outcome_label"] == "PRE-CHECK PASSED"
    assert report["missing_items"] == []
    assert report["needs_review"] is True
    assert report["human_review"] == doc_check.config()["human_review"]


def test_a_rejected_document_never_satisfies_a_line(db):
    _record_category(db, SECOND)
    _upload(db, SECOND, "university_noc", rejected=True)
    report = _evaluate(db, SECOND)
    assert "annexure:t23-13:noc_format_2" in _missing_keys(report)


def test_a_draft_case_with_nothing_uploaded_lists_everything_it_can(db):
    """DRAFT has no documents and no recorded category: the inventory leg
    is needs-review (never an empty all-clear) while the affidavit leg is
    a definite candidate."""
    report = _evaluate(db, DRAFT)
    assert _missing_keys(report) == {"affidavit_2"}
    assert report["needs_review"] is True


def test_the_check_is_computed_on_read_and_stores_nothing(db):
    application = db.get(Application, MAIN)

    def snapshot() -> tuple:
        def count(model) -> int:
            return db.scalar(select(func.count()).select_from(model))

        return (
            count(Deficiency),
            count(AuditEvent),
            application.baseline_version,
            application.current_state,
        )

    before = snapshot()
    _evaluate(db, MAIN)
    _evaluate(db, MAIN)
    assert snapshot() == before


# ------------------------------------------------------------- staging


def test_staging_creates_a_draft_row_keyed_by_line(db):
    actor = _user_id(db, SCRUTINY_EMAIL)
    application = db.get(Application, MAIN)
    result = doc_check.stage_drafts(db, application, actor)
    db.commit()

    assert [row["field_name"] for row in result["created"]] == ["affidavit_2"]
    assert result["skipped"] == []
    assert result["outcome"] == "one_or_more_required_documents_missing"
    row = db.get(Deficiency, result["created"][0]["deficiency_id"])
    assert row.status == "draft"
    assert row.rule_key == doc_check.RULE_ID
    assert row.field_name == "affidavit_2"
    assert row.created_by == actor


def test_staging_is_idempotent_while_a_live_row_covers_the_line(db):
    actor = _user_id(db, SCRUTINY_EMAIL)
    application = db.get(Application, MAIN)
    first = doc_check.stage_drafts(db, application, actor)
    db.commit()
    second = doc_check.stage_drafts(db, application, actor)
    db.commit()

    assert second["created"] == []
    assert [row["deficiency_id"] for row in second["skipped"]] == [
        row["deficiency_id"] for row in first["created"]
    ]


def test_a_closed_row_does_not_cover_the_line_anymore(db):
    """A past acceptance must not hide a document that has gone missing
    since: only a live (draft/open/addressed) row covers its line."""
    actor = _user_id(db, SCRUTINY_EMAIL)
    application = db.get(Application, MAIN)
    first = doc_check.stage_drafts(db, application, actor)
    db.commit()
    row = db.get(Deficiency, first["created"][0]["deficiency_id"])
    row.status = "closed"
    db.commit()

    again = doc_check.stage_drafts(db, application, actor)
    db.commit()
    assert [c["field_name"] for c in again["created"]] == ["affidavit_2"]
    assert again["created"][0]["deficiency_id"] != first["created"][0]["deficiency_id"]


def test_staging_never_moves_issues_or_leaks_the_case(db):
    """Drafts are officer working notes: the case does not move, the rows
    are not issued, and Phase 4.4's report still answers the institution
    exactly as before."""
    actor = _user_id(db, SCRUTINY_EMAIL)
    application = db.get(Application, MAIN)
    doc_check.stage_drafts(db, application, actor)
    db.commit()

    assert application.current_state == "scrutiny"
    statuses = db.scalars(
        select(Deficiency.status).where(Deficiency.application_id == MAIN)
    ).all()
    assert set(statuses) == {"draft"}

    from app.services import compliance

    view = compliance.report_view(db, application, _now(), include_drafts=False)
    assert view["status"] == "not_issued"
    assert view["deficiencies"] == []


def test_staging_a_transcribed_checklist_stages_every_missing_line(db):
    _record_category(db, SECOND)
    # SECOND belongs to the other institution, so the actor is the admin.
    actor = _user_id(db, ADMIN_EMAIL)
    application = db.get(Application, SECOND)
    result = doc_check.stage_drafts(db, application, actor)
    db.commit()
    assert {row["field_name"] for row in result["created"]} == {
        "annexure:t23-13:noc_format_2",
        "annexure:t23-13:resolution_format_3",
        "affidavit_2",
    }


# ---------------------------------------------------------------- the API


def test_the_check_requires_a_token(client):
    response = client.get(f"/api/v1/applications/{MAIN}/doc-check")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_an_officer_reads_the_check_over_the_api(client, as_user):
    response = client.get(
        f"/api/v1/applications/{MAIN}/doc-check",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["rule_id"] == doc_check.RULE_ID
    assert body["outcome_label"] == "DEFICIENCY CANDIDATE"
    assert body["needs_review"] is True
    assert body["advisory_only"] is True


def test_the_institution_may_read_the_check_but_never_stage(client, as_user):
    read = client.get(
        f"/api/v1/applications/{MAIN}/doc-check",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert read.status_code == status.HTTP_200_OK
    stage = client.post(
        f"/api/v1/applications/{MAIN}/doc-check/drafts",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert stage.status_code == status.HTTP_403_FORBIDDEN


def test_an_officer_stages_drafts_over_the_api_and_it_is_audited(client, as_user, db):
    response = client.post(
        f"/api/v1/applications/{MAIN}/doc-check/drafts",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert [row["field_name"] for row in body["created"]] == ["affidavit_2"]

    event = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "deficiency.doc_check_staged"
        )
    ).first()
    assert event is not None
    assert event.entity_type == "deficiency"
    assert event.entity_id == MAIN

    # Idempotent over the wire too: a second POST stages nothing new.
    again = client.post(
        f"/api/v1/applications/{MAIN}/doc-check/drafts",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert again.status_code == status.HTTP_200_OK
    assert again.json()["created"] == []


def test_the_institution_never_sees_the_staged_drafts(client, as_user):
    client.post(
        f"/api/v1/applications/{MAIN}/doc-check/drafts",
        headers=as_user(SCRUTINY_EMAIL),
    )
    report = client.get(
        f"/api/v1/applications/{MAIN}/deficiency-report",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert report.status_code == status.HTTP_200_OK
    body = report.json()
    assert body["status"] == "not_issued"
    assert body["deficiencies"] == []


def test_the_check_is_scope_filtered(client, as_user):
    """An other-institution case looks absent, never leaked as a check."""
    response = client.get(
        f"/api/v1/applications/{SECOND}/doc-check",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --------------------------------------------------------------- helpers


def _user_id(db, email: str) -> str:
    from app.models import User

    return db.scalar(select(User.id).where(User.email == email))


def _now():
    from app.core.clock import get_clock

    return get_clock().now()
