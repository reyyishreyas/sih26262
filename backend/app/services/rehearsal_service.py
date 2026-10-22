"""The Approval Rehearsal ("Crash-Test") Engine.

Isolation is structural, not a promise in a README:

* the baseline is read through a connection that is set READ ONLY, so a stray write
  fails at the driver;
* hypothetical values live in a copied in-memory snapshot, never in an ORM object;
* results are written through ``SimResultsWriter``, which refuses anything that is
  not a simulation record;
* the response carries ``production_modified: false`` and the baseline version it was
  computed from, so a caller can prove the claim.

The metric slot is intentionally empty. ``load_factor`` stays ``null`` until its
formula, units, edge cases and test matrix are documented and validated; the
finding-level diff is the real output.
"""

from __future__ import annotations

import copy
import re
from datetime import date
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import open_readonly_session, open_sim_results_session
from ..core.permissions import PermissionDenied, REHEARSAL_RUN
from ..models import Application, WorkflowTransitionDefinition
from ..models.base import new_id
from ..models.rehearsal import SimInputSnapshot, SimMetric, SimRuleResult, SimRun
from .authorization_service import EffectiveAccess, can_access_application, require_permission
from .compliance_service import load_rule_specs
from .evidence_service import build_snapshot
from .rule_engine import (
    MISSING,
    RuleEvaluationResult,
    RuleOutcome,
    Snapshot,
    evaluate_rules,
    rule_set_version,
)

ALLOWED_OVERRIDE_ROOTS = ("documents", "undertakings")
MAX_OVERRIDES = 25
_SEGMENT = re.compile(r"^[a-z0-9_]+$")
_SCALAR = (str, int, float, bool, type(None))
_DATE_FIELDS = {"valid_to", "valid_from", "lease_expiry", "due_at"}


class OverrideRejected(ValueError):
    """A hypothetical change we refuse to invent."""


@dataclass
class RehearsalReport:
    run_id: str
    application_id: str
    baseline_version: int
    rule_set_version: str
    baseline: list[RuleEvaluationResult]
    simulated: list[RuleEvaluationResult]
    diff: list[dict[str, Any]]
    assumptions: list[str]
    workflow_implications: list[dict[str, Any]]
    superseded: bool = False

    def counted(self, results: list[RuleEvaluationResult]) -> dict[str, int]:
        counts = {outcome.value: 0 for outcome in RuleOutcome}
        for result in results:
            counts[result.outcome.value] += 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        by_change: dict[str, int] = {}
        for item in self.diff:
            by_change[item["change"]] = by_change.get(item["change"], 0) + 1
        return {
            "run_id": self.run_id,
            "application_id": self.application_id,
            "baseline_version": self.baseline_version,
            "rule_set_version": self.rule_set_version,
            "production_modified": False,
            "superseded": self.superseded,
            "summary": {
                "resolved_findings": by_change.get("resolved", 0),
                "remaining_findings": by_change.get("remaining", 0),
                "new_findings": by_change.get("new", 0),
                "regressed_findings": by_change.get("regressed", 0),
                "baseline_counts": self.counted(self.baseline),
                "simulated_counts": self.counted(self.simulated),
            },
            "diff": self.diff,
            "workflow_implications": self.workflow_implications,
            "assumptions": self.assumptions,
            "metrics": {"load_factor": None, "formula_version": None},
            "baseline_findings": [r.as_dict() for r in self.baseline],
            "simulated_findings": [r.as_dict() for r in self.simulated],
        }


