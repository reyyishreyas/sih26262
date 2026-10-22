"""The deterministic compliance rule engine.

Design constraints (these are acceptance criteria, not style preferences):

1. **No ``eval``.** Rules are JSON using the allowlisted grammar in
   ``ALLOWED_OPERATORS``. Anything unrecognised is rejected at load time.
2. **Three-valued logic.** A condition can be true, false, or *unknown*. Unknown is
   never coerced to false.
3. **Missing evidence is explicit.** A required input that does not exist produces
   ``NOT_EVALUATED``; an input that exists but has not been verified produces
   ``NEEDS_REVIEW``. Both are configurable per rule, and both are reported with the
   exact field paths.
4. **Determinism.** Same rule version + same snapshot -> same result, always. Results
   are returned in rule-key order.

The same function is called by the operational service and by the Rehearsal Engine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class RuleOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class InvalidRuleDefinition(ValueError):
    """Raised when a stored rule uses an operator or shape we do not allow."""


ALLOWED_OPERATORS = {
    "always",
    "and",
    "or",
    "not",
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "exists",
    "missing",
    "between",
    "contains",
}

_COMPARATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
}


class _Unresolved:
    """Sentinel: the snapshot does not contain this path at all."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<missing>"


MISSING = _Unresolved()


@dataclass
class Snapshot:
    """Values plus provenance.

    ``verified`` maps leaf paths to whether a human (or an explicitly trusted
    extractor) confirmed them. Paths under ``trusted_roots`` are system-of-record
    fields and count as verified by construction.
    """

    values: dict[str, Any]
    verified: dict[str, bool] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    trusted_roots: tuple[str, ...] = ("application", "institution")

    def resolve(self, path: str) -> Any:
        node: Any = self.values
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return MISSING
        return node

    def is_verified(self, path: str) -> bool:
        if path in self.verified:
            return bool(self.verified[path])
        root = path.split(".")[0]
        if root in self.trusted_roots:
            return True
        # Any ancestor marked verified implies its leaves are verified.
        parts = path.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in self.verified:
                return bool(self.verified[prefix])
        return False

    def source(self, path: str) -> str | None:
        if path in self.sources:
            return self.sources[path]
        parts = path.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in self.sources:
                return self.sources[prefix]
        return None


@dataclass(frozen=True)
class RuleSpec:
    key: str
    version: int
    condition: dict[str, Any]
    applicability: dict[str, Any] = field(default_factory=dict)
    missing_outcome: RuleOutcome = RuleOutcome.NOT_EVALUATED
    unverified_outcome: RuleOutcome = RuleOutcome.NEEDS_REVIEW
    failure_outcome: RuleOutcome = RuleOutcome.FAIL
    blocking: bool = False
    severity: str = "major"
    title: str = ""
    regulatory_reference: str = ""
    confidence: float = 1.0

    @classmethod
    def from_orm(cls, version: Any) -> RuleSpec:
        return cls(
            key=version.rule.key,
            version=version.version,
            condition=version.condition or {},
            applicability=version.applicability or {},
            missing_outcome=RuleOutcome(version.missing_outcome),
            unverified_outcome=RuleOutcome(version.unverified_outcome),
            failure_outcome=RuleOutcome(version.failure_outcome),
            blocking=version.blocking,
            severity=version.severity,
            title=version.rule.title,
            regulatory_reference=version.rule.regulatory_reference,
        )


@dataclass
class RuleEvaluationResult:
    rule_key: str
    rule_version: int
    outcome: RuleOutcome
    explanation: str
    evidence_refs: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    unverified_inputs: list[str] = field(default_factory=list)
    blocking: bool = False
    severity: str = "major"
    regulatory_reference: str = ""
    title: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_key": self.rule_key,
            "rule_version": self.rule_version,
            "outcome": self.outcome.value,
            "explanation": self.explanation,
            "evidence_refs": self.evidence_refs,
            "missing_inputs": self.missing_inputs,
            "unverified_inputs": self.unverified_inputs,
            "blocking": self.blocking,
            "severity": self.severity,
            "regulatory_reference": self.regulatory_reference,
            "title": self.title,
        }


@dataclass
class _Trace:
    truth: bool | None
    missing: set[str] = field(default_factory=set)
    unverified: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def merge(parts: list[_Trace]) -> _Trace:
        missing: set[str] = set()
        unverified: set[str] = set()
        refs: set[str] = set()
        notes: list[str] = []
        for part in parts:
            missing |= part.missing
            unverified |= part.unverified
            refs |= part.refs
            notes.extend(part.notes)
        return _Trace(None, missing, unverified, refs, notes)


