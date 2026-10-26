from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ
from ..schemas.api import TransitionRequest
from ..services import routing, workflow_service
from ..services.authorization_service import EffectiveAccess, require_application
from ..services.policy import workflow_routes
from .deps import get_access, require_any

router = APIRouter(tags=["workflow"])


class RevertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""
    # Same optimistic-concurrency contract as TransitionRequest.
    expected_baseline_version: int | None = None


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


@router.get("/workflow/table-2-3-scoreboard")
def table_2_3_scoreboard(
    access: EffectiveAccess = Depends(get_access),
) -> dict:
    """The 21 Table 2.3 rows, their stages, and coverage (Phase 1.9).

    A read-only scoreboard of the routing catalogue — no case data, so it
    needs only an authenticated user, not a per-case permission. Advisory
    like the rows themselves (Unverified, DEC-0003): it displays
    configuration and makes no routing decision.
    """
    return routing.scoreboard()


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
        expected_baseline_version=payload.expected_baseline_version,
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
        expected_baseline_version=payload.expected_baseline_version,
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
