"""Prometheus metrics for the HTTP surface.

The registry is explicit rather than the process-global default so tests and
embedded uses can reset state without unregistering collectors. Labels deliberately
use the matched route template (for example ``/api/v1/applications/{application_id}``)
and never the raw path, which would make cardinality unbounded.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "sih_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "sih_http_request_duration_seconds",
    "End-to-end HTTP request duration.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "sih_http_requests_in_progress",
    "HTTP requests currently being handled.",
    ("method",),
    registry=REGISTRY,
)
APP_INFO = Gauge(
    "sih_app_info",
    "Static application metadata; the value is always 1.",
    ("version", "environment"),
    registry=REGISTRY,
)
DATABASE_PROBE = Gauge(
    "sih_database_probe_success",
    "Last readiness probe result for a database path (1=ok, 0=failed).",
    ("component",),
    registry=REGISTRY,
)

ROUTE_UNMATCHED = "unmatched"


def route_label(scope: dict) -> str:
    """Return a bounded route label for a Starlette request scope."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    if scope.get("path") in {"/health", "/health/live", "/health/ready", "/metrics"}:
        return str(scope["path"])
    return ROUTE_UNMATCHED


def observe_request(
    *,
    method: str,
    route: str,
    status: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(
        max(0.0, duration_seconds)
    )


def record_app_info(version: str, environment: str) -> None:
    APP_INFO.labels(version=version, environment=environment).set(1)


def record_database_probe(component: str, ok: bool) -> None:
    DATABASE_PROBE.labels(component=component).set(1 if ok else 0)
