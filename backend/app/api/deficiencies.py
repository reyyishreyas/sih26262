from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import (
    APPLICATION_READ,
    CASE_READ,
    CASE_TRANSITION,
    DOCUMENT_VERIFY,
)
from ..models import Application, Deficiency, Document, ExtractedField
from ..schemas.api import (
    DeficiencyCloseRequest,
    DeficiencyCreate,
    DeficiencyOut,
    DeficiencyUpdate,
)
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
)
from .deps import require_any

router = APIRouter(prefix="/applications/{application_id}/deficiencies", tags=["deficiencies"])


@router.get("", response_model=list[DeficiencyOut])
def list_deficiencies(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> list[Deficiency]:
    """Retrieve all structured deficiencies for this application.

    Institutions see open, addressed and closed deficiencies (drafts are officer-only
    until finalized/returned). Officers see all deficiencies.
    """
    application = require_application(db, access, application_id)
    query = select(Deficiency).where(Deficiency.application_id == application.id)

    # Institution users should only see deficiencies that have been finalized/issued
    if "institution_representative" in access.roles and not any(
        r in access.roles for r in ("scrutiny_officer", "supervisory_officer", "regional_officer", "administrator")
    ):
        query = query.where(Deficiency.status.in_(("open", "addressed", "closed")))

    return list(db.scalars(query.order_by(Deficiency.created_at.asc())).all())


@router.post("", response_model=DeficiencyOut, status_code=status.HTTP_201_CREATED)
def create_deficiency(
    application_id: str,
    payload: DeficiencyCreate,
    access: EffectiveAccess = Depends(require_any(CASE_TRANSITION, DOCUMENT_VERIFY)),
    db: Session = Depends(get_db),
) -> Deficiency:
    """Create a structured deficiency on an application, optionally tied to a document and field.

    Enforces that institutions cannot create deficiencies (requires officer rights).
    """
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)

    # Validate document if supplied
    doc: Document | None = None
    if payload.document_id:
        doc = db.get(Document, payload.document_id)
        if doc is None or doc.application_id != application.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "document not found on this application")

    # Validate extracted field if supplied
    extracted_field: ExtractedField | None = None
    if payload.extracted_field_id:
        extracted_field = db.get(ExtractedField, payload.extracted_field_id)
        if extracted_field is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "extracted field not found")
        if doc and extracted_field.document_id != doc.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "extracted field does not belong to specified document")

    field_name = payload.field_name or (extracted_field.field_name if extracted_field else None)
    extracted_value = payload.extracted_value if payload.extracted_value is not None else (extracted_field.value if extracted_field else None)

    now = get_clock().now()
    deficiency = Deficiency(
        application_id=application.id,
        document_id=payload.document_id,
        extracted_field_id=payload.extracted_field_id,
        category=payload.category,
        rule_key=payload.rule_key,
        field_name=field_name,
        extracted_value=extracted_value,
        explanation=payload.explanation.strip(),
        corrective_action=payload.corrective_action.strip(),
        status=payload.status,
        created_by=access.user_id,
        created_at=now,
    )
    db.add(deficiency)
    db.flush()
    application.baseline_version += 1

    AuditService(db).append(
        action="deficiency.created",
        entity_type="deficiency",
        entity_id=deficiency.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.explanation[:255],
        after={
            "application_id": application.id,
            "category": payload.category,
            "field_name": field_name,
            "status": payload.status,
            "document_id": payload.document_id,
        },
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(deficiency)
    return deficiency


@router.patch("/{deficiency_id}", response_model=DeficiencyOut)
def update_deficiency(
    application_id: str,
    deficiency_id: str,
    payload: DeficiencyUpdate,
    access: EffectiveAccess = Depends(require_any(CASE_TRANSITION, DOCUMENT_VERIFY)),
    db: Session = Depends(get_db),
) -> Deficiency:
    """Update explanation, corrective action, or status of an existing deficiency (officers only)."""
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)

    deficiency = db.get(Deficiency, deficiency_id)
    if deficiency is None or deficiency.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deficiency not found on this application")

    before = {
        "status": deficiency.status,
        "explanation": deficiency.explanation,
        "corrective_action": deficiency.corrective_action,
    }

    if payload.explanation is not None:
        deficiency.explanation = payload.explanation.strip()
    if payload.corrective_action is not None:
        deficiency.corrective_action = payload.corrective_action.strip()
    if payload.resolution_note is not None:
        deficiency.resolution_note = payload.resolution_note.strip()
    if payload.status is not None:
        deficiency.status = payload.status
        if payload.status == "closed":
            deficiency.resolved_by = access.user_id
            deficiency.resolved_at = get_clock().now()

    application.baseline_version += 1
    AuditService(db).append(
        action="deficiency.updated",
        entity_type="deficiency",
        entity_id=deficiency.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        before=before,
        after={
            "status": deficiency.status,
            "explanation": deficiency.explanation,
            "corrective_action": deficiency.corrective_action,
        },
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(deficiency)
    return deficiency


@router.post("/{deficiency_id}/close", response_model=DeficiencyOut)
def close_deficiency(
    application_id: str,
    deficiency_id: str,
    payload: DeficiencyCloseRequest,
    access: EffectiveAccess = Depends(require_any(CASE_TRANSITION, DOCUMENT_VERIFY)),
    db: Session = Depends(get_db),
) -> Deficiency:
    """Explicitly verify and close an addressed deficiency following officer review."""
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)

    deficiency = db.get(Deficiency, deficiency_id)
    if deficiency is None or deficiency.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deficiency not found on this application")

    before_status = deficiency.status
    now = get_clock().now()
    deficiency.status = "closed"
    deficiency.resolved_by = access.user_id
    deficiency.resolved_at = now
    if payload.resolution_note:
        deficiency.resolution_note = payload.resolution_note.strip()

    application.baseline_version += 1
    AuditService(db).append(
        action="deficiency.closed",
        entity_type="deficiency",
        entity_id=deficiency.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.resolution_note or "Closed by officer",
        before={"status": before_status},
        after={"status": "closed", "resolved_at": now.isoformat()},
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(deficiency)
    return deficiency