def validate_overrides(overrides: dict[str, Any]) -> list[str]:
    if not isinstance(overrides, dict):
        raise OverrideRejected("overrides must be an object of path -> value")
    if len(overrides) > MAX_OVERRIDES:
        raise OverrideRejected(f"at most {MAX_OVERRIDES} hypothetical changes per run")

    assumptions: list[str] = []
    for path, value in overrides.items():
        if not isinstance(path, str):
            raise OverrideRejected("override paths must be strings")
        parts = path.split(".")
        if parts[0] not in ALLOWED_OVERRIDE_ROOTS:
            raise OverrideRejected(
                f"override {path!r} is not evidence; only "
                f"{', '.join(ALLOWED_OVERRIDE_ROOTS)} fields can be rehearsed"
            )
        if len(parts) < 3:
            raise OverrideRejected(
                f"override {path!r} is too broad; address a single field "
                "(e.g. documents.lease_deed.valid_to)"
            )
        if any(not _SEGMENT.match(part) for part in parts):
            raise OverrideRejected(f"override {path!r} contains an invalid segment")
        if isinstance(value, (dict, list)):
            raise OverrideRejected(f"override {path!r} must be a scalar value")
        if not isinstance(value, _SCALAR):
            raise OverrideRejected(f"override {path!r} has an unsupported type")
        if isinstance(value, str) and len(value) > 256:
            raise OverrideRejected(f"override {path!r} is too long")
        if parts[-1] in _DATE_FIELDS:
            if not isinstance(value, str):
                raise OverrideRejected(
                    f"override {path!r} must be an ISO date string, not "
                    f"{type(value).__name__}"
                )
            try:
                date.fromisoformat(value)
            except ValueError:
                raise OverrideRejected(
                    f"override {path!r} is not a valid ISO date: {value!r}"
                ) from None
        assumptions.append(
            f"{path} is assumed to be {value!r} and treated as verified for this "
            "rehearsal only"
        )
    return assumptions


def _apply(base: Snapshot, overrides: dict[str, Any], assumptions: list[str]) -> Snapshot:
    values = copy.deepcopy(base.values)
    verified = dict(base.verified)
    sources = dict(base.sources)
    for path, value in overrides.items():
        parts = path.split(".")
        node = values
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
        verified[path] = True
        sources[path] = "rehearsal:hypothetical"
    return Snapshot(
        values=values,
        verified=verified,
        sources=sources,
        trusted_roots=base.trusted_roots,
    )


def _classify(before: RuleEvaluationResult, after: RuleEvaluationResult) -> str:
    if before.outcome == after.outcome:
        return "unchanged"
    if after.outcome == RuleOutcome.PASS:
        return "resolved"
    if before.outcome == RuleOutcome.PASS:
        return "regressed"
    if before.outcome == RuleOutcome.NOT_APPLICABLE:
        return "new"
    return "remaining"


