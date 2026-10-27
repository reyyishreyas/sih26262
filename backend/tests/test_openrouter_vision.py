from __future__ import annotations

import json
import math
from contextlib import contextmanager

from sqlalchemy import select

from app.adapters.vision import openrouter
from app.core.config import Settings
from app.models import ExternalCallLog


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "openrouter_enabled": True,
        "openrouter_api_key": "test-only-key",
        "openrouter_model": "test/vision-model",
        **overrides,
    }
    return Settings(**values)


def test_key_alone_does_not_enable_external_calls(db, monkeypatch):
    settings = _settings(openrouter_enabled=False)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("provider must not be called while disabled")

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fail_if_called)
    result = openrouter.extract_low_confidence_page(
        db=db,
        settings=settings,
        image=b"image-bytes",
        mime_type="image/png",
        page_number=1,
        ocr_confidence=0.2,
        page_text="",
        trusted_public_or_synthetic=True,
    )
    assert result.status == "disabled"
    assert db.scalar(select(ExternalCallLog.id)) is None


def test_nonpublic_and_high_confidence_pages_never_leave_the_system(db, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("ineligible page must not be sent")

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fail_if_called)
    common = {
        "db": db,
        "settings": _settings(),
        "image": b"image-bytes",
        "mime_type": "image/png",
        "page_number": 1,
        "ocr_confidence": 0.2,
        "page_text": "some page words",
    }
    private = openrouter.extract_low_confidence_page(
        **common, trusted_public_or_synthetic=False
    )
    confident = openrouter.extract_low_confidence_page(
        **{**common, "ocr_confidence": 0.9}, trusted_public_or_synthetic=True
    )
    assert private.status == "ineligible"
    assert confident.status == "not_needed"
    assert db.scalar(select(ExternalCallLog.id)) is None


def test_invalid_ocr_confidence_never_triggers_external_processing(db, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("invalid confidence must not be sent")

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fail_if_called)
    result = openrouter.extract_low_confidence_page(
        db=db,
        settings=_settings(),
        image=b"synthetic-image",
        mime_type="image/png",
        page_number=1,
        ocr_confidence=math.nan,
        page_text="A public synthetic page",
        trusted_public_or_synthetic=True,
    )
    assert result.status == "invalid_input"
    assert db.scalar(select(ExternalCallLog.id)) is None


def test_low_confidence_public_page_uses_json_schema_and_logs_metadata(db, monkeypatch):
    response_text = json.dumps({
        "choices": [{"message": {"content": json.dumps({"fields": [{
            "field_name": "institution_name",
            "value": "ABC University",
            "source_quote": "ABC University",
            "confidence": 0.88,
            "source_page": 2,
        }]})}}]
    }).encode()
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            assert limit == 256_001
            return response_text

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["auth"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fake_urlopen)
    result = openrouter.extract_low_confidence_page(
        db=db,
        settings=_settings(),
        image=b"synthetic-page-image",
        mime_type="image/png",
        page_number=2,
        ocr_confidence=0.4,
        page_text="ABC University approval record",
        trusted_public_or_synthetic=True,
        application_id="app-main-0001",
        request_id="test-request",
    )
    assert result.status == "succeeded"
    assert result.candidates[0].grounding == "grounded"
    assert captured["auth"] == "Bearer test-only-key"
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["provider"]["require_parameters"] is True
    assert "data:image/png;base64," in captured["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert captured["timeout"] == 20

    log = db.scalar(select(ExternalCallLog))
    assert log.provider == "openrouter"
    assert log.model == "test/vision-model"
    assert log.application_id == "app-main-0001"
    assert log.pages == 1
    assert log.status == "succeeded"
    assert log.failure_code is None
    assert log.request_id == "test-request"
    assert not hasattr(log, "prompt")
    assert not hasattr(log, "response")


def test_invalid_model_response_is_failed_and_still_logged(db, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"choices":[{"message":{"content":"not-json"}}]}'

    @contextmanager
    def fake_urlopen(*_args, **_kwargs):
        yield Response()

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fake_urlopen)
    result = openrouter.extract_low_confidence_page(
        db=db,
        settings=_settings(),
        image=b"synthetic-page-image",
        mime_type="image/jpeg",
        page_number=1,
        ocr_confidence=0.1,
        page_text="This is a synthetic page",
        trusted_public_or_synthetic=True,
    )
    assert result.status == "failed"
    log = db.scalar(select(ExternalCallLog))
    assert log.status == "failed"
    assert log.failure_code == "invalid_response"
