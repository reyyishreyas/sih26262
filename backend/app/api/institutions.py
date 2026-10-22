from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import APPLICATION_CREATE, APPLICATION_READ, CASE_READ
from ..models import Institution, Region
from ..services.authorization_service import (
    EffectiveAccess,
    institution_scope_filter,
)
from .deps import require_any

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.get("")
def list_institutions(
    access: EffectiveAccess = Depends(
        require_any(APPLICATION_READ, APPLICATION_CREATE, CASE_READ)
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Institution).order_by(Institution.name)
    clause = institution_scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    regions = {
        region.id: region
        for region in db.scalars(select(Region)).all()
    }
    return [
        {
            "id": institution.id,
            "aicte_id": institution.aicte_id,
            "name": institution.name,
            "region_id": institution.region_id,
            "region_code": regions[institution.region_id].code
            if institution.region_id in regions
            else None,
        }
        for institution in db.scalars(query).all()
    ]
