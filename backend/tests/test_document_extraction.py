"""Real document extraction: the uploaded bytes are actually read.

The mock extractor is still available for tests that do not care about
extraction, but the default engine has to prove it reads real files — including
scans and photos, which go through Tesseract OCR.
"""

from __future__ import annotations

import shutil
from io import BytesIO

import pytest
from pdf_factory import affidavit_pdf, lease_deed_pdf, text_pdf

from app.adapters.ocr.mock import MockOCRExtractor
from app.adapters.ocr.real import RealOCRExtractor
from app.services import ocr_service

TESSERACT_INSTALLED = shutil.which("tesseract") is not None
requires_ocr = pytest.mark.skipif(
    not TESSERACT_INSTALLED,
    reason="Tesseract is not installed on this machine",
)


def _render(lines: list[str], *, font_size: int = 22):
    """Draws text onto a blank page, the way a phone photo of a page looks."""
    from PIL import Image, ImageDraw

    font = _font(font_size)
    image = Image.new("RGB", (1400, 200 + 60 * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((80, 80 + 60 * index), line, fill="black", font=font)
    return image


def _font(size: int):
    """A TrueType font when one is available, else Pillow's built-in bitmap."""
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _scan_image(lines: list[str]) -> bytes:
    """The rendered page as a PNG upload."""
    buffer = BytesIO()
    _render(lines).save(buffer, format="PNG")
    return buffer.getvalue()


def _scan_pdf(lines: list[str]) -> bytes:
    """A PDF whose page is an image — a scan with no text layer inside."""
    buffer = BytesIO()
    _render(lines).save(buffer, format="PDF", resolution=150)
    return buffer.getvalue()


LEASE_LINES = [
    "REGISTERED LEASE DEED",
    "Lessor: Demo Land Holdings Private Limited",
    "Lessee: Example Institute of Technology",
    "Issuing Authority: Sub-Registrar of Records, Demo District",
    "Valid From: 01 April 2026",
    "Valid To: 31 March 2028",
]


def test_a_pdf_with_a_text_layer_is_read_directly():
    result = RealOCRExtractor().extract(
        doc_type="lease_deed", content=lease_deed_pdf(), file_name="lease.pdf"
    )
    assert result.simulated is False
    values = {field.field_name: field.value for field in result.fields}
    assert values["lessee_name"] == "Example Institute of Technology"
    assert values["valid_to"] == "2028-03-31"
    assert {field.method for field in result.fields} == {"pdf_text"}
    # A text layer is read with high, but never perfect, confidence.
    assert all(0.8 <= field.confidence <= 0.99 for field in result.fields)
    assert result.warnings == []


def test_dates_are_normalised_to_iso_from_every_common_format():
    extractor = RealOCRExtractor()
    cases = {
        "Valid To: 31 March 2028": "2028-03-31",
        "Valid To: 31st March, 2028": "2028-03-31",
        "Valid To: March 31, 2028": "2028-03-31",
        "Valid To: 2028-03-31": "2028-03-31",
        "Valid To: 31/03/2028": "2028-03-31",
    }
    for line, expected in cases.items():
        result = extractor.extract(
            doc_type="lease_deed",
            content=text_pdf([[line]]),
            file_name="lease.pdf",
        )
        found = [f.value for f in result.fields if f.field_name == "valid_to"]
        assert found == [expected], f"{line!r} produced {found}"


def test_an_impossible_date_is_dropped_rather_than_guessed():
    """The rule engine compares dates as strings, so a half-read date must
    never reach it: it is omitted and reported instead."""
    result = RealOCRExtractor().extract(
        doc_type="lease_deed",
        content=text_pdf([["Valid To: 31 Smarch 2028"]]),
        file_name="lease.pdf",
    )
    assert [f.field_name for f in result.fields] == []
    assert any("Could not find any of the expected details" in w for w in result.warnings)


def test_each_page_records_where_the_value_came_from():
    result = RealOCRExtractor().extract(
        doc_type="affidavit",
        content=affidavit_pdf(),
        file_name="affidavit.pdf",
    )
    pages = {f.field_name: f.source_page for f in result.fields}
    assert pages["institution_name"] == 1
    assert pages["aicte_id"] == 2
    assert pages["notary_date"] == 3


def test_a_document_type_without_a_profile_says_so_honestly():
    result = RealOCRExtractor().extract(
        doc_type="other",
        content=text_pdf([["Anything at all"]]),
        file_name="other.pdf",
    )
    assert result.fields == []
    assert any("by hand" in warning for warning in result.warnings)


@requires_ocr
def test_a_photo_of_a_page_is_read_with_ocr():
    result = RealOCRExtractor().extract(
        doc_type="lease_deed",
        content=_scan_image(LEASE_LINES),
        file_name="photo.png",
    )
    assert result.simulated is False
    assert {field.method for field in result.fields} == {"ocr"}
    values = {field.field_name: field.value for field in result.fields}
    # OCR reads what is really there, including the institute's own name.
    assert values["lessee_name"] == "Example Institute of Technology"
    # OCR confidence is measured from Tesseract's own word confidences.
    assert all(0.1 < field.confidence < 1.0 for field in result.fields)


@requires_ocr
def test_a_scanned_pdf_is_ocrd_page_by_page():
    result = RealOCRExtractor().extract(
        doc_type="lease_deed",
        content=_scan_pdf(LEASE_LINES),
        file_name="scan.pdf",
    )
    assert {field.method for field in result.fields} == {"ocr"}
    values = {field.field_name: field.value for field in result.fields}
    assert values["valid_to"] == "2028-03-31"
    # The person is told the file was a scan, so they check extra carefully.
    assert any("read with OCR" in warning for warning in result.warnings)


def test_a_corrupt_pdf_is_a_warning_not_an_exception():
    result = RealOCRExtractor().extract(
        doc_type="lease_deed",
        content=b"%PDF-1.4 fake demo bytes",
        file_name="broken.pdf",
    )
    assert result.fields == []
    assert result.simulated is False
    assert any("could not be opened" in warning for warning in result.warnings)


def test_an_unknown_file_type_is_refused_with_a_message():
    result = RealOCRExtractor().extract(
        doc_type="lease_deed",
        content=b"just some plain text, not a document",
        file_name="notes.pdf",
    )
    assert result.fields == []
    assert any("cannot be read" in warning for warning in result.warnings)


def test_the_mock_stays_selectable_for_demos_that_cannot_ocr():
    ocr_service.set_ocr_extractor(MockOCRExtractor())
    try:
        result = ocr_service.get_ocr_extractor().extract(
            doc_type="lease_deed",
            content=b"%PDF-1.4",
            file_name="anything.pdf",
        )
        assert result.simulated is True
        assert {f.field_name for f in result.fields} >= {"valid_to", "lessee_name"}
    finally:
        ocr_service.reset_ocr_extractor()
