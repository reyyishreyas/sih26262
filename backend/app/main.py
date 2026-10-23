"""FastAPI application factory."""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import (
    admin_access,
    alerts,
    applications,
    audit,
    auth,
    compliance,
    documents,
    evc,
    institutions,
    officer_dashboard,
    rehearsals,
    reports,
    undertakings,
    workflow,
)
from .core.clock import get_clock, iso
from .core.config import get_settings
from .core.context import current_request_id
from .core.db import (
    SessionLocal,
    create_all,
    dispose_engines,
    engine,
    readonly_engine,
    sim_engine,
)
from .core.logging import configure_logging
from .core.metrics import (
    REGISTRY,
    record_app_info,
    record_database_probe,
)
from .core.middleware import RequestContextMiddleware, error_payload
from .core.permissions import PermissionDenied

logger = logging.getLogger("sih26262")


def _database_probe() -> tuple[bool, dict[str, str]]:
    settings = get_settings()
    components: dict[str, str] = {}
    ok = True
    engines = {"operational": engine}
    # Only probe the rehearsal paths when they are actually distinct connections.
    # On SQLite the fallback URLs point at the same file and reporting them as
    # separate roles would overstate the isolation.
    if (
        settings.simulation_results_url
        and settings.simulation_results_url != settings.database_url
    ):
        engines["simulation_results"] = sim_engine
    if (
        settings.simulation_readonly_url
        and settings.simulation_readonly_url != settings.database_url
    ):
        engines["simulation_baseline"] = readonly_engine

    for name, candidate in engines.items():
        try:
            with candidate.connect() as connection:
                connection.execute(text("SELECT 1"))
                if candidate.dialect.name == "sqlite":
                    role = "sqlite"
                else:
                    role = connection.execute(text("SELECT current_user")).scalar()
            components[name] = f"ok:{role or 'unknown'}"
            record_database_probe(name, True)
        except Exception:  # pragma: no cover - operational path
            ok = False
            components[name] = "unavailable"
            record_database_probe(name, False)
            if settings.debug:
                logger.exception("database probe failed", extra={"database": name})
    return ok, components


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    if not settings.is_production and settings.jwt_secret in {
        "dev-only-change-me",
        "docker-dev-only-change-me",
    }:
        logger.warning(
            "using a development JWT secret; set SIH_JWT_SECRET before deployment"
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # SQLite is a development convenience. PostgreSQL deployments run Alembic
        # before the API starts and never perform DDL as the application role.
        create_all()
        if settings.seed_on_startup:
            from .services.seed import seed

            db = SessionLocal()
            try:
                seed(db)
            finally:
                db.close()
        logger.info(
            "startup complete",
            extra={
                "environment": settings.env,
                "clock": settings.clock_mode,
                "simulation_schema": settings.simulation_schema or "sqlite/default",
                "version": settings.app_version,
            },
        )
        try:
            yield
        finally:
            dispose_engines()
            logger.info("shutdown complete")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        description=(
            "AICTE approval workflow, compliance monitoring and alert management. "
            "The Approval Rehearsal Engine is isolated from operational writes. "
            "Prototype: synthetic data, mock OCR and mock notification delivery."
        ),
    )

    # Last added is outermost, so every response (including a rejected Host or a
    # CORS preflight) gets a request id and the security headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Range"],
        expose_headers=["X-Request-ID", "X-Total-Count"],
        max_age=600,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
    )
    app.add_middleware(RequestContextMiddleware, settings=settings)

    record_app_info(settings.app_version, settings.env)

    prefix = settings.api_prefix
    for module in (
        auth,
        applications,
        institutions,
        documents,
        compliance,
        rehearsals,
        workflow,
        undertakings,
        alerts,
        audit,
        officer_dashboard,
        admin_access,
        evc,
        reports,
    ):
        app.include_router(module.router, prefix=prefix)

    @app.exception_handler(PermissionDenied)
    async def permission_denied(_request: Request, exc: PermissionDenied):
        code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_403_FORBIDDEN
        return JSONResponse(
            status_code=code,
            content=error_payload(exc.message, exc.code, current_request_id()),
        )

    from .services.rehearsal_service import OverrideRejected
    from .services.rule_engine import InvalidRuleDefinition

    @app.exception_handler(OverrideRejected)
    async def override_rejected(_request: Request, exc: OverrideRejected):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_payload(
                str(exc), "override_rejected", current_request_id()
            ),
        )

    @app.exception_handler(InvalidRuleDefinition)
    async def invalid_rule(_request: Request, exc: InvalidRuleDefinition):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_payload(
                str(exc), "invalid_rule_definition", current_request_id()
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.detail, "http_error", current_request_id()),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_payload(
                jsonable_encoder(exc.errors()), "validation_error", current_request_id()
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception):
        logger.exception("unhandled application error")
        settings_ = get_settings()
        detail = str(exc) if settings_.debug else "internal server error"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(detail, "internal_error", current_request_id()),
        )

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> Response:
        if not settings.metrics_enabled:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error_payload("not found", "http_error", current_request_id()),
            )
        expected = settings.metrics_token
        if expected:
            authorization = request.headers.get("authorization", "")
            supplied = (
                authorization[7:]
                if authorization.lower().startswith("bearer ")
                else ""
            )
            header_token = request.headers.get("x-metrics-token", "")
            if not (
                hmac.compare_digest(supplied, expected)
                or hmac.compare_digest(header_token, expected)
            ):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content=error_payload(
                        "metrics authentication required",
                        "forbidden",
                        current_request_id(),
                    ),
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/health/live", tags=["health"])
    def live() -> dict:
        return {"status": "ok", "version": settings.app_version}

    @app.get("/health/ready", tags=["health"])
    def ready(response: Response) -> dict:
        ready_now, components = _database_probe()
        response.status_code = (
            status.HTTP_200_OK if ready_now else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return {
            "status": "ready" if ready_now else "not_ready",
            "components": components,
            "version": settings.app_version,
        }

    @app.get("/health", tags=["health"])
    def health() -> dict:
        database_ok, components = _database_probe()
        role = "unknown"
        operational = components.get("operational", "")
        if operational.startswith("ok:"):
            role = operational.split(":", 1)[1]
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "unavailable",
            "database_role": role,
            "components": components,
            "simulation_schema": settings.simulation_schema or None,
            "clock": iso(get_clock().now()),
            "environment": settings.env,
            "version": settings.app_version,
        }

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.docs_enabled else None,
            "health": {"live": "/health/live", "ready": "/health/ready"},
            "api": settings.api_prefix,
            "disclosures": [
                "Synthetic demo data only.",
                "OCR and notification delivery are mock adapters.",
                "Load Factor is intentionally null until its formula and test matrix are validated.",
                "Automated findings are decision support; the competent authority decides.",
            ],
        }

    return app


app = create_app()
