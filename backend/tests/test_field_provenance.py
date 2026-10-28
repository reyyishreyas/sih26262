"""Phase 5.2: per-field provenance — bbox, engine + version, page (FR-48, FR-39).

The plan's 5.2 (line 81) reads: *"Store per-field bbox, confidence, engine+
version, page (extend extracted-field model + migration)."* Confidence and
page already existed on `ExtractedField`; this adds the three missing pieces:

* **bbox** — where on the page the value was read, as normalised fractions
  (``origin: top_left``, ``level: line``) so the UI can highlight the exact
  line without knowing page pixel sizes (FR-48 split-screen highlight).
* **engine / engine_version** — *who* read the value (pypdf, Tesseract, the
  mock, the grounded lease parser, Gemini). Provenance for a checker: two
  engines reading the same file differently is exactly the kind of
  discrepancy a human must resolve.

What this suite pins down — each is a way provenance could mislead:

* Every real text-layer field carries the pypdf version actually installed
  and a bbox inside the page's 0..1 frame, ``origin: top_left``,
  ``level: line``; two lines of the same page get **different** boxes.
* When a normalised value (an ISO date) cannot be found verbatim in the
  line text, the locator falls back to the parser's own label line rather
  than inventing a box — and answers ``None`` if neither is on the page.
* The mock admits it is the mock (engine ``mock``, no bbox, no version);
  the grounded lease parser admits it is ``grounded_lease``.
* Provenance survives the round trip through the API and an officer's
  verification without being rewritten.
* OCR provenance (engine ``tesseract`` + pixel-derived boxes) — marked
  ``requires_ocr``; on a machine without Tesseract it **skips, which is
  reported as skipped, never as passing** (BUG-0001).
"""

from __future__ import annotations

import shutil

import pytest
from pdf_factory import affidavit_pdf, lease_deed_pdf
from sqlalchemy import JSON

from app.adapters.ocr.mock import MockOCRExtractor
from app.adapters.ocr.real import RealOCRExtractor
from app.models import ExtractedField
from app.services.grounded_lease_extractor import GroundedLeaseExtractor

APP = "app-main-0001"
INSTITUTION = "institution@demo.local"
SCRUTINY = "scrutiny@demo.local"

BBOX_KEYS = {"x", "y", "width", "height", "origin", "level"}

# Same pattern as test_document_extraction.py: skipped != passed (BUG-0001).
requires_ocr = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract is not installed on this machine",
)


def _assert_normalised_line_box(bbox: dict) -> None:
    """A bbox must be a line box inside the page's unit frame."""
    assert set(bbox) == BBOX_KEYS, bbox
    assert bbox["origin"] == "top_left"
    assert bbox["level"] == "line"
    for key in ("x", "y", "width", "height"):
        assert isinstance(bbox[key], float), (key, bbox[key])
        assert 0.0 <= bbox[key] <= 1.0, (key, bbox[key])
    # The box must fit inside the page, not just have in-range parts.
    assert bbox["x"] + bbox["width"] <= 1.0001, bbox
    assert bbox["y"] + bbox["height"] <= 1.0001, bbox
    assert bbox["width"] > 0.0 and bbox["height"] > 0.0, bbox


# ------------------------------------------------------------- the model


def test_the_extracted_field_model_carries_the_three_new_columns():
    columns = {column.name: column for column in ExtractedField.__table__.columns}
    # bbox: JSON, nullable — old rows (and engines with no box) store NULL.
    assert "bbox" in columns
    assert isinstance(columns["bbox"].type, JSON)
    assert columns["bbox"].nullable
    # engine + version: short strings, nullable — unknown provenance is NULL,
    # never a guessed name.
    for name in ("engine", "engine_version"):
        assert name in columns
        assert columns[name].nullable
        assert columns[name].type.length == 64
    # The pre-existing provenance fields stay (5.2 extends, never replaces).
    assert {"source_page", "source_span", "method", "confidence"} <= set(columns)


