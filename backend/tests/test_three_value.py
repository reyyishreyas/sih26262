"""Phase 5.4: the three-value model — Extraction / Claim / Master (FR-41).

The plan's 5.4 (line 83) reads: *"`three_value.py`: Extraction / Claim /
Master values, edit reason, RULE-EDIT-01 (FR-41)."* PRD §8 line 140:

  *every field keeps all three* — **Extraction Value** (what the document
  says), **Claim Value** (what the institution confirms/edits), **Master
  Record Value** (AICTE's record). Rules run on the Extraction Value
  only; an edit is flagged, both values kept, a reason required, and an
  edit can never clear a failed rule. Wording stays neutral ("edited
  after extraction").

and RULE-EDIT-01 (`md/rules.json`): *"Preserve original extraction and
store the correction as a separate value with actor, time, reason, and
version. Do not silently overwrite the source extraction."*

What this suite pins down — each is a way the three-value model could
mislead:

* The config is pinned to the PRD's own sentences and to
  `md/rules.json`'s RULE-EDIT-01 (outcomes + human-review line), and it
  admits the **Master Record Value has no source**: `integrated: false`
  with the spec's own caveat — unknown, never guessed.
* An edit **never overwrites the extraction value** — it stores a
  separate claim with actor, time and (required) reason; a missing
  reason is a 400 with *nothing* recorded, never a silent overwrite.
* **An edit can never clear a failed rule**: the rule engine's snapshot
  is byte-identical before and after a claim, because rules read the
  Extraction Value only.
* RULE-EDIT-01 answers in `md/rules.json`'s vocabulary
  (`continue` / `REVIEW REQUIRED`) — a provenance outcome, never a
  pass/fail of the application, and never applicable until a claim that
  actually *differs* exists.
* The API: the institution may confirm/edit its own case's fields
  (403 outside the permission, 404 outside scope), the audit records
  `document.field_claimed`, and wording stays neutral.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import ExtractedField
from app.services import three_value

APP = "app-main-0001"
OTHER_APP = "app-second-0002"
INSTITUTION = "institution@demo.local"
SCRUTINY = "scrutiny@demo.local"
REGIONAL = "regional@demo.local"

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def _spec_rule() -> dict:
    rules = json.loads((REPO_ROOT / "md" / "rules.json").read_text(encoding="utf-8"))

    def walk(node: object) -> dict | None:
        if isinstance(node, dict):
            if node.get("rule_id") == "RULE-EDIT-01":
                return node
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found is not None:
                    return found
        return None

    entry = walk(rules)
    assert entry is not None, "RULE-EDIT-01 not found in md/rules.json"
    return entry


def _field(value: object = "Example Institute of Technology") -> ExtractedField:
    return ExtractedField(document_id="doc-test", field_name="institution", value=value)


# ------------------------------------------------------------- the config


def test_the_config_is_pinned_to_the_prd_and_to_the_spec_rule():
    prd = (REPO_ROOT / "md" / "1_PRD.md").read_text(encoding="utf-8").splitlines()
    fr41 = next(line for line in prd if line.startswith("| FR-41 |"))
    assert "edits flagged with reason" in fr41 and "Extraction/Claim/Master" in fr41
    three_value_line = next(
        line for line in prd if line.startswith("**Three-value model**")
    )
    assert "Rules run on the Extraction Value only" in three_value_line
    assert "an edit can never clear a failed rule" in three_value_line
    assert '"edited after extraction"' in three_value_line

    config = three_value.config()
    assert config["rule_reference"] == "RULE-EDIT-01"
    assert config["status"] == "proposed_unverified"
    assert config["advisory_only"] is True
    # The neutral wording is the PRD's own phrase, kept verbatim.
    assert config["claim"]["edited_label"] == "edited after extraction"
    assert config["claim"]["reason_required_on_edit"] is True

    # Outcome vocabulary and the human-review line are md/rules.json's own.
    spec = _spec_rule()
    assert config["outcomes"] == spec["outcomes"]
    assert config["human_review"] == spec["human_review"]
    assert set(config["outcomes"]) == {
        "complete_provenance",
        "missing_required_reason_or_actor",
    }


def test_the_master_record_slot_admits_no_source_is_integrated():
    """`master` stays unknown with the spec's caveat — never a guess."""
    config = three_value.config()
    master = config["master_source"]
    assert master["integrated"] is False
    assert "if one is actually integrated" in master["note"]

    values = three_value.values(_field())
    assert values["master"] is None
    assert values["master_note"] == master["note"]


# ------------------------------------------------------------- the model


