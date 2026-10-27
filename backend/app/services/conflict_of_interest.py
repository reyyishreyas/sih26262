"""Conflict-of-interest declarations (FR-12, PRD Appendix E).

The PRD proposes a COI schema (declaration, type, timestamp, reviewer,
exclusion, reassignment) but explicitly says not to claim COI handling exists
"without approved policy and tests" (Appendix E, line 412). So this records the
*declaration* and HIDES the case from the declarer — the minimum honest
behaviour that does not invent a conflict rule. A human reviewer decides the
exclusion and any reassignment; the declaration itself never gates, moves or
rejects a case (DEC-0003).

What a declaration does:
* **Hides the case** from an ``assigned``-scoped officer — the declarer is
  skipped in assignment and excluded from their visible list (see
  ``assignment_policy.has_open_coi`` and the ``scope_filter`` /
  ``can_access_application`` hooks).
* **Keeps the declarer out of the workload pool** — ``assign_next_actors``
  skips them.
* **Never gates**: the case still moves through the workflow; a declared COI
  is never a reason to refuse a transition.

Resolving or revoking a declaration (``status`` leaves ``open``) restores
visibility and pool eligibility, so a mistaken declaration is recoverable.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..models import ConflictOfInterest, User
from .policy import assignment_policy


def open_coi_case_ids(db: Session, user_id: str) -> set[str]:
    """Application IDs this user has an OPEN conflict declaration on.

    Used by the visibility hooks: an assigned-scoped officer must not see a
    case they declared a conflict on while that declaration is unresolved.
    """
    rows = db.scalars(
        select(ConflictOfInterest.application_id).where(
            ConflictOfInterest.declarant_id == user_id,
            ConflictOfInterest.status == "open",
        )
    ).all()
    return set(rows)


def has_open_coi(db: Session, user_id: str, application_id: str) -> bool:
    """True when this user has an open conflict declaration on this case."""
    row = db.scalars(
        select(ConflictOfInterest).where(
            ConflictOfInterest.declarant_id == user_id,
            ConflictOfInterest.application_id == application_id,
            ConflictOfInterest.status == "open",
        )
    ).first()
    return row is not None


def declare(
    db: Session,
    *,
    application_id: str,
    declarant_id: str,
    conflict_type: str,
    description: str = "",
) -> ConflictOfInterest:
    """Record a conflict declaration. Hides the case from the declarer.

    One open declaration per (case, declarant): re-declaring while one is open
    is refused (the existing declaration is the source of truth), so the
    "already declared" case cannot be created by a retry.
    """
    allowed = {
        entry["type"]
        for entry in assignment_policy()["conflict_of_interest"]["declaration_types"]
    }
    if conflict_type not in allowed:
        raise ValueError(
            f"unknown conflict type {conflict_type!r}; "
            f"allowed: {sorted(allowed)}"
        )

    existing = db.scalars(
        select(ConflictOfInterest).where(
            ConflictOfInterest.declarant_id == declarant_id,
            ConflictOfInterest.application_id == application_id,
            ConflictOfInterest.status == "open",
        )
    ).first()
    if existing is not None:
        return existing

    row = ConflictOfInterest(
        application_id=application_id,
        declarant_id=declarant_id,
        conflict_type=conflict_type,
        description=description,
    )
    db.add(row)
    db.flush()
    return row


def review(
    db: Session,
    *,
    declaration_id: str,
    reviewer_id: str,
    status: str,
    resolution_note: str = "",
) -> ConflictOfInterest | None:
    """A reviewer resolves or revokes a declaration, restoring visibility.

    ``status`` leaves ``open`` (``resolved``/``revoked``), which is what
    restores the case to the declarer's view and pool. The reviewer and
    timestamp are recorded per Appendix E.
    """
    row = db.get(ConflictOfInterest, declaration_id)
    if row is None:
        return None
    if status not in ("resolved", "revoked"):
        raise ValueError(f"status must be resolved or revoked, got {status!r}")
    row.status = status
    row.reviewer_id = reviewer_id
    row.reviewed_at = get_clock().now()
    row.resolution_note = resolution_note
    db.flush()
    return row


def declarations_for_case(
    db: Session, application_id: str
) -> list[ConflictOfInterest]:
    """All declarations on one case, for the assignment/audit view."""
    return list(
        db.scalars(
            select(ConflictOfInterest).where(
                ConflictOfInterest.application_id == application_id
            )
        ).all()
    )


def serialise(row: ConflictOfInterest, declarant: User | None = None) -> dict:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "declarant_id": row.declarant_id,
        "declarant_email": declarant.email if declarant else None,
        "conflict_type": row.conflict_type,
        "description": row.description,
        "declared_at": row.declared_at.isoformat() if row.declared_at else None,
        "status": row.status,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "resolution_note": row.resolution_note,
    }