def test_the_source_span_column_holds_the_ocr_adapters_own_cap():
    # The real OCR adapter deliberately truncates spans to 512 characters
    # (adapters/ocr/real.py) — long intake-table rows for real scanned EoA
    # documents exceed the old 255-char column and turned the whole upload
    # into a 500 (BUG-0091). The column must accept what the adapter writes.
    columns = {column.name: column for column in ExtractedField.__table__.columns}
    assert columns["source_span"].type.length >= 512


# ------------------------------------------------- the pypdf text-layer read


def test_text_layer_fields_carry_pypdf_version_and_a_normalised_line_box():
    import pypdf

    result = RealOCRExtractor().extract(
        doc_type="affidavit",
        content=affidavit_pdf(),
        file_name="affidavit.pdf",
    )
    assert result.fields, "the affidavit fixture must yield fields"
    for field in result.fields:
        assert field.method == "pdf_text"
        assert field.engine == "pypdf"
        # The version actually installed, not a hard-coded string.
        assert field.engine_version == pypdf.__version__
        assert field.source_page is not None
        assert field.confidence > 0.0
        _assert_normalised_line_box(field.bbox)


def test_two_lines_on_one_page_get_different_boxes():
    result = RealOCRExtractor().extract(
        doc_type="affidavit",
        content=affidavit_pdf(),
        file_name="affidavit.pdf",
    )
    by_name = {field.field_name: field for field in result.fields}
    # Page 2 of the fixture holds "AICTE Identity No: ..." then
    # "Document ID: ..." on the next line down.
    aicte, document_id = by_name["aicte_id"], by_name["document_id"]
    assert aicte.source_page == document_id.source_page == 2
    assert aicte.bbox != document_id.bbox
    # Top-left origin: the second line sits *below* the first.
    assert document_id.bbox["y"] > aicte.bbox["y"]


def test_an_iso_date_falls_back_to_its_label_line_rather_than_no_box():
    """`notary_date` is stored as "2026-04-12" but the page reads "Sworn on
    12 April 2026" — the value itself matches no line, so the locator uses
    the parser's own label (the value is read *after* that label on the same
    line by construction). No label match would mean bbox None, not a guess.
    """
    result = RealOCRExtractor().extract(
        doc_type="affidavit",
        content=affidavit_pdf(),
        file_name="affidavit.pdf",
    )
    notary = next(f for f in result.fields if f.field_name == "notary_date")
    assert notary.value == "2026-04-12"
    _assert_normalised_line_box(notary.bbox)