def test_the_model_carries_claim_columns_and_seeded_rows_are_null():
    columns = {column.name: column for column in ExtractedField.__table__.columns}
    assert columns["claim_value"].nullable
    assert columns["claim_reason"].nullable
    assert columns["claimed_by"].nullable
    assert columns["claimed_at"].nullable
    # The extraction column is untouched and still the only `value`.
    assert columns["value"].nullable

    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        rows = session.scalars(
            select(ExtractedField).where(ExtractedField.method == "seed")
        ).all()
        assert rows, "the demo seed must create extracted fields"
        for row in rows:
            assert row.claim_value is None
            assert row.claim_reason is None
            assert row.claimed_by is None
            assert row.claimed_at is None
    finally:
        session.close()


# ------------------------------------------------- the service, no claim


def test_values_reports_the_three_slots_and_a_field_without_a_claim():
    field = _field()
    values = three_value.values(field)
    assert values["extraction"] == "Example Institute of Technology"
    assert values["claim"] is None
    assert values["master"] is None
    assert values["edited"] is False
    assert values["label"] != three_value.config()["claim"]["edited_label"]


def test_rule_edit01_is_not_applicable_until_a_claim_exists():
    result = three_value.rule_edit01(_field())
    assert result["applicable"] is False
    assert result["outcome"] is None
    assert result["label"] is None
    assert result["rule_id"] == "RULE-EDIT-01"


# ------------------------------------------------------------ recording


def test_a_confirmation_stores_the_claim_without_calling_it_an_edit():
    field = _field()
    result = three_value.record_claim(
        field, value="Example Institute of Technology", reason="", actor_id="user-1", at=NOW
    )
    assert result["edited"] is False
    assert result["note"] != three_value.config()["claim"]["edited_label"]
    assert field.claim_value == "Example Institute of Technology"
    assert field.claim_reason is None  # nothing to explain — it agrees
    assert field.claimed_by == "user-1"
    assert field.claimed_at == NOW
    assert field.value == "Example Institute of Technology"  # extraction kept


def test_an_edit_keeps_both_values_and_requires_a_reason():
    field = _field()
    result = three_value.record_claim(
        field,
        value="Example Institute of Technology, Pune",
        reason="address completed from the lease",
        actor_id="user-1",
        at=NOW,
    )
    assert result["edited"] is True
    assert result["note"] == "edited after extraction"  # neutral, PRD wording
    # BOTH values kept, in separate columns — the extraction is not overwritten.
    assert field.value == "Example Institute of Technology"
    assert field.claim_value == "Example Institute of Technology, Pune"
    assert field.claim_reason == "address completed from the lease"
    assert field.claimed_by == "user-1"
    assert field.claimed_at == NOW


def test_an_edit_without_a_reason_is_refused_and_records_nothing():
    field = _field()
    with pytest.raises(HTTPException) as excinfo:
        three_value.record_claim(
            field, value="Completely Different", reason="  ", actor_id="user-1", at=NOW
        )
    assert excinfo.value.status_code == 400
    # Nothing recorded: no half-correction, no silent overwrite.
    assert field.claim_value is None
    assert field.claim_reason is None
    assert field.claimed_by is None
    assert field.claimed_at is None
    assert field.value == "Example Institute of Technology"


# ---------------------------------------------------- RULE-EDIT-01 leg


def test_rule_edit01_says_continue_for_a_fully_provenanced_edit():
    field = _field()
    three_value.record_claim(
        field,
        value="Other value entirely",
        reason="checked against the page",
        actor_id="user-1",
        at=NOW,
    )
    result = three_value.rule_edit01(field)
    assert result["applicable"] is True
    assert result["outcome"] == "complete_provenance"
    assert result["label"] == "continue"  # md/rules.json's own label
    # It is a provenance verdict, not a compliance one: it never says
    # pass/fail/cleared for the application.
    assert result["label"] not in {"pass", "PASS", "clear", "cleared"}


def test_rule_edit01_answers_review_required_when_reason_or_actor_is_missing():
    field = _field()
    three_value.record_claim(
        field, value="Other value entirely", reason="because", actor_id="user-1", at=NOW
    )
    # Simulate a row whose provenance was broken by another path — the API
    # refuses to create one, but the rule must still answer honestly.
    field.claim_reason = None
    result = three_value.rule_edit01(field)
    assert result["applicable"] is True
    assert result["outcome"] == "missing_required_reason_or_actor"
    assert result["label"] == "REVIEW REQUIRED"
    assert result["human_review"]


def test_rule_edit01_is_not_applicable_to_a_confirmation():
    field = _field()
    three_value.record_claim(
        field, value="Example Institute of Technology", reason="", actor_id="user-1", at=NOW
    )
    result = three_value.rule_edit01(field)
    assert result["applicable"] is False
    assert result["outcome"] is None


