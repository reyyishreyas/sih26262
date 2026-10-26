"""FR-03 blocked-application flags and the FR-05 lease-years check.

Read is advisory (evaluation is computed on read, never stored); the flag
write is an officer act — permission-gated, scope-checked, audited — and
records only the clear/hold decision from PRD §7. The lease check is a
read-only computation over stored evidence. Nothing here transitions or
blocks the case itself (DEC-0003, PRD §0).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ, CASE_TRANSITION
from ..models import ReadinessFlag
from ..schemas.api import BlockedFlagDecision, BlockedFlagOut, LeaseCheckOut
from ..services import readiness
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
)
from .deps import require, require_any

router = APIRouter(prefix="/applications/{application_id}", tags=["readiness"])


def _merge(evaluation: dict, flag: ReadinessFlag | None) -> dict:
    """Fold an officer's decision over the evaluation.

    The decision overrides ``state`` (PRD §7: the official's clear/hold is
    the authority); evaluation, reason and missing inputs stay visible so
    the officer can see *why* the flag was raised even after deciding.
    """
    if flag is None:
        return evaluation
    return {
        **evaluation,
        "decision": flag.decision,
        "decided_by": flag.decided_by,
        "decided_at": flag.decided_at,
        "note": flag.note,
        "state": flag.decision,
    }


@router.get("/blocked-flags", response_model=list[BlockedFlagOut])
def list_blocked_flags(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    """The five FR-03 flags for this application.

    Evaluation is computed here from configuration + recorded case data and
    merged with any officer decision already on file. Officers see what the
    institution sees plus their own decision fields; nothing is hidden —
    the flags are advisory and the institution's own case is readable to it.
    """
    application = require_application(db, access, application_id)
    evaluations = readiness.evaluate_blocked_flags(application)
    decisions = {
        flag.flag_id: flag
        for flag in db.scalars(
            select(ReadinessFlag).where(ReadinessFlag.application_id == application.id)
        )
    }
    return [_merge(row, decisions.get(row["flag_id"])) for row in evaluations]


@router.post("/blocked-flags/{flag_id}", response_model=BlockedFlagOut)
def decide_blocked_flag(
    application_id: str,
    flag_id: str,
    payload: BlockedFlagDecision,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """Record the officer's clear/hold decision on one flag (creates or
    updates the single decision row for this application + flag).

    Like the deficiency endpoints: gate first (403 by role), scope second
    (404 by scope, never 403 — record existence must not leak), then act.
    The decision is validated at the edge against the same two-value
    vocabulary the config declares, so no other outcome can be recorded.
    """
    application = require_application(db, access, application_id)

    evaluations = readiness.evaluate_blocked_flags(application)
    known = next((row for row in evaluations if row["flag_id"] == flag_id), None)
    if known is None:
        # Config-defined catalogue: an id the rules do not define cannot be
        # decided. Client error (404), so it is not confused with scope.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"unknown blocked flag id {flag_id!r} — not defined in readiness_policy.json",
        )

    flag = db.scalars(
        select(ReadinessFlag).where(
            ReadinessFlag.application_id == application.id,
            ReadinessFlag.flag_id == flag_id,
        )
    ).first()
    before = flag.decision if flag is not None else None

    now = get_clock().now()
    note = payload.note.strip() or None
    if flag is None:
        flag = ReadinessFlag(
            application_id=application.id,
            flag_id=flag_id,
            decision=payload.decision,
            note=note,
            decided_by=access.user_id,
            created_at=now,
            decided_at=now,
        )
        db.add(flag)
    else:
        flag.decision = payload.decision
        flag.note = note
        flag.decided_by = access.user_id
        flag.decided_at = now
    db.flush()

    application.baseline_version += 1
    AuditService(db).append(
        action="readiness_flag.decided",
        entity_type="readiness_flag",
        entity_id=flag.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=note or f"Flag {flag_id} {payload.decision}",
        before={"decision": before},
        after={
            "flag_id": flag_id,
            "decision": payload.decision,
            "evaluation": known["evaluation"],
        },
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(flag)
    return _merge(known, flag)


@router.get("/lease-check", response_model=LeaseCheckOut)
def get_lease_check(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """FR-05: remaining lease years vs the longest course duration.

    Read-only and advisory: it computes from the *persisted* grounded
    extractor output (evidence snapshot), writes nothing, and stores no
    verdict. With the shipped configuration (no recorded course duration)
    every live lease answers ``needs_review`` with the real computed years
    attached — never a guessed sufficient/insufficient (PRD §19 Q11).
    """
    application = require_application(db, access, application_id)
    valid_to, verified = readiness.lease_evidence(db, application)
    return readiness.lease_check(
        valid_to,
        as_of=get_clock().now().date(),
        verified=verified,
    )
