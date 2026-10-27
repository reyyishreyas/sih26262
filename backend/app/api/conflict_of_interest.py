"""Conflict-of-interest declarations (FR-12, PRD Appendix E).

An officer declares a conflict on one case; that hides the case from them and
keeps them out of the workload pool. A reviewer resolves or revokes the
declaration, restoring visibility. Advisory — a declaration never gates, moves
or rejects a case (DEC-0003). See ``services/conflict_of_interest`` and
IMPL-0031.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import CASE_READ, MONITORING_READ, PermissionDenied
from ..models import Application, ConflictOfInterest
from ..services import conflict_of_interest as coi
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    can_access_application,
    require_application,
)
from .deps import require, require_any

router = APIRouter(tags=["conflict-of-interest"])


class DeclareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_type: str
    description: str = ""


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    resolution_note: str = ""


@router.post("/applications/{application_id}/conflicts-of-interest")
def declare_conflict(
    application_id: str,
    payload: DeclareRequest,
    access: EffectiveAccess = Depends(require_any(CASE_READ, MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Record an officer's conflict declaration; hides the case from them.

    One open declaration per (case, declarant): re-declaring while one is open
    returns the existing declaration, so a retry is idempotent and cannot
    create a second hold.
    """
    # Existence only. Visibility is deliberately NOT checked: a COI declaration
    # hides the case from the declarer, so requiring visibility would refuse
    # the very declaration that caused it and break re-declaration. An id
    # outside the caller's scope still looks absent (404), because such a
    # caller was never assigned the case and holds no declaration on it.
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    if (
        not can_access_application(db, access, application)
        and not coi.has_open_coi(db, access.user_id, application.id)
    ):
        raise PermissionDenied(
            "application not found in your scope", code="not_found"
        )
    try:
        row = coi.declare(
            db,
            application_id=application.id,
            declarant_id=access.user_id,
            conflict_type=payload.conflict_type,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    AuditService(db).append(
        action="coi.declared",
        entity_type="conflict_of_interest",
        entity_id=row.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.conflict_type,
        after={
            "application_id": application_id,
            "conflict_type": row.conflict_type,
            "status": row.status,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return coi.serialise(row)


@router.get("/applications/{application_id}/conflicts-of-interest")
def list_conflicts(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, MONITORING_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """All declarations on one case (officer + reviewer view)."""
    application = require_application(db, access, application_id)
    rows = coi.declarations_for_case(db, application.id)
    return [coi.serialise(row) for row in rows]


@router.post("/conflicts-of-interest/{declaration_id}/review")
def review_conflict(
    declaration_id: str,
    payload: ReviewRequest,
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """A reviewer resolves or revokes a declaration, restoring visibility.

    ``status`` must be ``resolved`` or ``revoked``; anything else is a 422.
    The reviewer and timestamp are recorded per Appendix E.
    """
    row = db.get(ConflictOfInterest, declaration_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "declaration not found")
    application = require_application(db, access, row.application_id)
    try:
        updated = coi.review(
            db,
            declaration_id=declaration_id,
            reviewer_id=access.user_id,
            status=payload.status,
            resolution_note=payload.resolution_note,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "declaration not found")
    AuditService(db).append(
        action="coi.reviewed",
        entity_type="conflict_of_interest",
        entity_id=updated.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.status,
        after={
            "application_id": application.id,
            "status": updated.status,
            "reviewer_id": updated.reviewer_id,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return coi.serialise(updated)
