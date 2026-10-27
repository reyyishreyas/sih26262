"""Phase 5.1: document classification for the ingest step (FR-38).

PRD FR-38 (line 222, APH cl. 2.3.4 as cited): *"Accept PDF/scan/DOCX;
classify"*, and the section 8 pipeline step 1 (line 133) names what it must
classify into: *"(EoA letter = master record, Format-2 NOC, Format-3
Resolution, lease, affidavit, other Annexure-2 item)"*.

The safety properties this suite pins down — each is a way a classifier
could quietly become a decision-maker or a liar:

- **The class list is the PRD's own**, compared against the sentence in
  `md/1_PRD.md`, so config and spec can never drift.
- **Classification never changes the recorded type and never blocks** — a
  wrong-looking declaration is flagged as a warning on a 201, never a 4xx.
- **It is honest about evidence**: no readable text => `no_text`, nothing
  matched => `unclassified`, an equal tie => `ambiguous`, file-name-only =>
  needs review. None of those may ever read as a confident label.
- **Phrase lists are labelled placeholders** (the official Format-2/3
  templates do not exist yet — PRD section 19).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import status

from app.adapters.ocr.mock import MockOCRExtractor
from app.services import doc_classifier, ocr_service

APP = "app-main-0001"
INSTITUTION = "institution@demo.local"

# One representative text per class. Each is written the way the document
# would actually read (mixed case, line breaks) so matching has to survive
# normalisation, not just exact lowercase substrings.
SAMPLES = {
    "eoa_letter": (
        "eoa_letter",
        "EXTENSION OF APPROVAL\nApproval letter issued to the institution.",
    ),
    "format_2_noc": (
        "university_noc",
        "Format 2\nNo Objection Certificate from the affiliating university.\n"
        "NOC is granted subject to conditions.",
    ),
    "format_3_resolution": (
        "format_3_resolution",
        "Format 3\nResolution of the Board of Management of the university.",
    ),
    "lease": (
        "lease_deed",
        "REGISTERED LEASE DEED\nLessor: Demo Land Holdings\n"
        "Lessee: Example Institute of Technology",
    ),
    "affidavit": (
        "affidavit",
        "AFFIDAVIT\nSworn on 12 April 2026\nDeponent: Ramesh Kumar",
    ),
}


def _pdf(lines: list[str]) -> bytes:
    from pdf_factory import text_pdf

    return text_pdf([lines])


# ------------------------------------------------------------- the config


def test_the_config_is_labelled_placeholder_and_advisory():
    config = doc_classifier.config()
    assert config["placeholder"] is True
    assert config["advisory_only"] is True
    assert config["status"] == "proposed_unverified"
    assert "FR-38" in config["source"]
    assert "133" in config["source"]  # the PRD sentence that names the classes
    assert "never changes" in config["human_review"]
    assert "never rejects" in config["human_review"]
    assert "templates" in config["note"]  # §19's open Format-2/3 templates


def test_the_class_list_is_the_prd_sentence_verbatim():
    """The six items PRD line 133 names, compared against the spec file."""
    prd_path = Path(__file__).resolve().parents[2] / "md" / "1_PRD.md"
    ingest_line = next(
        line
        for line in prd_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("1. **Ingest**")
    )
    parenthetical = ingest_line.split("classify (", 1)[1].rsplit(")", 1)[0]
    prd_items = {
        item.split(" = ")[0].strip() for item in parenthetical.split(",")
    }
    from_config = {entry["prd_name"] for entry in doc_classifier.classes()}
    from_config.add(doc_classifier.config()["fallback"]["prd_name"])
    assert from_config == prd_items


def test_every_class_carries_phrases_and_a_declared_type_mapping():
    declared_owners: dict[str, str] = {}
    for entry in doc_classifier.classes():
        assert len(entry["phrases"]) >= 2, entry["class_id"]
        assert entry["label"]
        assert entry["declared_doc_types"], entry["class_id"]
        for doc_type in entry["declared_doc_types"]:
            # One upload type may only ever suggest one class, or the
            # agreement check would answer two different ways.
            assert doc_type not in declared_owners, doc_type
            declared_owners[doc_type] = entry["class_id"]


def test_text_evidence_outranks_a_filename():
    matching = doc_classifier.config()["matching"]
    assert matching["text_weight"] > matching["file_name_weight"]


# -------------------------------------------------------- the five classes


def test_each_of_the_five_classes_is_recognised_from_its_text():
    for class_id, (declared, text) in SAMPLES.items():
        result = doc_classifier.classify(
            page_texts=[text], declared_doc_type=declared
        )
        assert result["status"] == "classified", class_id
        assert result["label_id"] == class_id, class_id
        assert result["agrees_with_declared"] is True, class_id
        assert result["needs_review"] is False, class_id
        assert result["evidence"] == "text"
        assert result["hits"][0]["phrases"], class_id


def test_matching_survives_case_and_layout():
    noisy = "aFFidavit\n\nSWORN   before me\nDeponent here"
    result = doc_classifier.classify(page_texts=[noisy], declared_doc_type="affidavit")
    assert result["label_id"] == "affidavit"
    assert result["needs_review"] is False


def test_multi_page_text_is_joined():
    pages = ["Format 3", "Resolution of the Board meets under section 7"]
    result = doc_classifier.classify(page_texts=pages, declared_doc_type="format_3_resolution")
    assert result["label_id"] == "format_3_resolution"
    assert result["agrees_with_declared"] is True


# --------------------------------------------------- honest uncertainty


def test_no_readable_text_answers_no_text_and_needs_review():
    result = doc_classifier.classify(page_texts=[], declared_doc_type="affidavit")
    assert result["status"] == "no_text"
    assert result["label_id"] is None
    assert result["needs_review"] is True
    assert "no readable text" in result["note"]


def test_text_that_matches_nothing_answers_unclassified():
    result = doc_classifier.classify(
        page_texts=["Minutes of the annual meeting held in the college hall."],
        declared_doc_type="affidavit",
    )
    assert result["status"] == "unclassified"
    assert result["label_id"] is None
    assert result["needs_review"] is True
    assert result["note"] == doc_classifier.config()["fallback"]["note"]


def test_an_equal_tie_answers_ambiguous_with_both_candidates():
    # One lease phrase and one affidavit phrase, same weight: the classifier
    # must refuse to pick rather than break the tie by list order.
    result = doc_classifier.classify(
        page_texts=["AFFIDAVIT filed for the lessee of the premises."],
        declared_doc_type="affidavit",
    )
    assert result["status"] == "ambiguous"
    assert result["label_id"] is None
    assert set(result["candidates"]) == {"lease", "affidavit"}
    assert result["needs_review"] is True


def test_the_file_name_alone_never_produces_a_label():
    result = doc_classifier.classify(
        page_texts=[], file_name="affidavit-2.pdf", declared_doc_type="affidavit"
    )
    assert result["status"] == "no_text"
    assert result["label_id"] is None
    assert result["needs_review"] is True
    # The hint is reported as evidence, not promoted to an answer.
    affidavit_hit = next(row for row in result["hits"] if row["class_id"] == "affidavit")
    assert affidavit_hit["signals"] == ["file_name"]
    assert "file name alone" in result["note"]


def test_text_beats_the_file_name_but_still_needs_review():
    result = doc_classifier.classify(
        page_texts=["Minutes of the annual meeting."],
        file_name="affidavit.pdf",
        declared_doc_type="other",
    )
    assert result["status"] == "classified"
    assert result["label_id"] == "affidavit"
    assert result["evidence"] == "file_name"
    assert result["needs_review"] is True
    assert "file name only" in result["note"]
    # The declaration mismatch is reported too — both caveats at once.
    assert "recorded type is unchanged" in result["note"]


# ----------------------------------------------------- declaration checking


def test_a_mismatch_is_flagged_never_corrected():
    result = doc_classifier.classify(
        page_texts=[SAMPLES["affidavit"][1]], declared_doc_type="lease_deed"
    )
    assert result["label_id"] == "affidavit"
    assert result["agrees_with_declared"] is False
    assert result["needs_review"] is True
    assert "lease_deed" in result["mismatch_note"]
    assert "Affidavit" in result["mismatch_note"]
    assert "recorded type is unchanged" in result["mismatch_note"]
    assert result["note"] == result["mismatch_note"]


def test_a_catch_all_declaration_can_still_be_questioned():
    # "other" is the PRD's bucket: predicting a concrete class from the
    # text is exactly the useful flag an officer wants.
    result = doc_classifier.classify(
        page_texts=[SAMPLES["affidavit"][1]], declared_doc_type="other"
    )
    assert result["label_id"] == "affidavit"
    assert result["agrees_with_declared"] is False
    assert result["needs_review"] is True


def test_without_a_declaration_a_text_answer_stands_on_its_own():
    result = doc_classifier.classify(page_texts=[SAMPLES["lease"][1]])
    assert result["label_id"] == "lease"
    assert result["agrees_with_declared"] is None
    assert result["needs_review"] is False


# ------------------------------------------------------------------ the API


def test_an_upload_returns_its_classification(client, as_user):
    response = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user(INSTITUTION),
        data={"doc_type": "affidavit"},
        files={"file": ("affidavit.pdf", _pdf(["AFFIDAVIT", "Sworn on 12 April 2026"]), "application/pdf")},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    classification = body["classification"]
    assert classification["label_id"] == "affidavit"
    assert classification["agrees_with_declared"] is True
    assert classification["needs_review"] is False
    assert classification["advisory_only"] is True
    # No mismatch warning on an honest declaration.
    assert not any("reads more like" in w for w in body["extraction"]["warnings"])


def test_a_mismatch_warns_on_a_201_and_never_blocks(client, as_user):
    """An affidavit declared as a lease deed is still accepted: the warning
    reaches the UI through extraction.warnings; the record is untouched."""
    response = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user(INSTITUTION),
        data={"doc_type": "lease_deed"},
        files={"file": ("affidavit.pdf", _pdf(["AFFIDAVIT", "Sworn on 12 April 2026"]), "application/pdf")},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    classification = body["classification"]
    assert classification["label_id"] == "affidavit"
    assert classification["agrees_with_declared"] is False
    assert classification["needs_review"] is True
    assert any("reads more like" in w for w in body["extraction"]["warnings"])
    # The uploader's declaration survives verbatim — classification changed
    # nothing (DEC-0003: no AI/OCR decision may touch the record).
    assert body["document"]["doc_type"] == "lease_deed"


def test_an_upload_without_readable_text_still_succeeds_and_says_so(client, as_user):
    # The mock reader does not read bytes, so there is no text to classify:
    # the honest answer is "no_text", on a normal 201.
    ocr_service.set_ocr_extractor(MockOCRExtractor())
    try:
        response = client.post(
            f"/api/v1/applications/{APP}/documents",
            headers=as_user(INSTITUTION),
            data={"doc_type": "affidavit"},
            files={"file": ("scan.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        ocr_service.reset_ocr_extractor()
    assert response.status_code == status.HTTP_201_CREATED
    classification = response.json()["classification"]
    assert classification["status"] == "no_text"
    assert classification["label_id"] is None
    assert classification["needs_review"] is True


def test_the_classifier_configuration_is_loadable_as_json():
    """The file a non-programmer edits parses as plain JSON."""
    rules_dir = Path(doc_classifier.__file__).resolve().parents[2] / "rules"
    data = json.loads((rules_dir / "doc_classifier.json").read_text(encoding="utf-8"))
    assert data["classifier_id"] == doc_classifier.config()["classifier_id"]
    assert len(data["classes"]) == 5
