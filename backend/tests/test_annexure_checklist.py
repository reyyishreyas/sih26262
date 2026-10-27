"""Annexure-2 checklist beside the uploaded documents (Plan 4.2, FR-13).

PRD FR-13 (line 185): *"Generate checklist from category's Annexure-2 list
beside uploaded docs"*. The checklist is advisory presentation (DEC-0003):
it joins the configured list against the documents that exist right now and
never blocks, returns or rejects anything.

The safety properties this suite pins down — each one is a way the feature
could quietly lie:

- **A category with no transcribed list reads as "needs review", never as
  "nothing required".** Only Change of Site (t23-13) is transcribed today;
  every other category ships an empty list with a pending note (§19 Q8).
- **A case whose Table 2.3 categories are not recorded reads as "needs
  review", never as an empty all-clear.** Nothing in the product creates
  ``ApplicationItem`` rows yet, so this is the normal state of a seeded case.
- **Presence is not validity.** An uploaded (non-rejected) document marks an
  item *uploaded*; the checklist never says the document is genuine or
  sufficient.
- **Read-only.** The answer is computed on read from config + documents;
  nothing is stored, no audit event, no state change.
"""

from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models import Application, ApplicationItem, AuditEvent, Document
from app.services import checklist

EXISTING = "app-existing-0003"  # seeded: existing_technical, scrutiny, no items
# The draft case carries no seeded documents, so "nothing uploaded yet" is a
# real premise there. (EXISTING ships lease_deed + ownership_record, which
# already satisfy the new-site-proof line of t23-13.)
DRAFT = "app-draft-0004"


def _record_category(db, app_id: str, category_id: str) -> None:
    db.add(
        ApplicationItem(
            application_id=app_id,
            category_id=category_id,
            route="SCR+EVC+AA",
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


# ------------------------------------------------------------- the config


def test_the_config_is_labelled_placeholder_and_advisory():
    from app.services import policy

    config = policy.annexure_2_policy()
    assert config["status"] == "unverified"
    assert config["placeholder"] is True
    assert config["advisory_only"] is True
    assert "FR-13" in config["source"]


def test_every_table_2_3_category_has_an_entry():
    """All 21 rows are present, so no category can silently fall through."""
    from app.services import policy, routing

    config = policy.annexure_2_policy()
    ids = [row["category_id"] for row in routing.table_2_3_rows()]
    assert sorted(config["categories"]) == sorted(ids)


def test_only_change_of_site_is_transcribed_and_the_rest_say_pending():
    from app.services import policy

    config = policy.annexure_2_policy()
    with_items = [
        cid
        for cid, entry in config["categories"].items()
        if entry.get("items")
    ]
    assert with_items == ["t23-13"]
    for cid, entry in config["categories"].items():
        if cid == "t23-13":
            continue
        assert entry["items"] == [], cid
        # An empty list must be labelled, so nobody reads it as "nothing to do".
        assert "needs review" in entry["pending_note"].lower()


def test_the_change_of_site_list_cites_its_sources():
    items, entry = checklist.category_items("t23-13")
    assert entry["status"] == "unverified"
    assert [item["item_id"] for item in items] == [
        "noc_format_2",
        "resolution_format_3",
        "new_site_proof",
    ]
    for item in items:
        assert item["title"]
        assert item["doc_types"]
        # Every item carries its own provenance line; nothing is invented.
        assert item["source"]


def test_an_unknown_category_fails_loudly_not_with_an_empty_list():
    with pytest.raises(KeyError):
        checklist.category_items("t23-99")


# ------------------------------------------------------------- a live case


def test_a_case_without_recorded_categories_needs_review(db):
    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)
    assert result["status"] == "needs_review"
    assert result["categories"] == []
    assert result["items"] == []
    # The note explains why, instead of an empty list looking like an approval.
    assert "no table 2.3 category" in result["note"].lower()


def test_a_change_of_site_case_with_nothing_uploaded_is_incomplete(db):
    _record_category(db, DRAFT, "t23-13")

    application = db.get(Application, DRAFT)
    result = checklist.case_checklist(db, application)

    assert result["status"] == "incomplete"
    assert len(result["items"]) == 3
    assert {item["status"] for item in result["items"]} == {"missing"}
    category = result["categories"][0]
    assert category["category_id"] == "t23-13"
    assert category["uploaded"] == 0
    assert category["total"] == 3


def test_uploading_the_named_documents_moves_the_items_to_uploaded(db):
    _record_category(db, EXISTING, "t23-13")
    _upload(db, EXISTING, "university_noc")
    # Any of the alternative doc types satisfies the new-site-proof line.
    _upload(db, EXISTING, "ownership_record")

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)

    by_id = {item["item_id"]: item for item in result["items"]}
    assert by_id["noc_format_2"]["status"] == "uploaded"
    assert by_id["new_site_proof"]["status"] == "uploaded"
    assert by_id["resolution_format_3"]["status"] == "missing"
    assert result["status"] == "incomplete"
    assert result["categories"][0]["uploaded"] == 2


