"""OpenRouter low-confidence vision fallback.

This adapter only suggests page-grounded field candidates. It never returns a
compliance or workflow decision. External processing requires both the global
switch and trusted public/synthetic provenance from server-side code.
"""

from __future__ import annotations

import base64
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ...adapters.ocr.base import ExtractedFieldCandidate
from ...core.clock import get_clock
from ...core.config import Settings
from ...models import ExternalCallLog
from ...services.fuzzy_grounding import ground_candidates

_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_ALLOWED_MIME_TYPES = {"image/png", "image/jpeg"}
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "value": {"type": "string"},
                    "source_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_page": {"type": "integer", "minimum": 1},
                },
                "required": [
                    "field_name", "value", "source_quote", "confidence", "source_page"
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["fields"],
    "additionalProperties": False,
}


@dataclass
class VisionFallbackResult:
    status: str
    candidates: list[ExtractedFieldCandidate] = field(default_factory=list)
    warning: str | None = None


def _parse_candidates(payload: str, *, model: str, page_number: int) -> list[ExtractedFieldCandidate]:
    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(body, dict) or set(body) != {"fields"} or not isinstance(body["fields"], list):
        raise ValueError("schema_mismatch")

    candidates: list[ExtractedFieldCandidate] = []
    seen: set[str] = set()
    expected = {"field_name", "value", "source_quote", "confidence", "source_page"}
    for item in body["fields"]:
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError("schema_mismatch")
        name = item["field_name"]
        value = item["value"]
        quote = item["source_quote"]
        confidence = item["confidence"]
        source_page = item["source_page"]
        if (
            not isinstance(name, str) or not name.strip() or len(name) > 64
            or not isinstance(value, str) or not value.strip()
            or not isinstance(quote, str) or not quote.strip()
            or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
            or isinstance(source_page, bool) or not isinstance(source_page, int)
            or source_page != page_number
        ):
            raise ValueError("schema_mismatch")
        normalized_name = name.strip()
        if normalized_name in seen:
            raise ValueError("duplicate_field")
        seen.add(normalized_name)
        candidates.append(
            ExtractedFieldCandidate(
                field_name=normalized_name,
                value={"value": value.strip(), "source_quote": quote.strip()},
                source_page=source_page,
                source_span="OpenRouter vision source quote",
                method="openrouter_vision",
                confidence=float(confidence),
                engine="openrouter",
                engine_version=model,
            )
        )
    return candidates


def extract_low_confidence_page(
    *,
    db: Session,
    settings: Settings,
    image: bytes,
    mime_type: str,
    page_number: int,
    ocr_confidence: float,
    page_text: str,
    trusted_public_or_synthetic: bool,
    application_id: str | None = None,
    document_id: str | None = None,
    request_id: str | None = None,
) -> VisionFallbackResult:
    """Ask OpenRouter only for eligible low-confidence public/synthetic pages."""
    if not settings.openrouter_enabled:
        return VisionFallbackResult("disabled", warning="External vision fallback is disabled.")
    if not trusted_public_or_synthetic:
        return VisionFallbackResult("ineligible", warning="This document is not approved for external processing.")
    if not settings.openrouter_api_key:
        return VisionFallbackResult("unconfigured", warning="OpenRouter is enabled but its API key is not configured.")
    if ocr_confidence >= settings.openrouter_confidence_threshold:
        return VisionFallbackResult("not_needed")
    if (
        page_number < 1
        or mime_type not in _ALLOWED_MIME_TYPES
        or not image
        or not math.isfinite(ocr_confidence)
        or not 0 <= ocr_confidence <= 1
    ):
        return VisionFallbackResult("invalid_input", warning="The vision fallback input is invalid.")

    log = ExternalCallLog(
        application_id=application_id,
        document_id=document_id,
        provider="openrouter",
        model=settings.openrouter_model,
        attempt=1,
        pages=1,
        latency_ms=0,
        status="started",
        request_id=request_id,
        created_at=get_clock().now(),
    )
    db.add(log)
    db.commit()  # retain evidence of an attempt even if the process stops mid-call

    started = time.monotonic()
    try:
        encoded = base64.b64encode(image).decode("ascii")
        prompt = (
            "Read only the visible fields on this page. Return candidate values and exact "
            "source quotes. Never assess compliance, approve, reject, return, or decide a "
            "workflow action. If a value or exact quote is unclear, omit that field. "
            f"This is page {page_number}."
        )
        body = {
            "model": settings.openrouter_model,
            "temperature": 0,
            "max_tokens": 1200,
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "page_field_candidates",
                    "strict": True,
                    "schema": _OUTPUT_SCHEMA,
                },
            },
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{encoded}"
                    }},
                ],
            }],
        }
        request = urllib.request.Request(
            _CHAT_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=settings.openrouter_timeout_seconds) as response:
            response_bytes = response.read(256_001)
        if len(response_bytes) > 256_000:
            raise ValueError("response_too_large")
        response_data = json.loads(response_bytes.decode("utf-8"))
        output = response_data["choices"][0]["message"]["content"]
        if not isinstance(output, str):
            raise ValueError("schema_mismatch")
        candidates = _parse_candidates(output, model=settings.openrouter_model, page_number=page_number)
        warnings = ground_candidates(candidates, [page_text])
        log.status = "succeeded"
        log.failure_code = None
        return VisionFallbackResult(
            "succeeded",
            candidates=candidates,
            warning=" ".join(warnings) or None,
        )
    except urllib.error.HTTPError as exc:
        log.status = "failed"
        log.failure_code = f"http_{exc.code}"
        return VisionFallbackResult("failed", warning="Vision fallback request failed.")
    except (urllib.error.URLError, TimeoutError):
        log.status = "failed"
        log.failure_code = "transport_error"
        return VisionFallbackResult("failed", warning="Vision fallback request failed.")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        log.status = "failed"
        log.failure_code = "invalid_response"
        return VisionFallbackResult("failed", warning="Vision fallback response could not be validated.")
    except Exception:
        log.status = "failed"
        log.failure_code = "provider_error"
        return VisionFallbackResult("failed", warning="Vision fallback request failed.")
    finally:
        log.latency_ms = int((time.monotonic() - started) * 1000)
        db.add(log)
        db.commit()
