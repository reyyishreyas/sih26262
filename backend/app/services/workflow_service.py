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

from ..core.clock import get_clock, iso
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
