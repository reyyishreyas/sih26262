"""OCR / text-extraction adapter contract.

The platform never depends on a specific OCR vendor. The prototype ships a mock that
returns plausible, clearly-labelled fields so the rule engine can be exercised
end-to-end. Replacing it is a configuration change, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ExtractedFieldCandidate:
    field_name: str
    value: object
    source_page: int | None = None
    source_span: str | None = None
    method: str = "mock_ocr"
    confidence: float = 0.0
    # Provenance (5.2): where on the page the value was read, and which
    # program read it. NULL/None whenever the engine cannot say — the mock
    # never read a page so it has no box, seeded rows ran no engine at all.
    bbox: dict | None = None
    engine: str | None = None
    engine_version: str | None = None
    # Grounding (5.3, FR-40): for MODEL-produced values only, whether the
    # text was found on the page — "grounded" or "REVIEW_REQUIRED"; None
    # for OCR/mock values (nothing to ground them against) and for rows
    # that predate the check.
    grounding: str | None = None


@dataclass
class ExtractionResult:
    doc_type: str
    fields: list[ExtractedFieldCandidate] = field(default_factory=list)
    simulated: bool = True
    warnings: list[str] = field(default_factory=list)
    # The text the reader actually saw, page by page. Classification
    # (Phase 5.1, FR-38) needs the words themselves; a reader that does not
    # read bytes (the mock) leaves this empty and classification honestly
    # answers "no_text" instead of guessing.
    page_texts: list[str] = field(default_factory=list)


class OCRExtractor(Protocol):
    def extract(self, *, doc_type: str, content: bytes, file_name: str) -> ExtractionResult:
        ...
