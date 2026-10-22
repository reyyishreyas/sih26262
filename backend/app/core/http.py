"""Small HTTP helpers shared by middleware and authentication."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import Scope

from .config import Settings


def client_ip(scope: Scope, settings: Settings) -> str:
    """Return the caller address.

    ``X-Forwarded-For`` is only trusted when the operator explicitly enables it;
    otherwise any client could choose the address used for throttling.
    """
    if settings.trust_proxy_headers:
        forwarded = Headers(scope=scope).get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            if candidate:
                return candidate
    client = scope.get("client")
    return client[0] if client else "unknown"
