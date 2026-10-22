from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.permissions import ADMIN_ASSIGNMENTS, ADMIN_USERS, AUDIT_READ
from ..core.security import hash_password
from ..models import (
    AuditEvent,
    Permission,
    Role,
    RolePermission,
    User,
    UserRoleAssignment,
)
from ..schemas.api import AssignmentCreate
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess
from .deps import require

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/roles")
def list_roles(
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    out = []
    for role in roles:
        codes = db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.code)
        ).all()
        out.append({"id": role.id, "name": role.name, "permissions": list(codes)})
    return out


@router.get("/users")
def list_users(
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    users = db.scalars(select(User).order_by(User.email)).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "assignments": [
                {
                    "id": assignment.id,
                    "role_id": assignment.role_id,
                    "role": assignment.role.name if assignment.role else None,
                    "scope_type": assignment.scope_type,
                    "scope_id": assignment.scope_id,
                    "revoked_at": iso(assignment.revoked_at),
                }
                for assignment in user.assignments
            ],
        }
        for user in users
    ]


@router.post("/assignments")
def create_assignment(
    payload: AssignmentCreate,
    access: EffectiveAccess = Depends(require(ADMIN_ASSIGNMENTS)),
    db: Session = Depends(get_db),
) -> dict:
    from fastapi import HTTPException, status

    user = db.get(User, payload.user_id)
    role = db.scalars(select(Role).where(Role.name == payload.role_name)).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    if payload.scope_type != "global" and not payload.scope_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "a non-global scope requires scope_id",
        )

    assignment = UserRoleAssignment(
        user_id=user.id,
        role_id=role.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    db.add(assignment)
    db.flush()
    AuditService(db).append(
        action="admin.role_assigned",
        entity_type="user",
        entity_id=user.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "role": role.name,
            "scope_type": payload.scope_type,
            "scope_id": payload.scope_id,
        },
    )
    db.commit()
    return {"assignment_id": assignment.id, "user_id": user.id, "role": role.name}


@router.post("/assignments/{assignment_id}/revoke")
def revoke_assignment(
    assignment_id: str,
    access: EffectiveAccess = Depends(require(ADMIN_ASSIGNMENTS)),
    db: Session = Depends(get_db),
) -> dict:
    from fastapi import HTTPException, status

    assignment = db.get(UserRoleAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assignment not found")
    if assignment.revoked_at is not None:
        return {"assignment_id": assignment.id, "already_revoked": True}
    assignment.revoked_at = get_clock().now()
    AuditService(db).append(
        action="admin.role_revoked",
        entity_type="user",
        entity_id=assignment.user_id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={"assignment_id": assignment.id},
    )
    db.commit()
    return {"assignment_id": assignment.id, "revoked_at": iso(assignment.revoked_at)}


@router.get("/audit")
def admin_audit(
    access: EffectiveAccess = Depends(require(AUDIT_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.action.like("admin.%"))
        .order_by(AuditEvent.seq.desc())
        .limit(200)
    ).all()
    return [
        {
            "seq": event.seq,
            "at": iso(event.at),
            "action": event.action,
            "actor_id": event.actor_id,
            "outcome": event.outcome,
            "after": event.after,
        }
        for event in events
    ]