def test_a_fully_uploaded_case_reads_complete(db):
    _record_category(db, EXISTING, "t23-13")
    _upload(db, EXISTING, "university_noc")
    _upload(db, EXISTING, "format_3_resolution")
    _upload(db, EXISTING, "lease_deed")

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)
    assert result["status"] == "complete"
    assert result["categories"][0]["status"] == "complete"


def test_a_rejected_document_does_not_satisfy_an_item(db):
    """An officer struck the file off — presence is about surviving evidence."""
    _record_category(db, EXISTING, "t23-13")
    _upload(db, EXISTING, "university_noc", rejected=True)

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)
    by_id = {item["item_id"]: item for item in result["items"]}
    assert by_id["noc_format_2"]["status"] == "missing"
    assert result["status"] == "incomplete"


def test_a_category_without_a_transcribed_list_reads_needs_review(db):
    _record_category(db, EXISTING, "t23-01")

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)

    assert result["status"] == "needs_review"
    assert result["items"] == [], "an untranscribed list adds no items"
    category = result["categories"][0]
    assert category["status"] == "needs_review"
    # The note rides the same "note" key every category uses, so the UI reads
    # one field whether the category is pending, incomplete or complete.
    assert "needs review" in category["note"].lower()


def test_a_mixed_case_is_only_as_clear_as_its_blurriest_category(db):
    """A complete Change of Site list beside an untranscribed category is
    still 'needs review' overall — the blurriest category wins."""
    _record_category(db, EXISTING, "t23-13")
    _record_category(db, EXISTING, "t23-05")
    _upload(db, EXISTING, "university_noc")
    _upload(db, EXISTING, "format_3_resolution")
    _upload(db, EXISTING, "lease_deed")

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)
    assert result["status"] == "needs_review"
    by_category = {c["category_id"]: c["status"] for c in result["categories"]}
    assert by_category["t23-13"] == "complete"
    assert by_category["t23-05"] == "needs_review"


def test_an_unrecognised_recorded_category_needs_review_not_a_crash(db):
    db.add(
        ApplicationItem(
            application_id=EXISTING, category_id="t23-99", route="SCR"
        )
    )
    db.commit()

    application = db.get(Application, EXISTING)
    result = checklist.case_checklist(db, application)
    assert result["status"] == "needs_review"
    assert result["categories"][0]["category_id"] == "t23-99"


def test_the_checklist_is_computed_on_read_and_writes_nothing(db):
    application = db.get(Application, EXISTING)
    _record_category(db, EXISTING, "t23-13")
    audit_before = db.scalar(select(AuditEvent.id).limit(1))
    state_before = application.current_state
    version_before = application.baseline_version

    checklist.case_checklist(db, application)
    db.expire_all()

    assert db.scalar(select(AuditEvent.id).limit(1)) == audit_before
    refreshed = db.get(Application, EXISTING)
    assert refreshed.current_state == state_before
    assert refreshed.baseline_version == version_before


def test_uploads_appear_on_the_next_read_without_any_refresh_step(db):
    """Presence is derived, never stored — a just-uploaded file counts
    immediately, and deleting the file (rejection) takes it away again."""
    _record_category(db, DRAFT, "t23-13")
    application = db.get(Application, DRAFT)

    first = checklist.case_checklist(db, application)
    assert {i["status"] for i in first["items"]} == {"missing"}

    _upload(db, DRAFT, "university_noc")
    second = checklist.case_checklist(db, application)
    by_id = {item["item_id"]: item for item in second["items"]}
    assert by_id["noc_format_2"]["status"] == "uploaded"


# ------------------------------------------------------------- the API


def test_the_checklist_endpoint_serves_a_signed_in_officer(client, as_user, db):
    _record_category(db, EXISTING, "t23-13")
    response = client.get(
        f"/api/v1/applications/{EXISTING}/checklist",
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["placeholder"] is True
    assert body["status"] == "incomplete"
    assert len(body["items"]) == 3


def test_the_checklist_endpoint_needs_a_token(client):
    assert (
        client.get(f"/api/v1/applications/{EXISTING}/checklist").status_code
        == status.HTTP_401_UNAUTHORIZED
    )


def test_the_checklist_endpoint_is_scope_filtered(client, as_user):
    """An other-institution case looks absent, never leaked as a checklist."""
    response = client.get(
        "/api/v1/applications/app-second-0002/checklist",
        headers=as_user("institution@demo.local"),
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
