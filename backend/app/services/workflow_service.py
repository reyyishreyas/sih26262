"""Route-aware workflow transitions with guards and audited rejections.

Order of checks is fixed and tested:

1. record visible in the caller's scope
2. caller holds the transition permission
3. caller's role is allowed for this action
4. the transition exists for the application's route
5. the application is in the expected state
6. a reason is supplied when required
7. required documents are present
8. required rules are satisfied (PASS or NOT_APPLICABLE)

Only then is the state changed. The state change, the transition row and the audit
event share one transaction. A rejected attempt is audited afterwards, in its own
transaction, because the business transaction has been rolled back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.permissions import PermissionDenied
from ..models import (
    Application,
    WorkflowTransition,
    WorkflowTransitionDefinition,
)
from . import audit_service, compliance_service
from .authorization_service import EffectiveAccess, can_access_application
from .evidence_service import build_snapshot
from .rule_engine import RuleEvaluationResult, RuleOutcome


@dataclass
class TransitionDecision:
    accepted: bool
    action: str
    application_id: str
    from_state: str
    to_state: str | None = None
    reasons: list[str] = field(default_factory=list)
    rule_results: list[RuleEvaluationResult] = field(default_factory=list)
    audit_seq: int | None = None
    # Side effects worth telling the caller about (e.g. a cancelled booking).
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action": self.action,
            "application_id": self.application_id,
            "from_state": self.from_state,
            "to_state": self.to_state if self.accepted else self.from_state,
            "reasons": self.reasons,
            "rule_results": [r.as_dict() for r in self.rule_results],
            "audit_seq": self.audit_seq,
            "notes": self.notes,
        }


def _definition(
    db: Session, route_key: str, action: str
) -> WorkflowTransitionDefinition | None:
    return db.scalars(
        select(WorkflowTransitionDefinition).where(
            WorkflowTransitionDefinition.route_key == route_key,
            WorkflowTransitionDefinition.action == action,
        )
    ).first()


def _reject(
    db: Session,
    *,
    application: Application,
    access: EffectiveAccess,
    action: str,
    from_state: str,
    reasons: list[str],
    rule_results: list[RuleEvaluationResult] | None = None,
    request_id: str | None = None,
) -> TransitionDecision:
    reason_text = "; ".join(reasons)
    application_id = application.id
    db.rollback()
    event = audit_service.append_in_new_transaction(
        action=f"workflow.{action}",
        entity_type="application",
        entity_id=application_id,
        outcome="rejected",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason_text,
        before={"state": from_state},
        after={},
        request_id=request_id,
    )
    return TransitionDecision(
        accepted=False,
        action=action,
        application_id=application_id,
        from_state=from_state,
        reasons=reasons,
        rule_results=rule_results or [],
        audit_seq=event.seq,
    )


def request_transition(
    db: Session,
    access: EffectiveAccess,
    application_id: str,
    action: str,
    reason: str = "",
    request_id: str | None = None,
) -> TransitionDecision:
    application = db.get(Application, application_id)
    if application is None:
        raise PermissionDenied("application not found in your scope", code="not_found")

    from_state = application.current_state

    if not can_access_application(db, access, application):
        # Fall through to the rejection path so the attempt is recorded, but the
        # caller still receives a not-found style error.
        _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=["application is outside the caller's authorised scope"],
            request_id=request_id,
        )
        raise PermissionDenied("application not found in your scope", code="not_found")

    definition = _definition(db, application.route_key, action)
    if definition is None:
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[f"action {action!r} is not defined for route {application.route_key!r}"],
            request_id=request_id,
        )

    if not access.has(definition.required_permission):
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[f"missing permission {definition.required_permission!r}"],
            request_id=request_id,
        )

    if definition.allowed_roles and not (set(access.roles) & set(definition.allowed_roles)):
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[
                f"role {access.primary_role!r} may not perform {action!r} "
                f"(allowed: {', '.join(definition.allowed_roles)})"
            ],
            request_id=request_id,
        )

    if from_state != definition.from_state:
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[
                f"action {action!r} requires state {definition.from_state!r}, "
                f"case is in {from_state!r}"
            ],
            request_id=request_id,
        )

    if definition.requires_reason and not reason.strip():
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[f"action {action!r} requires a recorded reason"],
            request_id=request_id,
        )

    snapshot = build_snapshot(db, application)
    missing_documents = _missing_documents(snapshot, definition.required_documents or [])
    if missing_documents:
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=[f"required document(s) not provided: {', '.join(missing_documents)}"],
            request_id=request_id,
        )

    rule_results: list[RuleEvaluationResult] = []
    required_rules = definition.required_rules or []
    if required_rules:
        specs = [s for s in compliance_service.load_rule_specs(db) if s.key in required_rules]
        from .rule_engine import evaluate_rules

        rule_results = evaluate_rules(specs, snapshot)
        unmet = [
            result
            for result in rule_results
            if result.outcome not in (RuleOutcome.PASS, RuleOutcome.NOT_APPLICABLE)
        ]
        if unmet:
            return _reject(
                db,
                application=application,
                access=access,
                action=action,
                from_state=from_state,
                reasons=[
                    f"{result.rule_key} is {result.outcome.value}: {result.explanation}"
                    for result in unmet
                ],
                rule_results=rule_results,
                request_id=request_id,
            )

    now = get_clock().now()
    before = {"state": from_state, "baseline_version": application.baseline_version}
    application.current_state = definition.to_state
    application.status = definition.to_state
    application.current_state_since = now
    application.baseline_version = application.baseline_version + 1
    if definition.action == "submit" and application.submitted_at is None:
        application.submitted_at = now

    db.add(
        WorkflowTransition(
            application_id=application.id,
            action=action,
            from_state=from_state,
            to_state=definition.to_state,
            actor_id=access.user_id,
            reason=reason,
            created_at=now,
        )
    )
    event = audit_service.AuditService(db).append(
        action=f"workflow.{action}",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason,
        before=before,
        after={
            "state": definition.to_state,
            "baseline_version": application.baseline_version,
        },
        request_id=request_id,
    )
    db.commit()

    # Keep the EVC scheduling records in step with the workflow: when the
    # committee records the visit, the live appointment stops being pending.
    if action == "complete_evc":
        _complete_evc_visits(db, application.id)

    return TransitionDecision(
        accepted=True,
        action=action,
        application_id=application.id,
        from_state=from_state,
        to_state=definition.to_state,
        rule_results=rule_results,
        audit_seq=event.seq,
    )


def _missing_documents(snapshot, doc_types: list[str]) -> list[str]:
    from .rule_engine import MISSING

    missing = []
    for doc_type in doc_types:
        value = snapshot.resolve(f"documents.{doc_type}.document_id")
        if value is MISSING or value is None:
            missing.append(doc_type)
    return missing


def _complete_evc_visits(db: Session, application_id: str) -> None:
    """Mark the live appointment completed once the visit outcome is recorded."""
    from ..models import EvcVisit

    now = get_clock().now()
    visits = db.scalars(
        select(EvcVisit).where(
            EvcVisit.application_id == application_id,
            EvcVisit.status == "scheduled",
        )
    ).all()
    for visit in visits:
        visit.status = "completed"
        visit.completed_at = now
    if visits:
        db.commit()


def available_transitions(
    db: Session, access: EffectiveAccess, application: Application
) -> list[dict[str, Any]]:
    definitions = db.scalars(
        select(WorkflowTransitionDefinition).where(
            WorkflowTransitionDefinition.route_key == application.route_key,
            WorkflowTransitionDefinition.from_state == application.current_state,
        )
    ).all()
    snapshot = build_snapshot(db, application)
    specs = {s.key: s for s in compliance_service.load_rule_specs(db)}
    from .rule_engine import evaluate_rules

    out = []
    for definition in definitions:
        unmet: list[str] = []
        if not access.has(definition.required_permission):
            unmet.append(f"missing permission: {definition.required_permission}")
        if definition.allowed_roles and not (
            set(access.roles) & set(definition.allowed_roles)
        ):
            unmet.append("role not permitted")
        missing = _missing_documents(snapshot, definition.required_documents or [])
        if missing:
            unmet.append("missing documents: " + ", ".join(missing))
        required = [specs[key] for key in (definition.required_rules or []) if key in specs]
        for result in evaluate_rules(required, snapshot):
            if result.outcome not in (RuleOutcome.PASS, RuleOutcome.NOT_APPLICABLE):
                unmet.append(f"{result.rule_key}: {result.outcome.value}")
        out.append(
            {
                "action": definition.action,
                "from_state": definition.from_state,
                "to_state": definition.to_state,
                "requires_reason": definition.requires_reason,
                "available": not unmet,
                "blocked_by": unmet,
            }
        )
    return sorted(out, key=lambda item: item["action"])


# ---------------------------------------------------------------------------
# Automatic stage movement
# ---------------------------------------------------------------------------


def auto_transition_if_available(
    db: Session,
    access: EffectiveAccess,
    application_id: str,
    action: str,
    reason: str = "",
) -> TransitionDecision | None:
    """Move the case forward *only* when the trigger satisfies an already-available
    transition.

    Used by operational actions that imply a stage change — booking a committee
    visit is the obvious one: the case should land on the committee stage with
    the booking, not wait for a second click. If the transition's guards are not
    met (missing evidence, rule still failing, wrong role) nothing moves and
    nothing is audited as a failure — the operational action stands on its own.
    """
    application = db.get(Application, application_id)
    if application is None:
        return None
    option = next(
        (
            entry
            for entry in available_transitions(db, access, application)
            if entry["action"] == action and entry["available"]
        ),
        None,
    )
    if option is None:
        return None
    return request_transition(db, access, application_id, action, reason)


# ---------------------------------------------------------------------------
# Revert (undo the last step)
# ---------------------------------------------------------------------------

TERMINAL_STATES = ("approved", "rejected")


def revert_last_transition(
    db: Session,
    access: EffectiveAccess,
    application_id: str,
    reason: str,
    request_id: str | None = None,
) -> TransitionDecision:
    """Take the case back one step, with the undo recorded like everything else.

    Only the most recent *forward* step that has not already been undone can be
    reverted, and only while the case is still in the state that step produced —
    otherwise the undo would silently skip stages. Reverting out of a final
    decision (approved/rejected) needs the decision permission, not just the
    transition permission.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise PermissionDenied("application not found in your scope", code="not_found")

    from_state = application.current_state

    if not can_access_application(db, access, application):
        _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=["application is outside the caller's authorised scope"],
            request_id=request_id,
        )
        raise PermissionDenied("application not found in your scope", code="not_found")

    from ..core.permissions import CASE_DECIDE, CASE_TRANSITION

    required = CASE_DECIDE if from_state in TERMINAL_STATES else CASE_TRANSITION
    if not access.has(required):
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=[
                f"undoing a step from “{from_state}” needs the {required!r} permission"
            ],
            request_id=request_id,
        )

    if not reason.strip():
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=["undoing a step requires a recorded reason"],
            request_id=request_id,
        )

    # Which step to undo is read from the audit chain, not from timestamps:
    # the audit sequence is monotonic even when the clock is frozen (tests)
    # or two steps land in the same microsecond.
    from ..models import AuditEvent

    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "application",
            AuditEvent.entity_id == application.id,
            AuditEvent.outcome == "accepted",
            AuditEvent.action.like("workflow.%"),
            AuditEvent.action != "workflow.revert",
        )
        .order_by(AuditEvent.seq.desc())
    ).all()
    target = next(
        (event for event in events if (event.after or {}).get("state") == from_state),
        None,
    )
    if target is None:
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=["there is nothing to undo on this case"],
            request_id=request_id,
        )

    undone_action = target.action.split(".", 1)[1]
    last = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application.id,
            WorkflowTransition.action == undone_action,
            WorkflowTransition.to_state == from_state,
            WorkflowTransition.reverted_at.is_(None),
        )
        .order_by(WorkflowTransition.created_at.desc())
    ).first()

    now = get_clock().now()
    before = {"state": from_state, "baseline_version": application.baseline_version}
    target_state = (target.before or {}).get("state") or (last.from_state if last else None)
    if target_state is None:
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=[f"the record of step {undone_action!r} is incomplete; not undoing it"],
            request_id=request_id,
        )
    application.current_state = target_state
    application.status = target_state
    application.current_state_since = now
    application.baseline_version = application.baseline_version + 1

    # The undone step stays in the table, marked — deleting it would make the
    # history dishonest. The undo is a new row on top.
    if last is not None:
        last.reverted_at = now
        last.reverted_by = access.user_id
    db.add(
        WorkflowTransition(
            application_id=application.id,
            action="revert",
            from_state=from_state,
            to_state=target_state,
            actor_id=access.user_id,
            reason=reason.strip(),
            created_at=now,
        )
    )
    event = audit_service.AuditService(db).append(
        action="workflow.revert",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason.strip(),
        before=before,
        after={
            "state": target_state,
            "undone_transition": {
                "action": undone_action,
                "from_state": (target.before or {}).get("state"),
                "to_state": from_state,
            },
        },
        request_id=request_id,
    )
    db.commit()

    notes: list[str] = []
    cancelled = _cancel_visits_on_revert(db, application, from_state, target_state)
    if cancelled:
        notes.append(
            f"{cancelled} committee visit booking(s) were cancelled — the case is "
            "no longer at the committee stage"
        )

    return TransitionDecision(
        accepted=True,
        action="revert",
        application_id=application.id,
        from_state=from_state,
        to_state=target_state,
        audit_seq=event.seq,
        notes=notes,
    )


def _cancel_visits_on_revert(
    db: Session, application: Application, from_state: str, to_state: str
) -> int:
    """A booking must not outlive the stage it was made for."""
    from ..models import EvcVisit

    if "evc" not in from_state or "evc" in to_state:
        return 0

    visits = db.scalars(
        select(EvcVisit).where(
            EvcVisit.application_id == application.id,
            EvcVisit.status == "scheduled",
        )
    ).all()
    for visit in visits:
        visit.status = "cancelled"
    if visits:
        audit_service.AuditService(db).append(
            action="evc.visit_cancelled",
            entity_type="application",
            entity_id=application.id,
            outcome="accepted",
            actor_role="system",
            reason="the case was taken back a step, so the booking no longer applies",
            after={"cancelled": len(visits)},
        )
        db.commit()
    return len(visits)