def test_a_value_that_matches_no_line_and_no_label_has_no_box():
    """Honest absence: a field the locator cannot place keeps bbox None."""
    from app.adapters.ocr.base import ExtractionResult
    from app.adapters.ocr.real import _add, _Line, _Page

    page = _Page(
        number=1,
        text="Nothing here resembles the value.",
        method="pdf_text",
        confidence=0.9,
        engine="pypdf",
        engine_version="0",
        lines=[_Line(text="Nothing here resembles the value.", bbox={"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.1, "origin": "top_left", "level": "line"})],
    )
    result = ExtractionResult(doc_type="affidavit")
    _add(
        result,
        name="notary_date",
        value="2026-04-12",
        page=page,
        method_note="label 'no such label exists here'",
        confidence=0.9,
    )
    assert result.fields[0].bbox is None


# ------------------------------------------------------------- the engines


def test_the_mock_admits_it_is_the_mock():
    result = MockOCRExtractor().extract(
        doc_type="affidavit", content=b"%PDF-1.4", file_name="anything.pdf"
    )
    assert result.fields
    for field in result.fields:
        assert field.engine == "mock"
        assert field.engine_version is None
        assert field.bbox is None  # it never read a page, so it has no box


def test_legacy_grounded_lease_facade_uses_local_ocr(monkeypatch):
    # The compatibility facade remains local regardless of API-key presence.
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-used")
    result = GroundedLeaseExtractor().extract(
        content=lease_deed_pdf(), file_name="lease.pdf"
    )
    assert result.fields, "the lease fixture must yield fields"
    assert all(field.engine == "pypdf" for field in result.fields)
    assert all(field.bbox is not None for field in result.fields)
    assert result.warnings == []


# ------------------------------------------------------------- the API


def test_provenance_survives_upload_and_officer_verification(client, as_user, db):
    """The three keys reach the client through FieldOut and are not rewritten
    when an officer verifies the field (verification changes only status)."""

    from app.models import ExtractedField

    upload = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user(INSTITUTION),
        data={"doc_type": "affidavit"},
        files={
            "file": ("affidavit.pdf", affidavit_pdf(), "application/pdf")
        },
    )
    assert upload.status_code == 201
    fields = upload.json()["document"]["fields"]
    assert fields, "the affidavit must yield fields"
    for field in fields:
        assert field["engine"] == "pypdf"
        assert field["engine_version"] is not None
        _assert_normalised_line_box(field["bbox"])

    # An officer verifies one field; provenance must be untouched.
    target = fields[0]
    verify = client.post(
        f"/api/v1/applications/{APP}/documents/{target['document_id']}"
        f"/fields/{target['id']}/verify",
        headers=as_user(SCRUTINY),
        json={"verification_status": "verified", "note": "checked against the scan"},
    )
    assert verify.status_code == 200

    row = db.get(ExtractedField, target["id"])
    assert row.verification_status == "verified"
    # Everything about *where/how it was read* is unchanged by a human
    # confirming the value.
    assert row.engine == target["engine"]
    assert row.engine_version == target["engine_version"]
    assert row.bbox == target["bbox"]

    # And the read-back through the API still exposes it.
    listed = client.get(
        f"/api/v1/applications/{APP}/documents", headers=as_user(SCRUTINY)
    )
    stored = next(d for d in listed.json() if d["id"] == target["document_id"])
    read_back = next(f for f in stored["fields"] if f["id"] == target["id"])
    assert read_back["bbox"] == target["bbox"]
    assert read_back["engine"] == "pypdf"


def test_seeded_fields_have_honest_null_provenance_where_no_engine_ran(client, db):
    """Seeded demo rows were never read by an engine: NULL, not a fake name."""
    from sqlalchemy import select

    rows = db.scalars(
        select(ExtractedField).where(ExtractedField.method == "seed")
    ).all()
    assert rows, "the demo seed must create extracted fields"
    for row in rows:
        assert row.engine is None
        assert row.engine_version is None
        assert row.bbox is None


# ------------------------------------------------------------- the OCR path


@requires_ocr
def test_ocr_fields_carry_tesseract_version_and_pixel_line_boxes():
    """Tesseract provenance with boxes derived from image_to_data word
    geometry. Skips (never silently passes) without the binary — BUG-0001."""
    from test_document_extraction import _scan_image

    # A scan of the lease fixture's lines: no text layer, so OCR runs.
    scan = _scan_image(
        [
            "REGISTERED LEASE DEED",
            "Lessor: Demo Land Holdings Private Limited",
            "Lessee: Example Institute of Technology",
            "Valid To: 31 March 2028",
        ]
    )
    result = RealOCRExtractor().extract(
        doc_type="lease_deed", content=scan, file_name="photo.png"
    )
    assert result.fields
    for field in result.fields:
        assert field.method == "ocr"
        assert field.engine == "tesseract"
        # Version of the binary on *this* machine, read at runtime.
        assert field.engine_version
        assert field.engine_version[0].isdigit()
        _assert_normalised_line_box(field.bbox)
    # Lessee and Valid To are on different rendered lines: different boxes.
    by_name = {field.field_name: field for field in result.fields}
    if {"lessee_name", "valid_to"} <= set(by_name):
        assert by_name["lessee_name"].bbox != by_name["valid_to"].bbox
