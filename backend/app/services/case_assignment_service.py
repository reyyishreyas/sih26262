"""Hands a case to the people who may act on it next.

A case nobody is assigned to is invisible to any officer whose scope is
``assigned`` — the Review Officer in this demo. Only the demo seed ever created
assignment rows, so a College could create an application, submit it and upload
documents, and no reviewer would ever see it: the case had no queue to appear
in.

The route table already declares, for every state, which roles may act out of
it (``allowed_roles`` on the transition whose ``from_state`` is that state).
The assignment is therefore *read from configuration* rather than invented
here:

* case enters ``submitted`` -> the route says a ``scrutiny_officer`` acts next
  from there -> every active scrutiny officer gets the case in their list;
* case enters ``evc_completed`` -> an ``evc_member`` acts next -> the committee
  gets it;
* case enters ``returned`` -> only the institution acts next -> nothing is
  handed to an officer, because the ball is with the College.

Jurisdiction is still enforced: a region-scoped officer is only assigned cases
their region actually covers. An ``assigned``-scoped officer is eligible by
definition, because the row being written is exactly what grants them access.

Seed data deliberately keeps its own assignments, so the RBAC fixtures that pin
"this officer sees precisely these cases" continue to describe demo data
rather than runtime behaviour.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.permissions import SCOPE_COMMITTEE
from ..models import (
    Application,
    CaseAssignment,
    Role,
    User,
    UserRoleAssignment,
    WorkflowTransitionDefinition,
)
from .authorization_service import can_access_application, effective_access

_INSTITUTION_ROLE = "institution_representative"


def next_actor_roles(db: Session, application: Application) -> set[str]:
    """Roles the route allows to act from the case's *current* state."""
    definitions = db.scalars(
        select(WorkflowTransitionDefinition).where(
            WorkflowTransitionDefinition.route_key == application.route_key,
            WorkflowTransitionDefinition.from_state == application.current_state,
        )
    ).all()
    return {
        role
        for definition in definitions
        for role in (definition.allowed_roles or [])
    }


def assign_next_actors(db: Session, application: Application) -> list[CaseAssignment]:
    """Puts the case in the queue of whoever may act next.

    Idempotent: an officer who already holds the case keeps the same row, so
    calling this on every transition never duplicates assignments. Returns the
    rows it created, for callers that want to audit the hand-off.
    """
    roles = next_actor_roles(db, application)
    if not roles:
        return []

    now = get_clock().now()
    candidates = db.execute(
        select(User, UserRoleAssignment, Role.name)
        .join(UserRoleAssignment, User.id == UserRoleAssignment.user_id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            Role.name.in_(roles),
            User.is_active.is_(True),
            or_(
                UserRoleAssignment.revoked_at.is_(None),
                UserRoleAssignment.revoked_at > now,
            ),
        )
    ).all()

    existing = db.scalars(
        select(CaseAssignment).where(
            CaseAssignment.application_id == application.id,
            CaseAssignment.revoked_at.is_(None),
        )
    ).all()
    held_users = {row.user_id for row in existing if row.user_id}
    held_committees = {row.committee_id for row in existing if row.committee_id}

    created: list[CaseAssignment] = []
    for user, grant, role_name in candidates:
        committee_id = (
            grant.scope_id if grant.scope_type == SCOPE_COMMITTEE else None
        )
        if user.id in held_users:
            continue
        if committee_id and committee_id in held_committees:
            continue

        access = effective_access(db, user)
        if not (
            access.assigned_cases_only
            or access.committees
            or can_access_application(db, access, application)
        ):
            # Their role allows the action, but their jurisdiction does not
            # cover this case. A role list is not a licence to cross regions.
            continue

        row = CaseAssignment(
            application_id=application.id,
            user_id=user.id,
            committee_id=committee_id,
            role_name=role_name,
        )
        db.add(row)
        created.append(row)
        held_users.add(user.id)
        if committee_id:
            held_committees.add(committee_id)

    if created and application.assigned_officer_id is None:
        # The single officer reporting groups by. While a case is still with
        # the College there is no officer yet, and "unassigned" is the honest
        # answer, so a draft leaves this alone.
        primary = next(
            (row for row in created if row.role_name != _INSTITUTION_ROLE),
            None,
        )
        if primary is not None:
            application.assigned_officer_id = primary.user_id

    return created