def validate_condition(node: Any, depth: int = 0) -> None:
    """Structural validation. Runs when a rule is drafted/approved, not per request."""
    if depth > 16:
        raise InvalidRuleDefinition("condition nesting too deep")
    if not isinstance(node, dict):
        raise InvalidRuleDefinition("condition node must be an object")
    op = node.get("op")
    if op not in ALLOWED_OPERATORS:
        raise InvalidRuleDefinition(f"operator not allowed: {op!r}")
    if op in {"and", "or"}:
        args = node.get("args")
        if not isinstance(args, list) or not args:
            raise InvalidRuleDefinition(f"'{op}' requires a non-empty 'args' list")
        for arg in args:
            validate_condition(arg, depth + 1)
        return
    if op == "not":
        if "arg" not in node:
            raise InvalidRuleDefinition("'not' requires 'arg'")
        validate_condition(node["arg"], depth + 1)
        return
    if op == "always":
        return
    if op in {"exists", "missing"}:
        if not isinstance(node.get("field"), str) or not node["field"]:
            raise InvalidRuleDefinition(f"operator {op!r} requires a non-empty 'field' path")
        return
    if op == "between":
        for key in ("left", "lower", "upper"):
            _require_operand(node, key)
        return
    _require_operand(node, "left")
    _require_operand(node, "right")


def _require_operand(node: dict, key: str) -> None:
    if key not in node:
        raise InvalidRuleDefinition(f"operator {node.get('op')!r} requires {key!r}")
    operand = node[key]
    if not isinstance(operand, dict):
        raise InvalidRuleDefinition(f"operand {key!r} must be an object")
    if "field" in operand:
        if not isinstance(operand["field"], str) or not operand["field"]:
            raise InvalidRuleDefinition("field operand must be a non-empty string")
    elif "literal" in operand:
        if isinstance(operand["literal"], dict):
            raise InvalidRuleDefinition("literal operands must be scalars or lists")
    else:
        raise InvalidRuleDefinition("operand needs 'field' or 'literal'")


def _literal(node: dict, snapshot: Snapshot, trace: _Trace) -> Any:
    if "field" in node:
        path = node["field"]
        value = snapshot.resolve(path)
        if value is MISSING:
            trace.missing.add(path)
            return MISSING
        if not snapshot.is_verified(path):
            trace.unverified.add(path)
        source = snapshot.source(path)
        if source:
            trace.refs.add(source)
        return value
    return node["literal"]


def _compare(op: str, left: Any, right: Any) -> bool:
    try:
        return bool(_COMPARATORS[op](left, right))
    except TypeError:
        # Comparing incomparable types is a rule defect, not a compliance answer.
        raise InvalidRuleDefinition(
            f"cannot compare {type(left).__name__} with {type(right).__name__} "
            f"using {op!r}"
        ) from None


def _eval(node: dict, snapshot: Snapshot, trace: _Trace) -> bool | None:
    op = node["op"]

    if op == "always":
        trace.notes.append("condition is unconditional")
        return True

    if op in {"exists", "missing"}:
        path = node["field"]
        value = snapshot.resolve(path)
        present = value is not MISSING and value is not None
        if present:
            source = snapshot.source(path)
            if source:
                trace.refs.add(source)
            trace.notes.append(f"{path} is present")
        else:
            trace.notes.append(f"{path} is not present")
        return present if op == "exists" else not present

    if op == "and":
        results = [_eval(arg, snapshot, trace) for arg in node["args"]]
        if any(result is False for result in results):
            return False
        if any(result is None for result in results):
            return None
        return True

    if op == "or":
        results = [_eval(arg, snapshot, trace) for arg in node["args"]]
        if any(result is True for result in results):
            return True
        if any(result is None for result in results):
            return None
        return False

    if op == "not":
        inner = _eval(node["arg"], snapshot, trace)
        return None if inner is None else not inner

    if op == "between":
        left = _literal(node["left"], snapshot, trace)
        low = _literal(node["lower"], snapshot, trace)
        high = _literal(node["upper"], snapshot, trace)
        if any(value is MISSING for value in (left, low, high)):
            return None
        result = _compare("gte", left, low) and _compare("lte", left, high)
        trace.notes.append(f"between check -> {result}")
        return result

    left = _literal(node["left"], snapshot, trace)
    right = _literal(node["right"], snapshot, trace)
    if left is MISSING or right is MISSING:
        return None
    result = _compare(op, left, right)
    trace.notes.append(f"{_describe(node['left'])} {op} {_describe(node['right'])} -> {result}")
    return result


