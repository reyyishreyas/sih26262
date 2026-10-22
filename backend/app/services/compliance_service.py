"""Operational compliance assessment: load approved rules, evaluate, persist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..models import Application, RuleEvaluation, RuleVersion
from .evidence_service import build_snapshot
from .rule_engine import (
    RuleEvaluationResult,
    RuleOutcome,
    RuleSpec,
    Snapshot,
    evaluate_rules,
    rule_set_version,
    unmet_blocking_rules,
    unresolved,
)


@dataclass
class AssessmentReport:
    application_id: str
    baseline_version: int
    evaluated_at: str
    rule_set_version: str
    batch_id: str
    results: list[RuleEvaluationResult] = field(default_factory=list)

    @property
    def blocking_unmet(self) -> list[RuleEvaluationResult]:
        return unmet_blocking_rules(self.results)

    @property
    def unresolved(self) -> list[RuleEvaluationResult]:
        return unresolved(self.results)

    def counted(self) -> dict[str, int]:
        counts = {outcome.value: 0 for outcome in RuleOutcome}
        for result in self.results:
            counts[result.outcome.value] += 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "baseline_version": self.baseline_version,
            "evaluated_at": self.evaluated_at,
            "rule_set_version": self.rule_set_version,
            "batch_id": self.batch_id,
            "counts": self.counted(),
            "blocking_unmet": [r.as_dict() for r in self.blocking_unmet],
            "needs_review": [r.as_dict() for r in self.unresolved],
            "findings": [r.as_dict() for r in self.results],
        }


def load_rule_specs(db: Session, on_date: date | None = None) -> list[RuleSpec]:
    """Approved, currently effective rule versions. One per rule key (highest wins)."""
    on_date = on_date or get_clock().now().date()
    versions = db.scalars(
        select(RuleVersion).where(RuleVersion.status == "approved")
    ).all()

    chosen: dict[str, RuleVersion] = {}
    for version in versions:
        if version.effective_from and version.effective_from > on_date:
            continue
        if version.effective_to and version.effective_to < on_date:
            continue
        current = chosen.get(version.rule.key)
        if current is None or version.version > current.version:
            chosen[version.rule.key] = version

    return [RuleSpec.from_orm(version) for version in chosen.values()]


def evaluate_application(
    db: Session, application: Application, *, persist: bool = True, batch_id: str | None = None
) -> AssessmentReport:
    from ..models.base import new_id

    now = get_clock().now()
    specs = load_rule_specs(db, now.date())
    snapshot = build_snapshot(db, application)
    results = evaluate_rules(specs, snapshot)

    batch = batch_id or new_id()
    if persist:
        for result in results:
            db.add(
                RuleEvaluation(
                    application_id=application.id,
                    rule_key=result.rule_key,
                    rule_version=result.rule_version,
                    outcome=result.outcome.value,
                    explanation=result.explanation,
                    evidence_refs=result.evidence_refs,
                    missing_inputs=result.missing_inputs,
                    blocking=result.blocking,
                    application_baseline_version=application.baseline_version,
                    context="operational",
                    batch_id=batch,
                    evaluated_at=now,
                )
            )
        db.flush()

    return AssessmentReport(
        application_id=application.id,
        baseline_version=application.baseline_version,
        evaluated_at=iso(now) or "",
        rule_set_version=rule_set_version(specs),
        batch_id=batch,
        results=results,
    )


def evaluate_snapshot(
    specs: list[RuleSpec], snapshot: Snapshot
) -> list[RuleEvaluationResult]:
    """Used by the Rehearsal Engine, which must not re-read mutable production state."""
    return evaluate_rules(specs, snapshot)
