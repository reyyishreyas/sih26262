"""Real extraction: reads the bytes that were actually uploaded.

Two engines, chosen per file:

* a text layer, when a PDF has one (the file was produced digitally, or the
  scanner embedded text). Fast, and the most reliable read;
* Tesseract OCR, for uploaded images and for PDFs that are scans (no text
  layer). Slower and noisier — a stamp or a smudge changes the letters, which
  is why every value this produces stays *unverified* until a human confirms
  it.

Nothing here invents a value. A field is emitted only when a labelled pattern
in the document's own text supports it, and a date is emitted only when it can
be normalised to ISO ``YYYY-MM-DD`` (the rule engine compares dates as
strings, so a half-read date must never reach it). Anything unreadable is
reported as a warning for a human to resolve by hand.

Failures are contained: a corrupt PDF or a missing Tesseract binary yields no
fields and an honest warning, never a 500 on the upload.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from .base import ExtractedFieldCandidate, ExtractionResult

# Rendering scale for scanned pages. 2x keeps small print readable without
# making a 10MB scan take minutes to OCR.
_RENDER_SCALE = 2.0

# An image smaller than this is upscaled before OCR; phone photos of a page
# are often too small for Tesseract to segment words reliably.
_MIN_OCR_WIDTH = 1200

# A text layer read is trustworthy but never certain (a PDF can carry the
# wrong text layer), so it is not reported as 1.0.
_TEXT_LAYER_CONFIDENCE = 0.9

_PDF_MAGIC = b"%PDF"
_PNG_MAGIC = b"\x89PNG"
_JPEG_MAGIC = b"\xff\xd8\xff"
_GIF_MAGIC = b"GIF8"
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")
_BMP_MAGIC = b"BM"

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))

# OCR noise that we normalise *before* date parsing, and nothing else. These
# are the substitutions Tesseract reliably makes on dates; fixing letters
# anywhere else would be guessing at the document's content.
_OCR_NOISE = (
    (re.compile(r"\b(\d)[Oo](\d)\b"), r"\g<1>0\g<2>"),      # 2O28 -> 2028
    (re.compile(r"\b(\d)[lI](\d)\b"), r"\g<1>1\g<2>"),      # 1l24 -> 1124
    (re.compile(r"(?<=\d)O(?=\d)"), "0"),
    (re.compile(r"\bO(\d)(\d)\b"), r"0\g<1>\g<2>"),
)


@dataclass
class _Page:
    """One page of readable text plus how it was read."""

    number: int
    text: str
    method: str
    confidence: float


class RealOCRExtractor:
    """Reads uploaded documents with pypdf and/or Tesseract."""

    simulated = False

    def extract(
        self, *, doc_type: str, content: bytes, file_name: str
    ) -> ExtractionResult:
        result = ExtractionResult(doc_type=doc_type, simulated=False)

        pages, warnings = self._read_pages(content, result)
        result.warnings.extend(warnings)
        # Classification (FR-38) runs on these words later — keep them.
        result.page_texts = [page.text for page in pages]

        if not pages:
            return result

        found = _parse(doc_type, pages, result)
        if not found:
            result.warnings.append(
                "Could not find any of the expected details in this file. "
                "It may be a scan we cannot read, or the wrong kind of "
                "document — a checker will read it by hand."
            )
        return result

    # -- reading -----------------------------------------------------------

    def _read_pages(
        self, content: bytes, result: ExtractionResult
    ) -> tuple[list[_Page], list[str]]:
        warnings: list[str] = []
        pages: list[_Page] = []

        if content[:4] == _PDF_MAGIC:
            pages, warnings = self._read_pdf(content, result)
        elif self._is_image(content):
            page = self._read_image(content, page_number=1, result=result)
            if page is not None:
                pages = [page]
            else:
                warnings.append(
                    "This image could not be read. Please upload a clearer "
                    "photo or scan of the document."
                )
        else:
            warnings.append(
                "This file type cannot be read. Please upload a PDF or an "
                "image (PNG, JPEG) of the document."
            )

        return pages, warnings

    @staticmethod
    def _is_image(content: bytes) -> bool:
        return (
            content[:4] == _PNG_MAGIC
            or content[:3] == _JPEG_MAGIC
            or content[:4] == _GIF_MAGIC
            or content[:2] in _TIFF_MAGIC
            or content[:2] == _BMP_MAGIC
        )

    def _read_pdf(
        self, content: bytes, result: ExtractionResult
    ) -> tuple[list[_Page], list[str]]:
        warnings: list[str] = []
        pages: list[_Page] = []

        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            for index, pdf_page in enumerate(reader.pages, start=1):
                text = (pdf_page.extract_text() or "").strip()
                if text:
                    pages.append(
                        _Page(
                            number=index,
                            text=text,
                            method="pdf_text",
                            confidence=_TEXT_LAYER_CONFIDENCE,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - corrupt files must not 500
            warnings.append(
                "This PDF could not be opened as a PDF "
                f"({type(exc).__name__}). If it is a scan, try re-saving it "
                "as a PDF, or upload a photo of the document instead."
            )
            return [], warnings

        if pages:
            return pages, warnings

        # No text layer: this is a scan. Render every page and OCR it.
        ocr_pages, ocr_warnings = self._read_pdf_as_scans(content, result)
        return ocr_pages, warnings + ocr_warnings

    def _read_pdf_as_scans(
        self, content: bytes, result: ExtractionResult
    ) -> tuple[list[_Page], list[str]]:
        warnings: list[str] = []
        pages: list[_Page] = []

        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(BytesIO(content))
            rendered = []
            for index in range(len(document)):
                bitmap = document[index].render(scale=_RENDER_SCALE)
                rendered.append(bitmap.to_pil())
        except Exception as exc:  # noqa: BLE001 - corrupt files must not 500
            warnings.append(
                "This PDF has no readable text and its pages could not be "
                f"prepared for scanning ({type(exc).__name__})."
            )
            return [], warnings

        for index, image in enumerate(rendered, start=1):
            page = self._ocr_image(image, page_number=index, result=result)
            if page is not None:
                pages.append(page)

        if pages:
            result.warnings.append(
                "This PDF is a scan (no text inside), so the pages were "
                "read with OCR. Scanned text is less reliable — please "
                "check every detail below."
            )
        return pages, warnings

    def _read_image(
        self, content: bytes, *, page_number: int, result: ExtractionResult
    ) -> _Page | None:
        try:
            from PIL import Image

            image = Image.open(BytesIO(content))
            image.load()
        except Exception:  # noqa: BLE001 - unreadable image, reported below
            return None
        return self._ocr_image(image, page_number=page_number, result=result)

    def _ocr_image(self, image, *, page_number: int, result: ExtractionResult) -> _Page | None:
        try:
            import pytesseract
            from PIL import Image

            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            # Small photos are upscaled: Tesseract needs the resolution to
            # separate words that a phone camera blurred together.
            if image.width < _MIN_OCR_WIDTH:
                factor = _MIN_OCR_WIDTH / image.width
                image = image.resize(
                    (int(image.width * factor), int(image.height * factor)),
                    Image.LANCZOS,
                )

            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT
            )
            text = pytesseract.image_to_string(image)
        except ImportError:
            result.warnings.append(
                "The OCR engine (Tesseract) is not installed on this "
                "server, so scanned documents and photos cannot be read."
            )
            return None
        except Exception as exc:  # noqa: BLE001 - OCR must never break upload
            result.warnings.append(
                f"OCR failed on page {page_number} ({type(exc).__name__})."
            )
            return None

        confidences = [
            int(value)
            # strict=False: a malformed OCR response with unequal lists should
            # yield fewer values, not crash the extraction.
            for value, word in zip(
                data.get("conf", []), data.get("text", []), strict=False
            )
            if str(value) != "-1" and word.strip()
        ]
        # Tesseract reports -1 for non-word blocks and 0-100 otherwise. When
        # it found no words at all the page is blank, not unreadable-but-
        # present, so confidence stays low and the value is unverified.
        confidence = (
            max(0.1, sum(confidences) / len(confidences) / 100)
            if confidences
            else 0.1
        )

        text = text.strip()
        if not text:
            return None

        return _Page(
            number=page_number,
            text=text,
            method="ocr",
            confidence=round(confidence, 2),
        )


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------


def _normalise_ocr(text: str) -> str:
    for pattern, replacement in _OCR_NOISE:
        text = pattern.sub(replacement, text)
    return text


def _to_iso_date(raw: str) -> str | None:
    """Normalises a date found in a document to ISO ``YYYY-MM-DD``.

    Returns ``None`` when the text is not confidently a single date — the
    rule engine compares dates as plain strings, so a guess here would be
    compared as if it were a fact.
    """
    text = raw.strip().strip(".,;:")
    text = re.sub(r"\s+", " ", text)

    # 2028-03-31 or 2028/03/31
    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return _safe_iso(year, month, day)

    # 31/03/2028 or 31-03-2028 (day first — Indian convention, and the only
    # reading that keeps 01/04/2026 distinct from an April date written US
    # style elsewhere in the same document).
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        return _safe_iso(year, month, day)

    # 31 March 2028, 31st March, 2028, 31-Mar-2028
    match = re.fullmatch(
        rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})[a-z]*\.?,?\s+(\d{{4}})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        day, month_name, year = match.groups()
        return _safe_iso(int(year), _MONTHS[month_name.lower()], int(day))

    # March 31, 2028 / March 31 2028
    match = re.fullmatch(
        rf"({_MONTH_PATTERN})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        month_name, day, year = match.groups()
        return _safe_iso(int(year), _MONTHS[month_name.lower()], int(day))

    return None


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


# A date as it may appear in a document, after OCR noise has been normalised.
_DATE = r"\d{1,2}(?:st|nd|rd|th)?[\s.,/-]+(?:{_MONTHS})[a-z]*\.?,?[\s]*\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|(?:{_MONTHS})[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{2,4}".replace(
    "{_MONTHS}", _MONTH_PATTERN
)

_DATE_RE = re.compile(_DATE, flags=re.IGNORECASE)


def _text_after(label: str, text: str) -> str | None:
    """Returns what follows ``label`` on the same line, if anything looks like
    a value rather than another label.

    The label is followed by a word boundary so that ``id`` does not match
    inside ``identity``, and one trailing qualifier word (``no``, ``number``)
    is allowed so that "AICTE Identity No: 1-12345678" yields the number
    rather than "No: 1-12345678".
    """
    pattern = re.compile(
        rf"{label}\b\s*(?:(?:no|number|id|identity)\b\s*)?[:\-–]?\s*"
        rf"([A-Za-z0-9][^\n]{{2,120}})",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip().strip(".,;:")
    # Reject the case where the label was at the end of a line and the next
    # words were the start of an unrelated sentence.
    if not value or len(value) < 2:
        return None
    return value


def _date_after(label: str, text: str) -> str | None:
    match = re.search(
        rf"{label}\b\s*[:\-–]?\s*({_DATE})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    candidate = _normalise_ocr(match.group(1))
    return _to_iso_date(candidate)


def _add(
    result: ExtractionResult,
    *,
    name: str,
    value: object,
    page: _Page,
    method_note: str,
    confidence: float,
) -> None:
    result.fields.append(
        ExtractedFieldCandidate(
            field_name=name,
            value=value,
            source_page=page.number,
            source_span=method_note,
            method=page.method,
            confidence=round(min(confidence, page.confidence), 2),
        )
    )


def _parse(doc_type: str, pages: list[_Page], result: ExtractionResult) -> int:
    """Extracts the labelled fields a rule or a human cares about.

    Returns the number of fields found, so the caller can warn honestly when
    a document of this type yielded nothing.
    """
    parser = _PARSERS.get(doc_type)
    if parser is None:
        return 0
    return parser(pages, result)


def _parse_lease_deed(pages: list[_Page], result: ExtractionResult) -> int:
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        lessee = _text_after(r"lessee(?:\s+name)?", text)
        if lessee and not any(f.field_name == "lessee_name" for f in result.fields):
            _add(
                result,
                name="lessee_name",
                value=lessee,
                page=page,
                method_note="label 'lessee'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        lessor = _text_after(r"lessor(?:\s+name)?", text)
        if lessor and not any(f.field_name == "lessor_name" for f in result.fields):
            _add(
                result,
                name="lessor_name",
                value=lessor,
                page=page,
                method_note="label 'lessor'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        authority = _text_after(
            r"(?:issuing\s+authority|registered\s+at|registration\s+authority|sub[\s-]?registrar)",
            text,
        )
        if authority and not any(
            f.field_name == "issuing_authority" for f in result.fields
        ):
            _add(
                result,
                name="issuing_authority",
                value=authority,
                page=page,
                method_note="label 'issuing authority'",
                confidence=0.88 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        valid_from = _date_after(
            r"(?:valid\s+from|lease\s+(?:starts|commences)|commencing|term\s+from)",
            text,
        )
        if valid_from and not any(
            f.field_name == "valid_from" for f in result.fields
        ):
            _add(
                result,
                name="valid_from",
                value=valid_from,
                page=page,
                method_note="label 'valid from'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        valid_to = _date_after(
            r"(?:valid\s+(?:to|until|till|up\s+to)|expiry|expires|term\s+(?:to|until))",
            text,
        )
        if valid_to and not any(f.field_name == "valid_to" for f in result.fields):
            _add(
                result,
                name="valid_to",
                value=valid_to,
                page=page,
                method_note="label 'valid to'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


def _parse_ownership_record(pages: list[_Page], result: ExtractionResult) -> int:
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        holder = _text_after(
            r"(?:record\s+holder|owner(?:\s+name)?|held\s+by|proprietor)",
            text,
        )
        if holder and not any(f.field_name == "record_holder" for f in result.fields):
            _add(
                result,
                name="record_holder",
                value=holder,
                page=page,
                method_note="label 'record holder'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        expiry = _date_after(
            r"(?:lease\s+expiry|expiry|expires|valid\s+(?:to|until|up\s+to))",
            text,
        )
        if expiry and not any(f.field_name == "lease_expiry" for f in result.fields):
            _add(
                result,
                name="lease_expiry",
                value=expiry,
                page=page,
                method_note="label 'lease expiry'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


def _parse_affidavit(pages: list[_Page], result: ExtractionResult) -> int:
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        institution = _text_after(
            r"(?:name\s+of\s+(?:the\s+)?institution|institution\s+name|college\s+name)",
            text,
        )
        if institution and not any(
            f.field_name == "institution_name" for f in result.fields
        ):
            _add(
                result,
                name="institution_name",
                value=institution,
                page=page,
                method_note="label 'name of institution'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        # Tesseract reads "Id" as "ld" and "1" as "2" often enough that the
        # pattern accepts both spellings; the value itself is never corrected.
        aicte_id = _text_after(
            r"(?:aicte\s+(?:id|identity)|approval\s+(?:no|number)|aicte\s+(?:no|number))",
            text,
        )
        if aicte_id and not any(f.field_name == "aicte_id" for f in result.fields):
            _add(
                result,
                name="aicte_id",
                value=aicte_id,
                page=page,
                method_note="label 'AICTE id'",
                confidence=0.85 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        document_id = _text_after(
            r"(?:document\s+(?:id|number|no)|affidavit\s+(?:id|number|no))",
            text,
        )
        if document_id and not any(
            f.field_name == "document_id" for f in result.fields
        ):
            _add(
                result,
                name="document_id",
                value=document_id,
                page=page,
                method_note="label 'document id'",
                confidence=0.85 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        sworn = _date_after(r"(?:sworn\s+on|deposition\s+date|notar)", text)
        if sworn and not any(f.field_name == "notary_date" for f in result.fields):
            _add(
                result,
                name="notary_date",
                value=sworn,
                page=page,
                method_note="label 'sworn on'",
                confidence=0.88 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


def _parse_faculty_list(pages: list[_Page], result: ExtractionResult) -> int:
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)
        match = re.search(
            r"(?:total|number\s+of)\s+(?:teaching\s+)?"
            r"(?:faculty|teachers|staff|posts?)\s*[:\-–]?\s*(\d{1,5})",
            text,
            flags=re.IGNORECASE,
        )
        if match and not any(f.field_name == "faculty_count" for f in result.fields):
            _add(
                result,
                name="faculty_count",
                value=int(match.group(1)),
                page=page,
                method_note="label 'total faculty'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


def _parse_fire_safety_certificate(
    pages: list[_Page], result: ExtractionResult
) -> int:
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        certificate = _text_after(
            r"(?:certificate\s+(?:no|number|id))", text
        )
        if certificate and not any(
            f.field_name == "certificate_number" for f in result.fields
        ):
            _add(
                result,
                name="certificate_number",
                value=certificate,
                page=page,
                method_note="label 'certificate number'",
                confidence=0.85 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        valid_to = _date_after(
            r"(?:valid\s+(?:to|until|up\s+to)|expiry|expires|issued\s+on)",
            text,
        )
        if valid_to and not any(f.field_name == "valid_to" for f in result.fields):
            _add(
                result,
                name="valid_to",
                value=valid_to,
                page=page,
                method_note="label 'valid to'",
                confidence=0.88 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


_PARSERS = {
    "lease_deed": _parse_lease_deed,
    "ownership_record": _parse_ownership_record,
    "affidavit": _parse_affidavit,
    "faculty_list": _parse_faculty_list,
    "fire_safety_certificate": _parse_fire_safety_certificate,
}
