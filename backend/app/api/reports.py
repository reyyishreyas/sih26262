"""Consolidated reports: one endpoint per section, or all of them at once.

Everything here is scope-filtered through the caller's effective access — the
same filter that feeds the dashboard — so the drill-down lists reconcile with
the headline numbers by construction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import MONITORING_READ
from ..services import report_export_service, reporting_service
from ..services.authorization_service import EffectiveAccess
from .deps import require

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def all_reports(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Every report section in one round trip (what the Reports page loads)."""
    return reporting_service.full_report(db, access)


@router.get("/export")
def export_reports(
    format: str = Query(pattern="^(csv|pdf)$"),
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> Response:
    """Export the seven PRD §12 report families inside the caller's scope."""
    report = reporting_service.phase7_report_bundle(db, access)
    if format == "csv":
        content = report_export_service.as_csv(report)
        media_type = "text/csv; charset=utf-8"
    elif format == "pdf":
        content = report_export_service.as_pdf(report)
        media_type = "application/pdf"
    else:  # Query validation is the public guard; keep direct invocation safe.
        raise HTTPException(status_code=422, detail="format must be csv or pdf")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="aicte-reports.{format}"'},
    )


@router.get("/pendency")
def pendency(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.pendency_report(db, access)


@router.get("/regions")
def regions(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.region_report(db, access)


@router.get("/evc")
def evc(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.evc_report(db, access)


@router.get("/undertakings")
def undertakings(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.undertaking_report(db, access)


@router.get("/documents")
def documents(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.document_report(db, access)


@router.get("/overdue")
def overdue(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.overdue_report(db, access)


@router.get("/workload")
def workload(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return reporting_service.officer_workload(db, access)
