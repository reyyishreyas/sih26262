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
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
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
# A page that yields only a few machine characters is usually a scanned page
# with an invisible/partial OCR layer. Render those pages as well, then keep
# whichever reader actually recovered more text.
_MIN_USABLE_TEXT_CHARS = 24

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
class _Line:
    """One rendered line of a page and its box in normalised page units.

    ``bbox`` uses fractions of the page (0..1), ``origin: top_left`` and
    ``level: line`` — the shape the API stores and the UI highlights
    (FR-48). For a text-layer line the *width* is estimated (char count x
    0.5 em, a Helvetica-ish average): pypdf reports positions, not glyph
    advances. It is a highlight aid, never a measurement.
    """

    text: str
    bbox: dict


@dataclass
class _Page:
    """One page of readable text plus how it was read."""

    number: int
    text: str
    method: str
    confidence: float
    # Provenance (5.2): which program read this page and at which version —
    # NULL only when no program could be identified.
    engine: str | None = None
    engine_version: str | None = None
    lines: list[_Line] = field(default_factory=list)


@lru_cache(maxsize=1)
def _pypdf_version() -> str | None:
    """The installed pypdf's own version, or None if it cannot be read."""
    try:
        import pypdf

        return str(getattr(pypdf, "__version__", None) or None) or None
    except Exception:  # noqa: BLE001 - provenance must never break a read
        return None


@lru_cache(maxsize=1)
def _tesseract_version() -> str | None:
    """The installed Tesseract binary's version, or None.

    Shells out once per process (``lru_cache``); called only after OCR has
    already succeeded, so the binary exists by then.
    """
    try:
        import pytesseract

        return str(pytesseract.get_tesseract_version()).strip() or None
    except Exception:  # noqa: BLE001 - provenance must never break a read
        return None


def _alnum(text: str) -> str:
    """Matching key: case- and punctuation-insensitive.

    Values are stored normalised (``2026-04-12``) while pages read
    ``12 April 2026``; comparing alnum-only lets a value or its parser
    label be found on the line it was read from.
    """
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _unit_box(x: float, y: float, width: float, height: float) -> dict:
    """Clamps and rounds a box into the page's unit frame (top-left origin).

    Rounding happens *before* the fit clamp, so ``x + width`` and
    ``y + height`` can never exceed 1 after rounding.
    """
    x = round(min(max(x, 0.0), 1.0), 4)
    y = round(min(max(y, 0.0), 1.0), 4)
    width = round(min(max(width, 0.0), 1.0 - x), 4)
    height = round(min(max(height, 0.0), 1.0 - y), 4)
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "origin": "top_left",
        "level": "line",
    }


def _pdf_box(
    x0: float,
    baseline: float,
    x1: float,
    font_size: float,
    page_width: float,
    page_height: float,
    llx: float,
    lly: float,
) -> dict:
    """A text-layer line box: PDF user space (y up from the bottom) into
    top-left normalised fractions. The box spans ascender to descender
    (0.75 em above the baseline, 0.25 em below)."""
    return _unit_box(
        x=(x0 - llx) / page_width,
        y=1.0 - ((baseline + 0.75 * font_size) - lly) / page_height,
        width=(x1 - x0) / page_width,
        height=font_size / page_height,
    )


def _image_box(
    x0: float, y0: float, x1: float, y1: float, width: float, height: float
) -> dict:
    """A scanned-line box: pixel coordinates (already top-left origin) into
    normalised fractions of the image that was actually OCR'd."""
    return _unit_box(
        x=x0 / width, y=y0 / height, width=(x1 - x0) / width, height=(y1 - y0) / height
    )


# Average Helvetica advance per character, as a fraction of the font size.
# pypdf gives positions but not glyph advances, so text-layer line widths
# are estimated with this (see _Line.docstring) — a highlight aid only.
_AVG_CHAR_EM = 0.5


def _group_pdf_lines(
    chunks: list[tuple[str, float, float, float]],
    *,
    page_width: float,
    page_height: float,
    llx: float,
    lly: float,
) -> list[_Line]:
    """Groups visitor chunks that share a baseline into line boxes.

    Two chunks belong to one line when their baselines are within half a
    font size — PDF producers split a visual line across many text-showing
    operations, and a highlight must cover the whole line, not a fragment.
    """
    if not chunks or page_width <= 0 or page_height <= 0:
        return []
    ordered = sorted(chunks, key=lambda chunk: (-chunk[2], chunk[0]))
    groups: list[list[tuple[str, float, float, float]]] = []
    for chunk in ordered:
        _, _, y, font_size = chunk
        if groups and abs(groups[-1][0][2] - y) <= min(font_size, groups[-1][0][3]) * 0.5:
            groups[-1].append(chunk)
        else:
            groups.append([chunk])

    lines: list[_Line] = []
    for group in groups:
        font_size = max(chunk[3] for chunk in group)
        x0 = min(chunk[1] for chunk in group)
        x1 = max(chunk[1] + len(chunk[0]) * chunk[3] * _AVG_CHAR_EM for chunk in group)
        baseline = sum(chunk[2] for chunk in group) / len(group)
        lines.append(
            _Line(
                text=" ".join(chunk[0] for chunk in group),
                bbox=_pdf_box(
                    x0,
                    baseline,
                    x1,
                    font_size,
                    page_width,
                    page_height,
                    llx,
                    lly,
                ),
            )
        )
    # Top-to-bottom reading order (y is up in PDF space, so descending).
    lines.sort(key=lambda line: line.bbox["y"])
    return lines


