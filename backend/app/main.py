"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import (
    admin_access,
    alerts,
    applications,
    audit,
    auth,
    compliance,
    documents,
    officer_dashboard,
    rehearsals,
    undertakings,
    workflow,
)
from .core.clock import get_clock, iso
from .core.config import get_settings
from .core.db import SessionLocal, create_all
from .core.permissions import PermissionDenied

logger = logging.getLogger("sih26262")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "AICTE approval workflow, compliance monitoring and alert management. "
            "The Approval Rehearsal Engine is isolated from operational writes. "
            "Prototype: synthetic data, mock OCR and mock notification delivery."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    for module in (
        auth,
        applications,
        documents,
        compliance,
        rehearsals,
        workflow,
        undertakings,
        alerts,
        audit,
        officer_dashboard,
        admin_access,
    ):
        app.include_router(module.router, prefix=prefix)

    @app.exception_handler(PermissionDenied)
    async def permission_denied(_request: Request, exc: PermissionDenied):
        code = status.HTTP_404_NOT_FOUND if exc.code == "not_found" else status.HTTP_403_FORBIDDEN
        return JSONResponse(
            status_code=code,
            content={"detail": exc.message, "code": exc.code},
        )

    from .services.rehearsal_service import OverrideRejected
    from .services.rule_engine import InvalidRuleDefinition

    @app.exception_handler(OverrideRejected)
    async def override_rejected(_request: Request, exc: OverrideRejected):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "code": "override_rejected"},
        )

    @app.exception_handler(InvalidRuleDefinition)
    async def invalid_rule(_request: Request, exc: InvalidRuleDefinition):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc), "code": "invalid_rule_definition"},
        )

    @app.on_event("startup")
    def startup() -> None:
        create_all()
        if settings.seed_on_startup:
            from .services.seed import seed

            db = SessionLocal()
            try:
                seed(db)
            finally:
                db.close()

    @app.get("/health")
    def health() -> dict:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            database = "ok"
        except Exception as exc:  # pragma: no cover - operational path
            database = f"error: {exc}"
        finally:
            db.close()
        return {
            "status": "ok" if database == "ok" else "degraded",
            "database": database,
            "clock": iso(get_clock().now()),
            "environment": settings.env,
        }

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "docs": "/docs",
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
