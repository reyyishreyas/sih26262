"""Document extraction engine selection and test injection.

The upload endpoint depends on the ``OCRExtractor`` contract, never on a
specific engine. The default is the real reader (pypdf text layer, Tesseract
OCR for scans and images); the mock stays selectable so tests and demos that
must not depend on the OCR binary can pin it explicitly.
"""

from __future__ import annotations

from ..adapters.ocr.base import OCRExtractor
from ..adapters.ocr.mock import MockOCRExtractor
from ..adapters.ocr.real import RealOCRExtractor
from ..core.config import Settings, get_settings

_extractor: OCRExtractor | None = None
_extractor_configured = False


def build_extractor(settings: Settings) -> OCRExtractor:
    if settings.ocr_engine == "mock":
        return MockOCRExtractor()
    if settings.ocr_engine == "real":
        return RealOCRExtractor()
    raise ValueError(f"unknown OCR engine {settings.ocr_engine!r}")


def get_ocr_extractor() -> OCRExtractor:
    global _extractor, _extractor_configured
    if not _extractor_configured:
        _extractor = build_extractor(get_settings())
        _extractor_configured = True
    return _extractor


def set_ocr_extractor(extractor: OCRExtractor | None) -> None:
    """Injects an extractor (tests, and the demo 'fake reader' switch)."""
    global _extractor, _extractor_configured
    _extractor = extractor
    _extractor_configured = True


def reset_ocr_extractor() -> None:
    """Restores the engine implied by the current settings."""
    global _extractor, _extractor_configured
    _extractor = None
    _extractor_configured = False
