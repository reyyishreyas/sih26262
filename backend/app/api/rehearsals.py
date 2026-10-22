from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import REHEARSAL_RUN
from ..schemas.api import RehearsalRequest
from ..services import rehearsal_service
from ..services.authorization_service import EffectiveAccess, require_application
from .deps import require

router = APIRouter(tags=["rehearsal"])


@router.post("/applications/{application_id}/rehearsals")
def create_rehearsal(
    application_id: str,
    payload: RehearsalRequest,
    request: Request,
    access: EffectiveAccess = Depends(require(REHEARSAL_RUN)),
    db: Session = Depends(get_db),
) -> dict:
    return rehearsal_service.run_rehearsal(
        db,
        access,
        application_id,
        overrides=payload.overrides,
        request_id=request.headers.get("x-request-id"),
    )


@router.get("/rehearsals/{run_id}")
def get_rehearsal(
    run_id: str,
    access: EffectiveAccess = Depends(require(REHEARSAL_RUN)),
    db: Session = Depends(get_db),
) -> dict:
    report = rehearsal_service.get_run(run_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rehearsal run not found")
    # Simulation results are still case data: they inherit the case's access scope.
    require_application(db, access, report["application_id"])
    return report
