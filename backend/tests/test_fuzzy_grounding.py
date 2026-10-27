"""Phase 5.3: fuzzy grounding — a model value counts only if found on the page.

The plan's 5.3 (line 82) reads: *"`fuzzy_grounding.py`: model value must
match OCR words on page else `REVIEW_REQUIRED` (FR-40)."* PRD §8 step 3
(line 135) says it plainly: *"a model value counts only if its text is
found on the page (fuzzy match to OCR words); else `REVIEW_REQUIRED`"* —
and Essentials rule 10 repeats it for vision-model values. The match is
*fuzzy* because OCR words are noisy: one misread character must not
condemn a value that is visibly on the page.

What this suite pins down — each is a way grounding could mislead:

* The config is a **labelled placeholder** pinned to the PRD's own
  sentence (and FR-40's row, and Essentials rule 10): the thresholds are
  numbers the PRD never gave, so they must say so.
* Found on the page ⇒ ``grounded``; an OCR typo in one word still found
  (that is what fuzzy means); not found ⇒ ``REVIEW_REQUIRED`` with the
  offending token named — **never a guessed pass**.
* No page text, an empty value, or a value too short to check honestly ⇒
  ``REVIEW_REQUIRED`` (missing data is review, never acceptance).
* Only **model** methods are grounded (OCR values are the page's own
  words); an ungrounded model value warns on the 201 without changing the
  stored value, the doc_type or any status (DEC-0003 — nothing here
  blocks, rejects or mutates a record).
* The result is stored per field (PRD §8 line 159: grounding result is
  field data), exposed through ``FieldOut``, and never rewritten by an
  officer's verification.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.ocr.base import ExtractedFieldCandidate, ExtractionResult
from app.models import ExtractedField
from app.services import fuzzy_grounding, ocr_service

APP = "app-main-0001"
INSTITUTION = "institution@demo.local"
SCRUTINY = "scrutiny@demo.local"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _prd_line(prefix: str) -> str:
    lines = (REPO_ROOT / "md" / "1_PRD.md").read_text(encoding="utf-8").splitlines()
    return next(line for line in lines if line.startswith(prefix))


# ------------------------------------------------------------- the config


def test_the_grounding_config_is_a_labelled_placeholder_pinned_to_the_spec():
    """The thresholds are numbers the PRD never gave — they must say so,
    and the behaviour sentence itself is pinned so config and spec cannot
    drift (same pattern as 5.1's class list)."""
    config = fuzzy_grounding.config()

    # Pinned to the three places the requirement is stated.
    ground_sentence = _prd_line("3. **Ground:**")
    assert "fuzzy match to OCR words" in ground_sentence
    assert "`REVIEW_REQUIRED`" in ground_sentence
    fr40 = _prd_line("| FR-40 |")
    assert "REVIEW_REQUIRED" in fr40 and "found on page" in fr40
    essentials = (REPO_ROOT / "md" / "3_ARCHITECTURE_ESSENTIALS.md").read_text(
        encoding="utf-8"
    )
    rule10 = next(
        line for line in essentials.splitlines() if line.startswith("10.")
    )
    assert "grounded" in rule10 and "`REVIEW_REQUIRED`" in rule10

    # The config cites them and is honest about its own numbers.
    assert "FR-40" in config["source"]
    assert config["rule_reference"] == "RULE-OCR-01"
    assert config["status"] == "proposed_unverified"
    assert config["advisory_only"] is True
    assert "placeholder" in config["note"].lower()
    # Vocabulary comes from the spec, not from this module.
    assert config["statuses"]["review_required"] == "REVIEW_REQUIRED"
    assert config["statuses"]["grounded"] == "grounded"
    # Which methods count as "model values" is config, not code.
    assert config["model_methods"]


def test_the_matching_thresholds_are_numbers_with_a_stated_meaning():
    matching = fuzzy_grounding.config()["matching"]
    assert set(matching) >= {"min_token_length", "token_similarity", "min_match_ratio"}
    assert 0.0 < matching["token_similarity"] <= 1.0
    assert 0.0 < matching["min_match_ratio"] <= 1.0
    assert matching["min_token_length"] >= 1


# ---------------------------------------------------------- the grounding


def test_a_value_found_on_the_page_is_grounded():
    result = fuzzy_grounding.ground(
        value="Example Institute of Technology",
        page_texts=["AFFIDAVIT", "Name of Institution: Example Institute of Technology"],
    )
    assert result["grounded"] is True
    assert result["status"] == "grounded"
    assert result["similarity"] == 1.0
    assert result["matched"] == result["tokens"] >= 3


def test_one_misread_character_still_finds_the_value_on_the_page():
    """Fuzzy means an OCR typo does not condemn a value that is visibly
    there: "Privale" vs "Private" is one substitution in six characters."""
    result = fuzzy_grounding.ground(
        value="Demo Land Holdings Private Limited",
        page_texts=["Lessor: Demo Land Holdings Privale Limited"],
    )
    assert result["grounded"] is True, result
    assert result["status"] == "grounded"
    assert 0.0 < result["similarity"] < 1.0  # it matched fuzzily, not verbatim


def test_a_value_that_is_not_on_the_page_is_review_required():
    result = fuzzy_grounding.ground(
        value="Ghost Institute of Nowhere",
        page_texts=["Name of Institution: Example Institute of Technology"],
    )
    assert result["grounded"] is False
    assert result["status"] == "REVIEW_REQUIRED"
    # The reason names what could not be found — a human knows where to look.
    assert "ghost" in result["reason"].lower() or "nowhere" in result["reason"].lower()
    assert result["matched"] < result["tokens"]


def test_no_page_text_is_review_required_never_a_pass():
    """Missing input follows the essentials: never a guessed pass."""
    for page_texts in ([], ["   "], None):
        result = fuzzy_grounding.ground(value="Example Institute", page_texts=page_texts)
        assert result["grounded"] is False, page_texts
        assert result["status"] == "REVIEW_REQUIRED"
        assert result["reason"] == "no_page_text"


def test_a_value_too_short_to_check_honestly_is_review_required():
    """A two-character value has no token the config may check; claiming
    "found" would be a guess, so it goes to a human."""
    result = fuzzy_grounding.ground(value="12", page_texts=["Room 12, block C"])
    assert result["grounded"] is False
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["reason"] == "no_significant_tokens"


def test_matching_ignores_case_punctuation_and_spacing():
    result = fuzzy_grounding.ground(
        value="  Sub-Registrar of Records, ",
        page_texts=["Issuing Authority: sub registrar of records"],
    )
    assert result["grounded"] is True, result


def test_a_dict_shaped_model_value_is_grounded_by_its_value_string():
    """The Gemini path stores {value, source_quote, ai_reasoning}; the
    value is what must be found on the page (the quote is its citation)."""
    on_page = fuzzy_grounding.ground(
        value={
            "value": "Demo Land Holdings Private Limited",
            "source_quote": "Lessor: Demo Land Holdings Private Limited",
            "ai_reasoning": "read from line 2",
        },
        page_texts=["Lessor: Demo Land Holdings Private Limited"],
    )
    assert on_page["grounded"] is True

    off_page = fuzzy_grounding.ground(
        value={"value": "Completely Fabricated Holdings", "source_quote": "", "ai_reasoning": ""},
        page_texts=["Lessor: Demo Land Holdings Private Limited"],
    )
    assert off_page["grounded"] is False
    assert off_page["status"] == "REVIEW_REQUIRED"


# ------------------------------------------------------- wiring candidates


def _candidates() -> list[ExtractedFieldCandidate]:
    return [
        ExtractedFieldCandidate(
            field_name="lessor_name",
            value="Demo Land Holdings Private Limited",
            method="gemini_grounded_ai",
            confidence=0.98,
            engine="gemini",
        ),
        ExtractedFieldCandidate(
            field_name="lessee_name",
            value="Completely Fabricated Holdings",
            method="gemini_grounded_ai",
            confidence=0.98,
            engine="gemini",
        ),
        ExtractedFieldCandidate(
            field_name="document_id",
            value="DOC-123",
            method="pdf_text",
            confidence=0.9,
            engine="pypdf",
        ),
        ExtractedFieldCandidate(
            field_name="institution_name",
            value="Example Institute of Technology",
            method="mock_ocr",
            confidence=0.9,
            engine="mock",
        ),
    ]


def test_only_model_methods_are_grounded_and_an_ungrounded_value_warns():
    candidates = _candidates()
    warnings = fuzzy_grounding.ground_candidates(
        candidates, ["Lessor: Demo Land Holdings Private Limited"]
    )

    by_name = {candidate.field_name: candidate for candidate in candidates}
    # Model values: grounded, or REVIEW_REQUIRED.
    assert by_name["lessor_name"].grounding == "grounded"
    assert by_name["lessee_name"].grounding == "REVIEW_REQUIRED"
    # OCR/mock values are the page's own words — grounding does not apply.
    assert by_name["document_id"].grounding is None
    assert by_name["institution_name"].grounding is None

    # Exactly one warning, naming the field and the status — advisory on a
    # 201, never a rejection (the 5.1 classifier pattern).
    assert len(warnings) == 1
    assert "lessee_name" in warnings[0]
    assert "REVIEW_REQUIRED" in warnings[0]


def test_grounding_a_candidate_never_changes_its_value_or_method():
    candidates = _candidates()
    before = [
        (candidate.value, candidate.method, candidate.confidence)
        for candidate in candidates
    ]
    fuzzy_grounding.ground_candidates(
        candidates, ["Lessor: Demo Land Holdings Private Limited"]
    )
    after = [
        (candidate.value, candidate.method, candidate.confidence)
        for candidate in candidates
    ]
    assert after == before


# ----------------------------------------------------- storage + the API


def test_the_model_carries_a_nullable_grounding_column_and_seeded_rows_are_null():

    columns = {column.name: column for column in ExtractedField.__table__.columns}
    assert "grounding" in columns
    assert columns["grounding"].nullable
    assert columns["grounding"].type.length == 32

    # Seeded demo rows were never produced by a model: NULL, not a status.
    from sqlalchemy import select

    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        rows = session.scalars(
            select(ExtractedField).where(ExtractedField.method == "seed")
        ).all()
        assert rows, "the demo seed must create extracted fields"
        for row in rows:
            assert row.grounding is None
    finally:
        session.close()


class _ModelValuedExtractor:
    """Stands in for the Gemini path: one grounded value, one fabrication,
    plus an ordinary OCR value. No network, ever."""

    def extract(self, *, doc_type: str, content: bytes, file_name: str) -> ExtractionResult:
        result = ExtractionResult(doc_type=doc_type, simulated=False)
        result.page_texts = ["Lessor: Demo Land Holdings Private Limited"]
        result.fields = [
            ExtractedFieldCandidate(
                field_name="lessor_name",
                value="Demo Land Holdings Private Limited",
                source_page=1,
                method="gemini_grounded_ai",
                confidence=0.98,
                engine="gemini",
                engine_version="test-model",
            ),
            ExtractedFieldCandidate(
                field_name="lessee_name",
                value="Completely Fabricated Holdings",
                source_page=1,
                method="gemini_grounded_ai",
                confidence=0.98,
                engine="gemini",
                engine_version="test-model",
            ),
        ]
        return result


def test_upload_stores_grounding_and_warns_without_blocking_or_mutating(
    client, as_user, db
):
    from sqlalchemy import select

    ocr_service.set_ocr_extractor(_ModelValuedExtractor())
    try:
        upload = client.post(
            f"/api/v1/applications/{APP}/documents",
            headers=as_user(INSTITUTION),
            data={"doc_type": "affidavit"},
            files={"file": ("affidavit.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    finally:
        ocr_service.reset_ocr_extractor()

    # Grounding never blocks: the upload is a 201 with both values stored.
    assert upload.status_code == 201, upload.text
    body = upload.json()
    fields = {field["field_name"]: field for field in body["document"]["fields"]}
    assert fields["lessor_name"]["grounding"] == "grounded"
    assert fields["lessee_name"]["grounding"] == "REVIEW_REQUIRED"
    # The fabrication is kept (three-value model) and stays a candidate —
    # no status change, no doc_type change, nothing the model decided.
    assert fields["lessee_name"]["value"] == "Completely Fabricated Holdings"
    assert fields["lessee_name"]["verification_status"] == "unverified"
    assert body["document"]["doc_type"] == "affidavit"
    # The advisory warning rides the existing warnings channel (5.1 pattern).
    warnings = body["extraction"]["warnings"]
    assert any("lessee_name" in str(w) for w in warnings), warnings

    # Persisted on THIS document, and readable back through the API.
    document_id = body["document"]["id"]
    stored = db.scalars(
        select(ExtractedField).where(
            ExtractedField.document_id == document_id,
            ExtractedField.field_name == "lessee_name",
        )
    ).one()
    assert stored.grounding == "REVIEW_REQUIRED"

    # An officer's verification changes only the status — grounding is
    # provenance, immutable to reviewers (same rule as bbox/engine in 5.2).
    verify = client.post(
        f"/api/v1/applications/{APP}/documents/{stored.document_id}"
        f"/fields/{stored.id}/verify",
        headers=as_user(SCRUTINY),
        json={"verification_status": "verified", "note": "checked against the page"},
    )
    assert verify.status_code == 200
    db.refresh(stored)
    assert stored.verification_status == "verified"
    assert stored.grounding == "REVIEW_REQUIRED"
