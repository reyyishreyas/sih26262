from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ
from ..schemas.api import TransitionRequest
from ..services import workflow_service
from ..services.authorization_service import EffectiveAccess, require_application
from ..services.policy import workflow_routes
from .deps import get_access, require_any

router = APIRouter(tags=["workflow"])


class RevertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""


@router.get("/workflow/routes")
def list_routes(access: EffectiveAccess = Depends(get_access)) -> list[dict]:
    """Route catalogue used by the application-creation form and the review UI."""
    catalogue = workflow_routes().get("routes", {})
    return [
        {
            "key": key,
            "label": route.get("label", key),
            "states": sorted(
                {
                    transition["from_state"]
                    for transition in route.get("transitions", [])
                }
                | {
                    transition["to_state"]
                    for transition in route.get("transitions", [])
                }
            ),
        }
        for key, route in catalogue.items()
    ]


@router.post("/applications/{application_id}/transitions")
def request_transition(
    application_id: str,
    payload: TransitionRequest,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    decision = workflow_service.request_transition(
        db,
        access,
        application_id,
        payload.action,
        payload.reason,
        request_id=current_request_id(),
    )
    return decision.as_dict()


@router.post("/applications/{application_id}/revert")
def revert_last_transition(
    application_id: str,
    payload: RevertRequest,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Undo the last step on a case. The undo is itself a recorded step."""
    decision = workflow_service.revert_last_transition(
        db,
        access,
        application_id,
        payload.reason,
        request_id=current_request_id(),
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