def test_an_edit_can_never_clear_a_failed_rule(db):
    """PRD line 140: rules run on the Extraction Value only. The snapshot
    the rule engine reads must be identical before and after an edit."""
    from app.models import Application
    from app.services.evidence_service import build_snapshot, latest_document_fields

    field = db.scalars(
        select(ExtractedField).where(ExtractedField.method == "seed").limit(1)
    ).one()
    application = db.get(Application, APP)
    before = build_snapshot(db, application)
    before_docs = latest_document_fields(db, application.id)
    extraction_before = field.value

    three_value.record_claim(
        field,
        value="A claim that disagrees with the document",
        reason="institution says so",
        actor_id="user-inst",
        at=NOW,
    )
    db.flush()

    after = build_snapshot(db, application)
    after_docs = latest_document_fields(db, application.id)
    assert after == before, "a claim changed what the rule engine sees"
    assert after_docs == before_docs
    assert field.value == extraction_before  # extraction untouched
    assert field.claim_value == "A claim that disagrees with the document"


# ------------------------------------------------------------- the API


def _upload_field(client, headers) -> dict:
    from pdf_factory import affidavit_pdf

    upload = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=headers,
        data={"doc_type": "affidavit"},
        files={"file": ("affidavit.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    fields = upload.json()["document"]["fields"]
    assert fields, "the affidavit must yield fields"
    return fields[0]


def test_the_institution_may_confirm_and_edit_and_the_audit_records_it(
    client, as_user, db
):
    institution = as_user(INSTITUTION)
    field = _upload_field(client, institution)
    url = (
        f"/api/v1/applications/{APP}/documents/{field['document_id']}"
        f"/fields/{field['id']}/claim"
    )

    # 1. A confirmation: agrees with the extraction, no edit flagged.
    confirm = client.post(url, headers=institution, json={"value": field["value"]})
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["edited"] is False
    assert body["extraction_value"] == field["value"]
    assert body["rule_edit_01"]["applicable"] is False
    assert body["master_value"] is None and body["master_note"]

    # 2. An edit: both values kept, neutral wording, RULE-EDIT-01 answers.
    edited = client.post(
        url,
        headers=as_user(INSTITUTION),
        json={"value": "Edited by the institution", "reason": "record corrected"},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["edited"] is True
    assert body["note"] == "edited after extraction"
    assert body["extraction_value"] == field["value"]  # extraction never moved
    assert body["claim_value"] == "Edited by the institution"
    assert body["rule_edit_01"]["outcome"] == "complete_provenance"

    # 3. Read back through the API: both values are kept (FR-41).
    listed = client.get(
        f"/api/v1/applications/{APP}/documents", headers=as_user(SCRUTINY)
    )
    document = next(d for d in listed.json() if d["id"] == field["document_id"])
    read_back = next(f for f in document["fields"] if f["id"] == field["id"])
    assert read_back["value"] == field["value"]
    assert read_back["claim_value"] == "Edited by the institution"
    assert read_back["claim_reason"] == "record corrected"
    assert read_back["claimed_by"]
    assert read_back["master_value"] is None

    # 4. The audit records the act (RULE-EDIT-01 inputs: actor, reason).
    audit = client.get(
        f"/api/v1/applications/{APP}/audit", headers=as_user(INSTITUTION)
    )
    actions = [entry["action"] for entry in audit.json()["events"]]
    assert "document.field_claimed" in actions


def test_an_edit_without_a_reason_is_a_400_and_stores_nothing(client, as_user, db):
    field = _upload_field(client, as_user(INSTITUTION))
    url = (
        f"/api/v1/applications/{APP}/documents/{field['document_id']}"
        f"/fields/{field['id']}/claim"
    )
    refused = client.post(
        url, headers=as_user(INSTITUTION), json={"value": "Silent overwrite"}
    )
    assert refused.status_code == 400, refused.text
    assert "reason" in refused.text.lower()

    listed = client.get(
        f"/api/v1/applications/{APP}/documents", headers=as_user(SCRUTINY)
    )
    document = next(d for d in listed.json() if d["id"] == field["document_id"])
    read_back = next(f for f in document["fields"] if f["id"] == field["id"])
    assert read_back["claim_value"] is None
    assert read_back["value"] == field["value"]


def test_a_role_without_the_permission_is_refused_403(client, as_user):
    field = _upload_field(client, as_user(INSTITUTION))
    url = (
        f"/api/v1/applications/{APP}/documents/{field['document_id']}"
        f"/fields/{field['id']}/claim"
    )
    refused = client.post(
        url, headers=as_user(REGIONAL), json={"value": "nope", "reason": "nope"}
    )
    assert refused.status_code == 403