def _group_ocr_lines(
    data: dict, *, page_width: float, page_height: float
) -> list[_Line]:
    """Groups Tesseract word boxes into line boxes by its own line ids.

    ``image_to_data`` labels each word with ``(block, par, line)``; words
    sharing that id are one visual line, so the union of their pixel
    rectangles *is* the line box — exact geometry, no estimation.
    """
    if page_width <= 0 or page_height <= 0:
        return []
    texts = [str(value) for value in data.get("text", [])]
    line_nums = data.get("line_num", [])
    block_nums = data.get("block_num", [])
    par_nums = data.get("par_num", [])
    groups: dict[tuple[object, object, object], list[int]] = {}
    for index, key in enumerate(line_nums):
        if index >= len(texts) or not texts[index].strip():
            continue
        group_key = (block_nums[index], par_nums[index], key)
        groups.setdefault(group_key, []).append(index)

    lines: list[_Line] = []
    for word_indexes in groups.values():
        words = [texts[index] for index in word_indexes]
        lefts = [float(data["left"][index]) for index in word_indexes]
        tops = [float(data["top"][index]) for index in word_indexes]
        widths = [float(data["width"][index]) for index in word_indexes]
        heights = [float(data["height"][index]) for index in word_indexes]
        lines.append(
            _Line(
                text=" ".join(words),
                bbox=_image_box(
                    min(lefts),
                    min(tops),
                    max(
                        left + width
                        for left, width in zip(lefts, widths, strict=False)
                    ),
                    max(
                        top + height
                        for top, height in zip(tops, heights, strict=False)
                    ),
                    page_width,
                    page_height,
                ),
            )
        )
    lines.sort(key=lambda line: line.bbox["y"])
    return lines


def _locate_line(lines: list[_Line], *needles: str) -> _Line | None:
    """The first line containing any needle (alnum match).

    Tries the needles in order, so the stored value is preferred over the
    parser's label. Answers ``None`` when nothing matches — a box we cannot
    place is a box we must not invent (the UI then simply shows no
    highlight).
    """
    for needle in needles:
        key = _alnum(needle)
        if len(key) < 3:
            # Too short to place honestly: "id" or "no" would hit any line.
            continue
        for line in lines:
            if key in _alnum(line.text):
                return line
    return None


