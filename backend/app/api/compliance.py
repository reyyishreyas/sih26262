from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import CASE_TRANSITION, COMPLIANCE_EVALUATE
from ..models import FindingDisposition, RuleEvaluation
from ..services import compliance_service
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application
from .deps import require


class FindingDispositionRequest(BaseModel):
    disposition: str = Field(pattern="^(confirmed|dismissed|clarification_requested)$")
    reason: str = Field(default="", max_length=1024)

router = APIRouter(prefix="/applications/{application_id}/compliance", tags=["compliance"])


def _reject_disposition(db: Session, access: EffectiveAccess, finding_id: str,
                        reason: str) -> None:
    AuditService(db).append(
        action="finding.disposition_rejected",
        entity_type="rule_evaluation",
        entity_id=finding_id,
        outcome="rejected",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason,
        request_id=current_request_id(),
    )
    db.commit()


@router.post("/findings/{finding_id}/disposition")
def record_finding_disposition(
    application_id: str,
    finding_id: str,
    payload: FindingDispositionRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """Record a human officer's disposition; advisory pre-checks are not findings."""
    application = require_application(db, access, application_id)
    finding = db.get(RuleEvaluation, finding_id)
    if finding is None or finding.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")
    if finding.outcome not in ("FAIL", "NEEDS_REVIEW"):
        _reject_disposition(db, access, finding.id, "finding does not require a disposition")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "finding does not require a disposition")
    reason = payload.reason.strip()
    if payload.disposition == "dismissed" and not reason:
        _reject_disposition(db, access, finding.id, "dismissal requires a reason")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "dismissal requires a reason")

    current = db.scalar(select(FindingDisposition).where(
        FindingDisposition.rule_evaluation_id == finding.id
    ))
    before = ({"disposition": current.disposition, "reason": current.reason}
              if current else {})
    if current is None:
        current = FindingDisposition(rule_evaluation_id=finding.id)
        db.add(current)
    current.disposition = payload.disposition
    current.reason = reason
    current.actor_id = access.user_id
    current.recorded_at = get_clock().now()
    db.flush()
    AuditService(db).append(
        action="finding.disposition_recorded",
        entity_type="rule_evaluation",
        entity_id=finding.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason,
        before=before,
        after={"disposition": current.disposition, "reason": reason,
               "application_id": application.id, "batch_id": finding.batch_id},
        request_id=current_request_id(),
    )
    db.commit()
    return {"finding_id": finding.id, "disposition": current.disposition,
            "reason": current.reason, "recorded_at": current.recorded_at}


@router.post("/evaluate")
def evaluate(
    application_id: str,
    access: EffectiveAccess = Depends(require(COMPLIANCE_EVALUATE)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    report = compliance_service.evaluate_application(db, application, persist=True)
    AuditService(db).append(
        action="finding.batch_evaluated",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "batch_id": report.batch_id,
            "baseline_version": report.baseline_version,
            "rule_set_version": report.rule_set_version,
            "outcomes": report.counted(),
        },
        request_id=current_request_id(),
    )
    db.commit()
    result = report.as_dict()
    result.update(compliance_service.evaluate_advisory_precheck(db, application))
    return result
