"""Administrative draft, version history and four-eyes policy review."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.permissions import ADMIN_RULES
from ..models import PolicyConfigVersion
from ..services import policy_config_service
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess
from .deps import require

router = APIRouter(prefix="/admin/policies", tags=["admin policies"])


class PolicyDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]
    summary: str = Field(min_length=3, max_length=512)


@router.get("")
def list_policy_versions(
    access: EffectiveAccess = Depends(require(ADMIN_RULES)),
    db: Session = Depends(get_db),
) -> list[dict]:
    _ = access
    output = []
    for key in policy_config_service.POLICY_FILES:
        rows = db.scalars(
            select(PolicyConfigVersion)
            .where(PolicyConfigVersion.policy_key == key)
            .order_by(PolicyConfigVersion.version.desc())
        ).all()
        output.append({
            "policy_key": key,
            "baseline": policy_config_service.baseline(key),
            "active": policy_config_service.active(db, key),
            "versions": [_serialise(row) for row in rows],
        })
    return output


@router.post("/{policy_key}/drafts", status_code=status.HTTP_201_CREATED)
def create_policy_draft(
    policy_key: str,
    payload: PolicyDraftRequest,
    access: EffectiveAccess = Depends(require(ADMIN_RULES)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        content = policy_config_service.validate(policy_key, payload.content)
    except ValueError as exc:
        AuditService(db).append(
            action="policy.draft_rejected", entity_type="policy_config",
            entity_id=policy_key, outcome="rejected", actor_id=access.user_id,
            actor_role=access.primary_role, reason=str(exc),
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    version = (db.scalar(
        select(func.max(PolicyConfigVersion.version)).where(
            PolicyConfigVersion.policy_key == policy_key
        )
    ) or 0) + 1
    row = PolicyConfigVersion(
        policy_key=policy_key,
        version=version,
        status="draft",
        content=content,
        content_hash=policy_config_service.content_hash(content),
        summary=payload.summary.strip(),
        created_by=access.user_id,
        created_at=get_clock().now(),
    )
    db.add(row)
    db.flush()
    AuditService(db).append(
        action="policy.draft_created", entity_type="policy_config",
        entity_id=row.id, outcome="accepted", actor_id=access.user_id,
        actor_role=access.primary_role,
        after={"policy_key": policy_key, "version": version, "content_hash": row.content_hash},
    )
    db.commit()
    return _serialise(row)


@router.post("/{policy_key}/{version}/approve")
def approve_policy_draft(
    policy_key: str,
    version: int,
    access: EffectiveAccess = Depends(require(ADMIN_RULES)),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalars(select(PolicyConfigVersion).where(
        PolicyConfigVersion.policy_key == policy_key,
        PolicyConfigVersion.version == version,
    )).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy draft not found")
    if row.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "only a draft can be approved")
    if row.created_by == access.user_id:
        AuditService(db).append(
            action="policy.approval_rejected", entity_type="policy_config",
            entity_id=row.id, outcome="rejected", actor_id=access.user_id,
            actor_role=access.primary_role,
            reason="four-eyes review requires a different administrator",
            before={"status": "draft"}, after={"status": "draft"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a different administrator must review and approve this draft",
        )
    row.status = "approved"
    row.reviewed_by = access.user_id
    row.reviewed_at = get_clock().now()
    db.flush()
    AuditService(db).append(
        action="policy.draft_approved", entity_type="policy_config",
        entity_id=row.id, outcome="accepted", actor_id=access.user_id,
        actor_role=access.primary_role, before={"status": "draft"},
        after={"policy_key": row.policy_key, "version": row.version,
               "status": "approved", "content_hash": row.content_hash},
    )
    db.commit()
    return _serialise(row)


def _serialise(row: PolicyConfigVersion) -> dict:
    return {
        "id": row.id,
        "policy_key": row.policy_key,
        "version": row.version,
        "status": row.status,
        "content": row.content,
        "content_hash": row.content_hash,
        "summary": row.summary,
        "created_by": row.created_by,
        "created_at": iso(row.created_at),
        "reviewed_by": row.reviewed_by,
        "reviewed_at": iso(row.reviewed_at),
    }