def _describe(operand: dict) -> str:
    return operand.get("field") or repr(operand.get("literal"))


def evaluate_rule(spec: RuleSpec, snapshot: Snapshot) -> RuleEvaluationResult:
    validate_condition(spec.condition)
    if spec.applicability:
        validate_condition(spec.applicability)

    # Applicability first: a rule that does not apply is not a finding.
    if spec.applicability:
        app_trace = _Trace(truth=None)
        applies = _eval(spec.applicability, snapshot, app_trace)
        if applies is None:
            return RuleEvaluationResult(
                rule_key=spec.key,
                rule_version=spec.version,
                outcome=RuleOutcome.NOT_EVALUATED,
                explanation=(
                    "Applicability could not be decided because required inputs are "
                    "absent or unverified; the rule was not applied."
                ),
                evidence_refs=sorted(app_trace.refs),
                missing_inputs=sorted(app_trace.missing),
                unverified_inputs=sorted(app_trace.unverified),
                blocking=spec.blocking,
                severity=spec.severity,
                regulatory_reference=spec.regulatory_reference,
                title=spec.title,
            )
        if applies is False:
            return RuleEvaluationResult(
                rule_key=spec.key,
                rule_version=spec.version,
                outcome=RuleOutcome.NOT_APPLICABLE,
                explanation="The approved applicability conditions do not apply to this case.",
                evidence_refs=sorted(app_trace.refs),
                blocking=spec.blocking,
                severity=spec.severity,
                regulatory_reference=spec.regulatory_reference,
                title=spec.title,
            )

    trace = _Trace(truth=None)
    truth = _eval(spec.condition, snapshot, trace)

    if trace.unverified and truth is not None:
        # A conclusion drawn through unverified values is not a conclusion. It is
        # escalated for verification instead of being reported as PASS or FAIL.
        outcome = spec.unverified_outcome
        explanation = (
            "Condition depends on evidence that is not verified, so no automated "
            "verdict is issued: " + ", ".join(sorted(trace.unverified))
        )
    elif truth is True:
        outcome = RuleOutcome.PASS
        explanation = "Condition satisfied by the available verified evidence."
    elif truth is False:
        outcome = spec.failure_outcome
        explanation = "Condition not satisfied: " + "; ".join(trace.notes[-2:])
    elif trace.missing:
        outcome = spec.missing_outcome
        explanation = (
            "Required evidence is absent, so the rule was not evaluated: "
            + ", ".join(sorted(trace.missing))
        )
    else:
        outcome = spec.unverified_outcome
        explanation = (
            "Evidence exists but is not verified, so a human decision is required: "
            + ", ".join(sorted(trace.unverified))
        )

    return RuleEvaluationResult(
        rule_key=spec.key,
        rule_version=spec.version,
        outcome=outcome,
        explanation=explanation,
        evidence_refs=sorted(trace.refs),
        missing_inputs=sorted(trace.missing),
        unverified_inputs=sorted(trace.unverified),
        blocking=spec.blocking,
        severity=spec.severity,
        regulatory_reference=spec.regulatory_reference,
        title=spec.title,
    )


def evaluate_rules(
    specs: list[RuleSpec], snapshot: Snapshot
) -> list[RuleEvaluationResult]:
    """Deterministic: results are always returned in rule-key order."""
    results = [evaluate_rule(spec, snapshot) for spec in sorted(specs, key=lambda s: s.key)]
    return results


def rule_set_version(specs: list[RuleSpec]) -> str:
    payload = "|".join(
        f"{spec.key}@v{spec.version}:{_hash_condition(spec)}"
        for spec in sorted(specs, key=lambda s: s.key)
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _hash_condition(spec: RuleSpec) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            {"c": spec.condition, "a": spec.applicability}, sort_keys=True
        ).encode()
    ).hexdigest()[:12]


def unmet_blocking_rules(
    results: list[RuleEvaluationResult],
) -> list[RuleEvaluationResult]:
    """Blocking rules that are not satisfied.

    ``NOT_APPLICABLE`` is satisfied. ``NEEDS_REVIEW`` and ``NOT_EVALUATED`` are not
    promoted to PASS, so they block a transition that requires the rule to be met --
    which is the honest behaviour: the officer sees the reason and the field paths.
    """
    return [
        r
        for r in results
        if r.blocking and r.outcome not in (RuleOutcome.PASS, RuleOutcome.NOT_APPLICABLE)
    ]


def unresolved(results: list[RuleEvaluationResult]) -> list[RuleEvaluationResult]:
    return [r for r in results if r.outcome == RuleOutcome.NEEDS_REVIEW]


def serialise_date(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
