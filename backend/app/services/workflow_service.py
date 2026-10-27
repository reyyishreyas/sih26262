"""Route-aware workflow transitions with guards and audited rejections.

Order of checks is fixed and tested:

1. record visible in the caller's scope
1a. the case has not moved under the caller (optimistic concurrency): when the
    caller supplies the baseline_version it loaded and it no longer matches,
    the attempt is rejected with a reload message — see Essentials §14a
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
    Deficiency,
    EvcReport,
    EvcVisit,
    FindingDisposition,
    RuleEvaluation,
    WorkflowTransition,
    WorkflowTransitionDefinition,
)
from . import audit_service, compliance_service, stages
from .authorization_service import EffectiveAccess, can_access_application
from .case_assignment_service import assign_next_actors
from .evidence_service import build_snapshot
from .policy import reason_codes_policy
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


def _stale_version_reasons(application: Application, expected: int) -> list[str]:
    """Why a stale write was refused, in the words the officer sees.

    The message tells the caller exactly what to do (reload) rather than
    leaving them to guess why an otherwise-valid action failed.
    """
    return [
        "the case has changed since it was loaded "
        f"(expected version {expected}, current version "
        f"{application.baseline_version}) — reload the case and try again"
    ]


def _reason_code_error(applies_to: str, reason_code: str | None) -> list[str]:
    """FR-28: the structured half of a return/revert reason, from config.

    Returns refusal reasons (empty when fine). The vocabulary lives in
    `rules/reason_codes.json` (a labelled placeholder until AICTE confirms
    the official list); an unlisted code is refused rather than stored — an
    officer cannot invent a code any more than this repo invents a clause.
    The message names the valid codes so the refusal teaches the vocabulary.
    """
    valid = [
        code["id"]
        for code in reason_codes_policy().get("codes", [])
        if applies_to in code.get("applies_to", ())
    ]
    if not reason_code or not reason_code.strip():
        return [
            f"a reason code is mandatory on {applies_to} (PRD FR-28); "
            f"valid codes: {', '.join(valid)}"
        ]
    if reason_code not in valid:
        return [
            f"unknown reason code {reason_code!r} for {applies_to}; "
            f"valid codes: {', '.join(valid)}"
        ]
    return []


def request_transition(
    db: Session,
    access: EffectiveAccess,
    application_id: str,
    action: str,
    reason: str = "",
    reason_code: str | None = None,
    request_id: str | None = None,
    expected_baseline_version: int | None = None,
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

    if (
        expected_baseline_version is not None
        and expected_baseline_version != application.baseline_version
    ):
        return _reject(
            db,
            application=application,
            access=access,
            action=action,
            from_state=from_state,
            reasons=_stale_version_reasons(application, expected_baseline_version),
            request_id=request_id,
        )

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

    if action == "complete_evc":
        live_visit_id = db.scalar(
            select(EvcVisit.id).where(
                EvcVisit.application_id == application.id,
                EvcVisit.status == "scheduled",
            )
        )
        has_report = live_visit_id and db.scalar(
            select(EvcReport.id).where(EvcReport.visit_id == live_visit_id)
        )
        if not has_report:
            return _reject(
                db,
                application=application,
                access=access,
                action=action,
                from_state=from_state,
                reasons=["an EVC visit report must be recorded before the visit can be completed"],
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

    # FR-28: returns need a code AND free text. The mandate is scoped by
    # config (reason_codes.required_for_actions), not by requires_reason —
    # 'reject' also demands free text but the PRD asks no code for it.
    if action in reason_codes_policy().get("required_for_actions", ()):
        code_errors = _reason_code_error("return", reason_code)
        if code_errors:
            return _reject(
                db,
                application=application,
                access=access,
                action=action,
                from_state=from_state,
                reasons=code_errors,
                request_id=request_id,
            )
    elif reason_code and reason_code.strip():
        # Optional elsewhere, but never unvalidated: an unknown code must
        # not reach the row (it would poison the §11 metric).
        code_errors = _reason_code_error("return", reason_code)
        if code_errors:
            return _reject(
                db,
                application=application,
                access=access,
                action=action,
                from_state=from_state,
                reasons=code_errors,
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

    # FR-47: every persisted red (FAIL) or amber (NEEDS_REVIEW) finding in
    # the current operational batch needs a recorded officer disposition
    # before scrutiny can leave the scrutiny state. Advisory pre-checks are
    # intentionally excluded: they are neither persisted nor authoritative.
    if from_state == "scrutiny" and definition.to_state != "scrutiny":
        finding_rows = db.scalars(
            select(RuleEvaluation)
            .where(
                RuleEvaluation.application_id == application.id,
                RuleEvaluation.application_baseline_version == application.baseline_version,
                RuleEvaluation.context == "operational",
            )
            .order_by(RuleEvaluation.evaluated_at.desc(), RuleEvaluation.batch_id.desc())
        ).all()
        if finding_rows:
            latest_batch = max(
                finding_rows, key=lambda row: (row.evaluated_at, row.batch_id)
            ).batch_id
            findings = [row for row in finding_rows if row.batch_id == latest_batch
                        and row.outcome in ("FAIL", "NEEDS_REVIEW")]
            dispositions = {
                row.rule_evaluation_id: row.disposition
                for row in db.scalars(
                    select(FindingDisposition).where(
                        FindingDisposition.rule_evaluation_id.in_([f.id for f in findings])
                    )
                ).all()
            } if findings else {}
            undisposed = [f.rule_key for f in findings if f.id not in dispositions]
            if undisposed:
                return _reject(
                    db,
                    application=application,
                    access=access,
                    action=action,
                    from_state=from_state,
                    reasons=[
                        "every amber/red finding needs an officer disposition before scrutiny can complete: "
                        + ", ".join(undisposed)
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
            reason_code=reason_code.strip() if reason_code else None,
            created_at=now,
        )
    )
    # When returning for clarification, promote any 'draft' deficiencies to 'open'
    # so they become visible to the institution.
    if action == "return_for_clarification":
        drafts = db.scalars(
            select(Deficiency).where(
                Deficiency.application_id == application.id,
                Deficiency.status == "draft",
            )
        ).all()
        for d in drafts:
            d.status = "open"
            audit_service.AuditService(db).append(
                action="deficiency.finalized",
                entity_type="deficiency",
                entity_id=d.id,
                outcome="accepted",
                actor_id=access.user_id,
                actor_role=access.primary_role,
                reason="Finalized on application return for clarification",
                before={"status": "draft"},
                after={"status": "open"},
                request_id=request_id,
            )

    # Hand the case to whoever the route says acts from the new state, in the
    # same transaction as the move itself. Without this a case is in nobody's
    # queue, and an officer whose scope is "assigned cases" cannot see it at
    # all — the College would submit and the reviewer would see nothing.
    created_assignments = assign_next_actors(db, application)
    if created_assignments:
        audit_service.AuditService(db).append(
            action="assignment.created",
            entity_type="application",
            entity_id=application.id,
            outcome="accepted",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            after={
                "assignments": [
                    {
                        "user_id": row.user_id,
                        "committee_id": row.committee_id,
                        "role_name": row.role_name,
                    }
                    for row in created_assignments
                ]
            },
            request_id=request_id,
        )
    # Keep the EVC scheduling records in step with the workflow: when the
    # committee records the visit, the live appointment stops being pending.
    # Inside the same transaction — the case and its booking must agree, or a
    # failure here would leave the case at evc_completed with the visit still
    # "scheduled" (the queue report and the workflow would contradict).
    if action == "complete_evc":
        _complete_evc_visits(db, application.id)
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
            # FR-28: the structured code rides in the audit too, so §11's
            # "returns by reason code" metric never has to parse free text.
            "reason_code": (reason_code.strip() if reason_code else None),
        },
        request_id=request_id,
    )
    # FR-09 auto-advance: the stage list follows this authorised move in the
    # same transaction — derived bookkeeping, never a second decision point.
    # Runs only on the accepted path (a refused transition returns earlier
    # and changes no stage row).
    stages.sync_stage_instances(
        db, application, actor_id=access.user_id, from_state=from_state
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


def _complete_evc_visits(db: Session, application_id: str) -> None:
    """Mark the live appointment completed once the visit outcome is recorded.

    Runs inside the caller's transaction — it must not commit on its own.
    """
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
                # FR-28: which actions will also demand a structured code
                # (config-scoped — reason_codes.required_for_actions).
                "requires_reason_code": definition.action
                in reason_codes_policy().get("required_for_actions", ()),
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
    reason_code: str | None = None,
    request_id: str | None = None,
    expected_baseline_version: int | None = None,
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

    if (
        expected_baseline_version is not None
        and expected_baseline_version != application.baseline_version
    ):
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=_stale_version_reasons(application, expected_baseline_version),
            request_id=request_id,
        )

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

    # FR-28 covers undo too: an undo carries a code AND free text, from the
    # codes that apply to 'revert' (a return-only code does not satisfy it).
    code_errors = _reason_code_error("revert", reason_code)
    if code_errors:
        return _reject(
            db,
            application=application,
            access=access,
            action="revert",
            from_state=from_state,
            reasons=code_errors,
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
            reason_code=reason_code.strip() if reason_code else None,
            created_at=now,
        )
    )
    # A booking must not outlive the stage it was made for — and the undo
    # plus its cancellations are one step, so they share one transaction.
    cancelled = _cancel_visits_on_revert(db, application, from_state, target_state)
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
            # FR-28: the undo's structured code, for the same §11 metric.
            "reason_code": (reason_code.strip() if reason_code else None),
            "undone_transition": {
                "action": undone_action,
                "from_state": (target.before or {}).get("state"),
                "to_state": from_state,
            },
        },
        request_id=request_id,
    )
    # The stage rows rewind with the case, in the same transaction: a revert
    # that left compliance_cycle "active" while the case sits back in
    # scrutiny would make the graph lie about where the case is. retract=True
    # marks the pulled-back stage's stint as retracted, not completed.
    stages.sync_stage_instances(
        db, application, actor_id=access.user_id, from_state=from_state, retract=True
    )
    db.commit()

    notes: list[str] = []
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
    """A booking must not outlive the stage it was made for.

    Runs inside the caller's transaction — it must not commit on its own.
    """
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
    return len(visits)