def _usable_text_chars(text: str) -> int:
    """Count letters/digits, ignoring layout punctuation and whitespace."""
    return sum(character.isalnum() for character in text)


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
        text_pages: dict[int, _Page] = {}
        scan_candidates: set[int] = set()

        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            for index, pdf_page in enumerate(reader.pages, start=1):
                chunks: list[tuple[str, float, float, float]] = []

                # Positions (5.2, FR-48): pypdf reports every text-showing
                # operation through this visitor — text plus its origin
                # (tm[4], tm[5]) and font size. The returned page text is
                # unchanged; the chunks only add where each piece sits.
                def _visitor(
                    text: str,
                    cm: list[float],
                    tm: list[float],
                    font_dict: object,
                    font_size: float,
                    _chunks: list[tuple[str, float, float, float]] = chunks,
                ) -> None:
                    stripped = text.strip()
                    if not stripped:
                        return
                    scale = (cm[0] ** 2 + cm[1] ** 2) ** 0.5 or 1.0
                    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                    _chunks.append((stripped, x, y, font_size * scale))

                try:
                    text = (pdf_page.extract_text(visitor_text=_visitor) or "").strip()
                    if text:
                        box = pdf_page.mediabox
                        text_pages[index] = _Page(
                            number=index,
                            text=text,
                            method="pdf_text",
                            confidence=_TEXT_LAYER_CONFIDENCE,
                            engine="pypdf",
                            engine_version=_pypdf_version(),
                            lines=_group_pdf_lines(
                                chunks,
                                page_width=float(box.width),
                                page_height=float(box.height),
                                llx=float(box.left),
                                lly=float(box.bottom),
                            ),
                        )
                        if _usable_text_chars(text) < _MIN_USABLE_TEXT_CHARS:
                            scan_candidates.add(index)
                    else:
                        scan_candidates.add(index)
                except Exception as exc:  # noqa: BLE001 - continue with other pages
                    scan_candidates.add(index)
                    warnings.append(
                        f"Text on PDF page {index} could not be read ({type(exc).__name__}); trying page OCR."
                    )
        except Exception as exc:  # noqa: BLE001 - corrupt files must not 500
            warnings.append(
                "This PDF could not be opened as a PDF "
                f"({type(exc).__name__}). If it is a scan, try re-saving it "
                "as a PDF, or upload a photo of the document instead."
            )
            return [], warnings

        if not scan_candidates:
            return list(text_pages.values()), warnings

        # Render only pages with no/partial text, so mixed digital + scanned
        # PDFs are fully indexed without rasterising every text page.
        ocr_pages, ocr_warnings = self._read_pdf_as_scans(
            content, result, page_numbers=scan_candidates
        )
        warnings.extend(ocr_warnings)
        ocr_by_page = {page.number: page for page in ocr_pages}
        pages: list[_Page] = []
        for page_number in sorted(set(text_pages) | scan_candidates):
            text_page = text_pages.get(page_number)
            ocr_page = ocr_by_page.get(page_number)
            if ocr_page is not None and (
                text_page is None
                or _usable_text_chars(ocr_page.text) > _usable_text_chars(text_page.text)
            ):
                pages.append(ocr_page)
            elif text_page is not None:
                pages.append(text_page)
        if ocr_pages:
            result.warnings.append(
                "One or more PDF pages had no usable text layer and were read with OCR. "
                "Scanned text can be less reliable; check every extracted detail."
            )
        return pages, warnings

    def _read_pdf_as_scans(
        self, content: bytes, result: ExtractionResult, *, page_numbers: set[int]
    ) -> tuple[list[_Page], list[str]]:
        warnings: list[str] = []
        pages: list[_Page] = []

        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(BytesIO(content))
            page_count = len(document)
            for page_number in sorted(page_numbers):
                if page_number < 1 or page_number > page_count:
                    warnings.append(f"PDF page {page_number} was outside the readable page range.")
                    continue
                bitmap = document[page_number - 1].render(scale=_RENDER_SCALE)
                image = bitmap.to_pil()
                page = self._ocr_image(image, page_number=page_number, result=result)
                if page is not None:
                    pages.append(page)
        except Exception as exc:  # noqa: BLE001 - corrupt files must not 500
            warnings.append(
                "This PDF has no readable text and its pages could not be "
                f"prepared for scanning ({type(exc).__name__})."
            )
            return [], warnings

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
            engine="tesseract",
            engine_version=_tesseract_version(),
            # Exact pixel geometry of each line Tesseract identified —
            # normalised against the image that was actually OCR'd (after
            # any upscaling, so the coordinates line up).
            lines=_group_ocr_lines(
                data, page_width=float(image.width), page_height=float(image.height)
            ),
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


def _label_needles(method_note: str) -> list[str]:
    """The parser's own label words from a note like ``label 'lessee'``.

    Used as the *second* locating needle: a normalised value (an ISO date)
    never appears verbatim on the page, but the label it was read after
    does — the value sits on the label's line by construction of
    ``_text_after`` / ``_date_after``.
    """
    match = re.findall(r"'([^']+)'", method_note)
    return match or [method_note]


def _field_label_needles(name: str) -> list[str]:
    """Known source labels for parsers that normalise their stored values."""
    if name in {"valid_from", "valid_to"}:
        return [
            "valid from", "lease starts", "lease commences", "commencing",
            "term from", "valid to", "valid until", "valid till",
            "valid up to", "expiry date", "expiry", "expires", "term to",
            "term until", "issued on",
        ]
    return []


