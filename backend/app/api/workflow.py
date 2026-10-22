from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ
from ..schemas.api import TransitionRequest
from ..services import workflow_service
from ..services.authorization_service import EffectiveAccess, require_application
from .deps import require_any

router = APIRouter(tags=["workflow"])


@router.post("/applications/{application_id}/transitions")
def request_transition(
    application_id: str,
    payload: TransitionRequest,
    request: Request,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    decision = workflow_service.request_transition(
        db,
        access,
        application_id,
        payload.action,
        payload.reason,
        request_id=request.headers.get("x-request-id"),
    )
    return decision.as_dict()


@router.get("/applications/{application_id}/transitions")
def available_transitions(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    application = require_application(db, access, application_id)
    return workflow_service.available_transitions(db, access, application)