def run_rehearsal(
    db: Session,
    access: EffectiveAccess,
    application_id: str,
    overrides: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    require_permission(access, REHEARSAL_RUN)

    overrides = overrides or {}
    assumptions = validate_overrides(overrides)

    # --- 1-2: authorise, then capture a consistent baseline through a RO connection.
    application = db.get(Application, application_id)
    if application is None or not can_access_application(db, access, application):
        raise PermissionDenied("application not found in your scope", code="not_found")

    with open_readonly_session() as ro:
        frozen_app = ro.get(Application, application_id)
        if frozen_app is None:
            raise PermissionDenied("application not found", code="not_found")
        baseline_snapshot = build_snapshot(ro, frozen_app)
        specs = load_rule_specs(ro)
        baseline_version = frozen_app.baseline_version
        route_key = frozen_app.route_key
        current_state = frozen_app.current_state
        definitions = ro.scalars(
            select(WorkflowTransitionDefinition).where(
                WorkflowTransitionDefinition.route_key == route_key,
                WorkflowTransitionDefinition.from_state == current_state,
            )
        ).all()
        definition_rows = [
            {
                "action": d.action,
                "to_state": d.to_state,
                "required_rules": list(d.required_rules or []),
                "required_documents": list(d.required_documents or []),
            }
            for d in definitions
        ]

    # --- 3-4: hypothetical snapshot and identical evaluation.
    hypothetical = _apply(baseline_snapshot, overrides, assumptions)
    baseline_results = evaluate_rules(specs, baseline_snapshot)
    simulated_results = evaluate_rules(specs, hypothetical)

    simulated_by_key = {r.rule_key: r for r in simulated_results}
    diff = []
    for before in baseline_results:
        after = simulated_by_key[before.rule_key]
        diff.append(
            {
                "rule_key": before.rule_key,
                "rule_version": before.rule_version,
                "before": before.outcome.value,
                "after": after.outcome.value,
                "change": _classify(before, after),
                "blocking": before.blocking,
                "before_explanation": before.explanation,
                "after_explanation": after.explanation,
            }
        )

    # --- 5: workflow implications, computed and never applied.
    implications = []
    for definition in definition_rows:
        blocked = []
        for rule_key in definition["required_rules"]:
            result = simulated_by_key.get(rule_key)
            if result is None:
                blocked.append(f"{rule_key} is not in the approved rule set")
            elif result.outcome not in (RuleOutcome.PASS, RuleOutcome.NOT_APPLICABLE):
                blocked.append(f"{rule_key}: {result.outcome.value}")
        for doc_type in definition["required_documents"]:
            if hypothetical.resolve(f"documents.{doc_type}.document_id") is MISSING:
                blocked.append(f"missing document: {doc_type}")
        implications.append(
            {
                "action": definition["action"],
                "to_state": definition["to_state"],
                "eligible": not blocked,
                "blocked_by": blocked,
                "note": "hypothetical only — no transition was attempted",
            }
        )

    report = RehearsalReport(
        run_id=new_id(),
        application_id=application_id,
        baseline_version=baseline_version,
        rule_set_version=rule_set_version(specs),
        baseline=baseline_results,
        simulated=simulated_results,
        diff=diff,
        assumptions=assumptions
        + (["baseline captured read-only and evaluated at the same rule versions"]),
        workflow_implications=implications,
    )

    # --- 6: persist to simulation storage only.
    now = get_clock().now()
    with open_sim_results_session() as writer:
        run = SimRun(
            id=report.run_id,
            application_id=application_id,
            run_by=access.user_id,
            status="completed",
            baseline_version=baseline_version,
            rule_set_version=report.rule_set_version,
            created_at=now,
            completed_at=now,
        )
        writer.add(run)
        writer.flush()
        writer.add(
            SimInputSnapshot(
                run_id=run.id,
                baseline={
                    "values": baseline_snapshot.values,
                    "verified": baseline_snapshot.verified,
                    "sources": baseline_snapshot.sources,
                    "route_key": route_key,
                    "current_state": current_state,
                },
                overrides=overrides,
                assumptions=report.assumptions,
            )
        )
        for item, before, after in zip(diff, baseline_results, simulated_results):
            writer.add(
                SimRuleResult(
                    run_id=run.id,
                    rule_key=item["rule_key"],
                    rule_version=item["rule_version"],
                    before_outcome=before.outcome.value,
                    after_outcome=after.outcome.value,
                    before_explanation=before.explanation,
                    after_explanation=after.explanation,
                    change=item["change"],
                    blocking=item["blocking"],
                )
            )
        writer.add(
            SimMetric(
                run_id=run.id,
                name="load_factor",
                value=None,
                formula_version=None,
                inputs={},
            )
        )

    # --- 7: a run computed from a stale baseline is marked, not silently mixed.
    current = db.get(Application, application_id)
    if current is not None and current.baseline_version != baseline_version:
        report.superseded = True
        with open_sim_results_session() as writer:
            stored = writer.get_run(report.run_id)
            if stored is not None:
                stored.superseded = True
                stored.status = "superseded"

    return report.as_dict()


def get_run(run_id: str) -> dict[str, Any] | None:
    """Read-back from simulation storage, rebuilt from the stored rows."""
    with open_sim_results_session() as writer:
        run = writer.get_run(run_id)
        if run is None:
            return None
        session = writer.session
        snapshot = session.scalars(
            select(SimInputSnapshot).where(SimInputSnapshot.run_id == run_id)
        ).first()
        rows = session.scalars(
            select(SimRuleResult).where(SimRuleResult.run_id == run_id)
        ).all()
        metrics = session.scalars(
            select(SimMetric).where(SimMetric.run_id == run_id)
        ).all()
        return {
            "run_id": run.id,
            "application_id": run.application_id,
            "baseline_version": run.baseline_version,
            "rule_set_version": run.rule_set_version,
            "status": run.status,
            "superseded": run.superseded,
            "production_modified": False,
            "overrides": snapshot.overrides if snapshot else {},
            "assumptions": snapshot.assumptions if snapshot else [],
            "diff": [
                {
                    "rule_key": row.rule_key,
                    "rule_version": row.rule_version,
                    "before": row.before_outcome,
                    "after": row.after_outcome,
                    "change": row.change,
                    "blocking": row.blocking,
                }
                for row in rows
            ],
            "metrics": {
                item.name: item.value for item in metrics
            }
            | {"formula_version": None, "load_factor": None},
            "created_at": iso(run.created_at),
        }
