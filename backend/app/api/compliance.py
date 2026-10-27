from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import COMPLIANCE_EVALUATE
from ..services import compliance_service
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application
from .deps import require

router = APIRouter(prefix="/applications/{application_id}/compliance", tags=["compliance"])


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
    result["advisory_checks"] = compliance_service.evaluate_evidence_crosschecks(
        db, application
    )
    result["advisory_site_checks"] = compliance_service.evaluate_site_checks(
        db, application
    )
    return result
