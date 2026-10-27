from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import DASHBOARD_READ, MONITORING_READ
from ..services import monitoring_service
from ..services.authorization_service import EffectiveAccess
from .deps import require, require_any

router = APIRouter(prefix="/officer", tags=["officer"])


@router.get("/dashboard")
def dashboard(
    access: EffectiveAccess = Depends(require_any(MONITORING_READ, DASHBOARD_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return monitoring_service.dashboard(db, access)


@router.get("/pendency")
def pendency(
    state: str | None = Query(default=None),
    region: str | None = Query(default=None, description="Region code, applied inside your scope"),
    officer_id: str | None = Query(default=None),
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    rows = monitoring_service.pendency(
        db, access, state=state, region_code=region, officer_id=officer_id
    )
    return {
        "filters": {"state": state, "region": region, "officer_id": officer_id},
        "scope_enforced": True,
        "count": len(rows),
        "rows": rows,
    }


@router.get("/ageing")
def ageing(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return monitoring_service.ageing(db, access)


@router.get("/escalations")
def escalations(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    rows = monitoring_service.escalations(db, access)
    return {"count": len(rows), "rows": rows}


@router.get("/assignments")
def assignments(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    rows = monitoring_service.assignments(db, access)
    return {"count": len(rows), "rows": rows}
