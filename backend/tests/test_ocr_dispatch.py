"""Document uploads stay on the configured OCR adapter, including leases."""

from app.adapters.ocr.base import ExtractionResult
from app.services.ocr_service import DispatchingExtractor


class _RecordingExtractor:
    simulated = True

    def __init__(self):
        self.calls = []

    def extract(self, *, doc_type: str, content: bytes, file_name: str):
        self.calls.append((doc_type, content, file_name))
        return ExtractionResult(doc_type=doc_type, simulated=True)


def test_lease_upload_uses_the_configured_adapter_without_external_dispatch():
    delegate = _RecordingExtractor()
    wrapped = DispatchingExtractor(delegate)
    result = wrapped.extract(
        doc_type="lease_agreement",
        content=b"synthetic document bytes",
        file_name="synthetic-lease.pdf",
    )
    assert result.simulated is True
    assert delegate.calls == [(
        "lease_agreement", b"synthetic document bytes", "synthetic-lease.pdf"
    )]
