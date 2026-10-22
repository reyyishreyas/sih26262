from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import COMPLIANCE_EVALUATE
from ..services import compliance_service
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
    db.commit()
    return report.as_dict()
