"""Committee-scoped expert assignments for scheduled EVC visits."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, to_utc
from ..models import (
    CaseAssignment,
    Committee,
    ConflictOfInterest,
    EvcVisit,
    Role,
    User,
    UserRoleAssignment,
)


def available_experts(
    db: Session, *, committee_id: str, application_id: str | None = None
) -> list[User]:
    """Active EVC members explicitly scoped to this committee, without open COI."""
    rows = db.execute(
        select(User, UserRoleAssignment)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            Role.name == "evc_member",
            User.is_active.is_(True),
            UserRoleAssignment.scope_type == "committee",
            UserRoleAssignment.scope_id == committee_id,
        )
        .order_by(User.full_name, User.id)
    ).all()
    now = get_clock().now()
    experts: dict[str, User] = {}
    for user, assignment in rows:
        revoked_at = to_utc(assignment.revoked_at)
        if revoked_at is not None and revoked_at <= now:
            continue
        if application_id is not None and db.scalars(
            select(ConflictOfInterest.id).where(
                ConflictOfInterest.application_id == application_id,
                ConflictOfInterest.declarant_id == user.id,
                ConflictOfInterest.status == "open",
            )
        ).first():
            continue
        experts[user.id] = user
    return list(experts.values())


def experts_for_visit(db: Session, visit_id: str) -> list[dict[str, str]]:
    rows = db.execute(
        select(User.id, User.full_name)
        .join(CaseAssignment, CaseAssignment.user_id == User.id)
        .where(
            CaseAssignment.source_evc_visit_id == visit_id,
            CaseAssignment.revoked_at.is_(None),
            User.is_active.is_(True),
        )
        .order_by(User.full_name, User.id)
    ).all()
    return [{"id": user_id, "name": name} for user_id, name in rows]


def assign_visit_experts(
    db: Session,
    *,
    visit: EvcVisit,
    committee: Committee,
    expert_ids: list[str],
) -> None:
    for expert_id in sorted(set(expert_ids)):
        db.add(
            CaseAssignment(
                application_id=visit.application_id,
                user_id=expert_id,
                committee_id=committee.id,
                role_name="evc_member",
                source_evc_visit_id=visit.id,
                assigned_at=get_clock().now(),
            )
        )
