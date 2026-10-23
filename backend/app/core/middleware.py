"""HTTP middleware: request ids, access logs and baseline security headers."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .context import reset_request_id, set_request_id
from .http import client_ip
from .metrics import (
    HTTP_REQUESTS_IN_PROGRESS,
    observe_request,
    route_label,
)

logger = logging.getLogger("sih26262.http")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _security_headers(settings: Settings, request_id: str) -> dict[str, str]:
    headers = {
        "X-Request-ID": request_id,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
        "Content-Security-Policy": "frame-ancestors 'none'",
    }
    if settings.is_production and settings.hsts_seconds:
        headers["Strict-Transport-Security"] = (
            f"max-age={settings.hsts_seconds}; includeSubDomains"
        )
    return headers


class RequestContextMiddleware:
    """Pure ASGI middleware so it works for every route, including errors."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)

        method = scope.get("method", "")
        path = scope.get("path", "")
        started = time.perf_counter()
        status_code = 500
        response_started = False
        no_store = (
            path.startswith(self.settings.api_prefix)
            or path.startswith("/health")
            or path.startswith("/metrics")
        )
        # Scrapes are intentionally excluded from request metrics; otherwise the
        # scrape interval becomes a visibly dominant traffic source.
        measure = path != "/metrics"
        if measure:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers.update(_security_headers(self.settings, request_id))
                if no_store:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "unhandled request error",
                extra={
                    "http": {
                        "method": method,
                        "path": path,
                        "status": 500,
                    }
                },
            )
            if self.settings.debug or response_started:
                raise
            status_code = 500
            body = json.dumps(
                {
                    "detail": "internal server error",
                    "code": "internal_error",
                    "request_id": request_id,
                }
            ).encode("utf-8")
            raw_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                *[
                    (key.encode("latin-1"), value.encode("latin-1"))
                    for key, value in _security_headers(
                        self.settings, request_id
                    ).items()
                ],
            ]
            if no_store:
                raw_headers.append((b"cache-control", b"no-store"))
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": raw_headers,
                }
            )
            await send({"type": "http.response.body", "body": body})
        finally:
            duration_seconds = time.perf_counter() - started
            duration_ms = round(duration_seconds * 1000, 2)
            if measure:
                observe_request(
                    method=method,
                    route=route_label(scope),
                    status=status_code,
                    duration_seconds=duration_seconds,
                )
                HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            logger.info(
                "http.request",
                extra={
                    "http": {
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip(scope, self.settings),
                    }
                },
            )
            reset_request_id(token)


def error_payload(
    detail: Any, code: str, request_id: str | None
) -> dict[str, Any]:
    return {"detail": detail, "code": code, "request_id": request_id}
