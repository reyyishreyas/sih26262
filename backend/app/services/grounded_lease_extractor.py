"""Backward-compatible local lease OCR facade.

Regular document uploads use ``ocr_service`` directly. This facade remains for
older call sites and deliberately delegates to the configured local reader;
API-key presence must never send an institution document to an external model.
"""

from __future__ import annotations

from ..adapters.ocr.base import ExtractionResult


class GroundedLeaseExtractor:
    """Compatibility wrapper around the deterministic local lease parser."""

    simulated = False

    def extract(self, *, content: bytes, file_name: str) -> ExtractionResult:
        from .ocr_service import get_ocr_extractor

        return get_ocr_extractor().extract(
            doc_type="lease_agreement",
            content=content,
            file_name=file_name,
        )