def _add(
    result: ExtractionResult,
    *,
    name: str,
    value: object,
    page: _Page,
    method_note: str,
    confidence: float,
) -> None:
    # Where: the stored value on a line, else the parser's label line,
    # else no box at all — an unplaceable box would send the highlight to
    # the wrong part of the page, which is worse than no highlight.
    located_line = _locate_line(
        page.lines,
        str(value),
        *_label_needles(method_note),
        *_field_label_needles(name),
    )
    bbox = located_line.bbox if located_line else None
    result.fields.append(
        ExtractedFieldCandidate(
            field_name=name,
            value=value,
            source_page=page.number,
            source_span=(located_line.text[:512] if located_line else method_note),
            method=page.method,
            confidence=round(min(confidence, page.confidence), 2),
            bbox=bbox,
            engine=page.engine,
            engine_version=page.engine_version,
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
            r"(?:valid\s+(?:to|until|till|up\s+to)|expiry(?:\s+date)?|expires|term\s+(?:to|until))",
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

        property_address = _text_after(
            r"(?:property\s+address|premises\s+address|address\s+of\s+(?:the\s+)?premises|leased\s+premises)",
            text,
        )
        if property_address and not any(
            f.field_name == "property_address" for f in result.fields
        ):
            _add(
                result,
                name="property_address",
                value=property_address,
                page=page,
                method_note="label 'property address'",
                confidence=0.86 if page.method == "pdf_text" else page.confidence,
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


def _parse_eoa_letter(pages: list[_Page], result: ExtractionResult) -> int:
    """The EoA letter is the demo's master-record stand-in (PRD §8 step 1).

    The field names are the labelled placeholder paths the advisory
    crosschecks read (``rules/evidence_crosschecks.json``). No field is an
    official APH mapping — the letter template is unverified (PRD §19 Q13)
    and every value stays an extraction candidate.
    """
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        for field_name, label in (
            ("institution_name", r"institution(?:\s+name)?"),
            ("trust_name", r"trust(?:\s+name)?"),
            ("institution_address", r"address(?:es)?"),
            ("survey_number", r"survey"),
            ("pid", r"pid"),
            ("institution_type", r"institution\s+type"),
        ):
            if any(f.field_name == field_name for f in result.fields):
                continue
            value = _text_after(label, text)
            if not value:
                continue
            _add(
                result,
                name=field_name,
                value=value,
                page=page,
                method_note=f"label '{field_name.replace('_', ' ')}'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1

        if not any(f.field_name == "approved_programmes" for f in result.fields):
            programmes = _text_after(r"approved\s+programmes", text)
            if programmes:
                # The value stays the visual line's comma list: the site
                # check splits names off it (see _programme_names), and a
                # plain string gives `_locate` a needle it can actually
                # place — a box for the highlight, never an invented one.
                _add(
                    result,
                    name="approved_programmes",
                    value=programmes,
                    page=page,
                    method_note="label 'approved programmes'",
                    confidence=0.9 if page.method == "pdf_text" else page.confidence,
                )
                found += 1
    return found


def _parse_university_noc(pages: list[_Page], result: ExtractionResult) -> int:
    """Format-2 NOC fields (FR-42's compared side). Same placeholder caveat
    as ``_parse_eoa_letter``: labels follow the synthetic fixture shape."""
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        for field_name, label in (
            ("institution_name", r"institution(?:\s+name)?"),
            ("trust_name", r"trust(?:\s+name)?"),
            ("old_address", r"old\s+address(?:es)?"),
            ("survey_number", r"survey"),
            ("pid", r"pid"),
            ("institution_type", r"institution\s+type"),
            ("affiliating_university", r"affiliating\s+university"),
            ("new_region", r"new\s+region"),
        ):
            if any(f.field_name == field_name for f in result.fields):
                continue
            value = _text_after(label, text)
            if not value:
                continue
            _add(
                result,
                name=field_name,
                value=value,
                page=page,
                method_note=f"label '{field_name.replace('_', ' ')}'",
                confidence=0.9 if page.method == "pdf_text" else page.confidence,
            )
            found += 1
    return found


def _parse_format_3_resolution(pages: list[_Page], result: ExtractionResult) -> int:
    """Format-3 resolution fields (FR-44's compared side).

    ``resolution_text`` keeps the board's wording verbatim so the
    partial-shifting phrase check can find its configured phrase inside it.
    """
    found = 0
    for page in pages:
        text = _normalise_ocr(page.text)

        if not any(f.field_name == "resolution_text" for f in result.fields):
            value = _text_after(r"board\s+resolution", text)
            if value:
                _add(
                    result,
                    name="resolution_text",
                    value=value,
                    page=page,
                    method_note="label 'board resolution'",
                    confidence=0.9 if page.method == "pdf_text" else page.confidence,
                )
                found += 1

        if not any(f.field_name == "programmes_covered" for f in result.fields):
            programmes = _text_after(r"covered\s+programmes", text)
            if programmes:
                _add(
                    result,
                    name="programmes_covered",
                    value=programmes,
                    page=page,
                    method_note="label 'covered programmes'",
                    confidence=0.9 if page.method == "pdf_text" else page.confidence,
                )
                found += 1
    return found


_PARSERS = {
    "lease_deed": _parse_lease_deed,
    "lease_agreement": _parse_lease_deed,
    "ownership_record": _parse_ownership_record,
    "affidavit": _parse_affidavit,
    "faculty_list": _parse_faculty_list,
    "fire_safety_certificate": _parse_fire_safety_certificate,
    "eoa_letter": _parse_eoa_letter,
    "university_noc": _parse_university_noc,
    "format_3_resolution": _parse_format_3_resolution,
}
