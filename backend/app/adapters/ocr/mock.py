"""Deterministic mock extractor.

It does not read the uploaded bytes. It returns canned values per document type so
the workflow, rules and rehearsal can be demonstrated and tested. Every response is
marked ``simulated=True`` and the API surfaces that flag; nothing here may be
presented as real OCR.
"""

from __future__ import annotations

from .base import ExtractedFieldCandidate, ExtractionResult

_CANNED: dict[str, list[tuple[str, object, int, float]]] = {
    "lease_deed": [
        ("valid_from", "2026-04-01", 1, 0.97),
        ("valid_to", "2028-03-31", 7, 0.93),
        ("issuing_authority", "Sub-Registrar, Demo District", 1, 0.88),
        ("lessee_name", "Example Institute of Technology", 2, 0.95),
        ("lessor_name", "Demo Land Holdings", 2, 0.91),
    ],
    "ownership_record": [
        ("lease_expiry", "2027-03-31", 3, 0.86),
        ("record_holder", "Example Institute of Technology", 1, 0.9),
    ],
    "affidavit": [
        ("institution_name", "Example Institute of Technology", 1, 0.94),
        ("aicte_id", "1-12345678", 1, 0.92),
        ("notary_date", "2026-04-12", 4, 0.89),
    ],
    "faculty_list": [
        ("faculty_count", 72, 2, 0.81),
    ],
}


class MockOCRExtractor:
    simulated = True

    def extract(self, *, doc_type: str, content: bytes, file_name: str) -> ExtractionResult:
        rows = _CANNED.get(doc_type, [])
        result = ExtractionResult(doc_type=doc_type, simulated=True)
        if not rows:
            result.warnings.append(
                f"no mock extraction profile for doc_type {doc_type!r}; "
                "manual field entry required"
            )
            return result
        for name, value, page, confidence in rows:
            result.fields.append(
                ExtractedFieldCandidate(
                    field_name=name,
                    value=value,
                    source_page=page,
                    source_span=f"page {page}",
                    method="mock_ocr",
                    confidence=confidence,
                    # Honest provenance: this reader never opened the file,
                    # so it has no box and no version to report (5.2).
                    bbox=None,
                    engine="mock",
                    engine_version=None,
                )
            )
        result.warnings.append("mock extraction — values are canned, not read from the file")
        return result
