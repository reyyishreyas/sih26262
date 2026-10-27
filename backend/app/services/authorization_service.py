"""RBAC + scope enforcement.

Two separate questions, always asked on the server:

* **May this user perform this action?**  -> role permissions.
* **May this user touch this record?**     -> scope (region / institution / committee /
  assigned case), resolved from assignment records, never from a query parameter.

The same scope function produces the SQL filter for dashboards, so a total and its
drill-down can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.permissions import (
    SCOPE_ASSIGNED,
    SCOPE_COMMITTEE,
    SCOPE_GLOBAL,
    SCOPE_INSTITUTION,
    SCOPE_REGION,
    PermissionDenied,
)
from ..models import (
    Application,
    CaseAssignment,
    ConflictOfInterest,
    Institution,
    JurisdictionAssignment,
    Permission,
    RolePermission,
    User,
    UserRoleAssignment,
)


@dataclass
class EffectiveAccess:
    user: User
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    global_scope: bool = False
    regions: set[str] = field(default_factory=set)
    institutions: set[str] = field(default_factory=set)
    committees: set[str] = field(default_factory=set)
    assigned_cases_only: bool = False
    user_id: str = ""

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def primary_role(self) -> str:
        return self.roles[0] if self.roles else "unknown"


def effective_access(db: Session, user: User) -> EffectiveAccess:
    now = get_clock().now()
    access = EffectiveAccess(user=user, user_id=user.id)
    if not user.is_active:
        return access

    assignments = db.scalars(
        select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)
    ).all()
    active = [
        a
        for a in assignments
        if a.revoked_at is None or _aware(a.revoked_at) > now
    ]

    role_ids = {a.role_id for a in active}
    if role_ids:
        rows = db.execute(
            select(RolePermission.role_id, Permission.code)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
        ).all()
        access.permissions = {code for _role_id, code in rows}
        access.roles = sorted({a.role.name for a in active if a.role})

    for assignment in active:
        scope = assignment.scope_type
        if scope == SCOPE_GLOBAL:
            access.global_scope = True
        elif scope == SCOPE_REGION and assignment.scope_id:
            access.regions.add(assignment.scope_id)
        elif scope == SCOPE_INSTITUTION and assignment.scope_id:
            access.institutions.add(assignment.scope_id)
        elif scope == SCOPE_COMMITTEE and assignment.scope_id:
            access.committees.add(assignment.scope_id)
        elif scope == SCOPE_ASSIGNED:
            access.assigned_cases_only = True

    access.regions |= set(
        db.scalars(
            select(JurisdictionAssignment.region_id).where(
                JurisdictionAssignment.user_id == user.id
            )
        ).all()
    )
    return access


def _aware(value):
    from ..core.clock import to_utc

    return to_utc(value)


def require_permission(access: EffectiveAccess, permission: str) -> None:
    if not access.has(permission):
        raise PermissionDenied(
            f"role {access.primary_role!r} does not hold {permission!r}"
        )


def scope_filter(access: EffectiveAccess):
    """SQL predicate restricting Application rows to the caller's authority."""
    if access.global_scope:
        return None

    clauses = []
    if access.regions:
        clauses.append(
            Application.institution_id.in_(
                select(Institution.id).where(Institution.region_id.in_(access.regions))
            )
        )
    if access.institutions:
        clauses.append(Application.institution_id.in_(access.institutions))
    if access.committees:
        committee_cases = Application.id.in_(
            select(CaseAssignment.application_id).where(
                CaseAssignment.committee_id.in_(access.committees),
                CaseAssignment.revoked_at.is_(None),
            )
        )
        committee_conflicts = Application.id.in_(
            select(ConflictOfInterest.application_id).where(
                ConflictOfInterest.declarant_id == access.user_id,
                ConflictOfInterest.status == "open",
            )
        )
        clauses.append(
            committee_cases & ~committee_conflicts
        )
    if access.assigned_cases_only:
        # COI hiding (FR-12): an assigned-scoped officer must not see a case
        # they have an OPEN conflict declaration on. Surgical: this only
        # removes cases from the assigned-scoped officer's own list; region,
        # institution and committee scope are untouched, so a regional officer
        # who declared a COI still sees their region (hiding is per-declarer,
        # not a case-wide lock). Advisory — it hides, never gates (DEC-0003).
        assigned_clause = Application.id.in_(
            select(CaseAssignment.application_id).where(
                CaseAssignment.user_id == access.user_id,
                CaseAssignment.revoked_at.is_(None),
            )
        )
        conflicted = Application.id.in_(
            select(ConflictOfInterest.application_id).where(
                ConflictOfInterest.declarant_id == access.user_id,
                ConflictOfInterest.status == "open",
            )
        )
        clauses.append(and_(assigned_clause, ~conflicted))
    if not clauses:
        return false()
    return or_(*clauses)


def institution_scope_filter(access: EffectiveAccess):
    """SQL predicate for institution lookups, derived from the same scope sets."""
    if access.global_scope:
        return None

    clauses = []
    if access.regions:
        clauses.append(Institution.region_id.in_(access.regions))
    if access.institutions:
        clauses.append(Institution.id.in_(access.institutions))
    if access.committees:
        clauses.append(
            Institution.id.in_(
                select(Application.institution_id).where(
                    Application.id.in_(
                        select(CaseAssignment.application_id).where(
                            CaseAssignment.committee_id.in_(access.committees),
                            CaseAssignment.revoked_at.is_(None),
                        )
                    )
                )
            )
        )
    if access.assigned_cases_only:
        clauses.append(
            Institution.id.in_(
                select(Application.institution_id).where(
                    Application.id.in_(
                        select(CaseAssignment.application_id).where(
                            CaseAssignment.user_id == access.user_id,
                            CaseAssignment.revoked_at.is_(None),
                        )
                    )
                )
            )
        )
    if not clauses:
        return false()
    return or_(*clauses)


def can_access_application(db: Session, access: EffectiveAccess, application: Application) -> bool:
    if access.global_scope:
        return True
    institution = db.get(Institution, application.institution_id)
    if institution and institution.region_id in access.regions:
        return True
    if application.institution_id in access.institutions:
        return True
    assignments = db.scalars(
        select(CaseAssignment).where(
            CaseAssignment.application_id == application.id,
            CaseAssignment.revoked_at.is_(None),
        )
    ).all()
    if any(a.committee_id in access.committees for a in assignments if a.committee_id):
        from .conflict_of_interest import has_open_coi

        return not has_open_coi(db, access.user_id, application.id)
    if not access.assigned_cases_only:
        return False
    if not any(a.user_id == access.user_id for a in assignments):
        return False
    # COI hiding (FR-12): an assigned-scoped officer does not see a case they
    # have an OPEN conflict declaration on. Advisory — it hides, never gates.
    from .conflict_of_interest import has_open_coi

    return not has_open_coi(db, access.user_id, application.id)


def require_application(
    db: Session, access: EffectiveAccess, application_id: str
) -> Application:
    """404 semantics on purpose: an inaccessible case must not leak its existence."""
    application = db.get(Application, application_id)
    if application is None or not can_access_application(db, access, application):
        raise PermissionDenied(
            "application not found in your scope", code="not_found"
        )
    return application
