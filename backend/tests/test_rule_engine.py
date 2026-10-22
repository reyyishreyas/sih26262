"""Rule engine: typed outcomes, three-valued logic, allowlisted operators."""

from __future__ import annotations

import pytest

from app.services.rule_engine import (
    InvalidRuleDefinition,
    MISSING,
    RuleOutcome,
    RuleSpec,
    Snapshot,
    evaluate_rule,
    evaluate_rules,
    rule_set_version,
    unmet_blocking_rules,
    validate_condition,
)


def spec(**overrides) -> RuleSpec:
    base = dict(
        key="TEST_RULE",
        version=1,
        condition={"op": "gte", "left": {"field": "documents.lease.valid_to"}, "right": {"literal": "2027-01-01"}},
    )
    base.update(overrides)
    return RuleSpec(**base)


def test_missing_evidence_is_not_evaluated_never_false():
    snapshot = Snapshot(values={"documents": {}})
    result = evaluate_rule(spec(), snapshot)
    assert result.outcome == RuleOutcome.NOT_EVALUATED
    assert result.missing_inputs == ["documents.lease.valid_to"]
    assert "not evaluated" in result.explanation.lower()


def test_missing_outcome_is_configurable_but_explicit():
    snapshot = Snapshot(values={"documents": {}})
    result = evaluate_rule(spec(missing_outcome=RuleOutcome.FAIL), snapshot)
    assert result.outcome == RuleOutcome.FAIL


def test_unverified_evidence_needs_review():
    snapshot = Snapshot(
        values={"documents": {"lease": {"valid_to": "2028-03-31"}}},
        verified={"documents.lease.valid_to": False},
    )
    result = evaluate_rule(spec(), snapshot)
    assert result.outcome == RuleOutcome.NEEDS_REVIEW
    assert result.unverified_inputs == ["documents.lease.valid_to"]


def test_verified_evidence_passes_and_carries_source():
    snapshot = Snapshot(
        values={"documents": {"lease": {"valid_to": "2028-03-31"}}},
        verified={"documents.lease.valid_to": True},
        sources={"documents.lease.valid_to": "document:DOC-1#page=7"},
    )
    result = evaluate_rule(spec(), snapshot)
    assert result.outcome == RuleOutcome.PASS
    assert result.evidence_refs == ["document:DOC-1#page=7"]


def test_failure_outcome_can_be_needs_review():
    snapshot = Snapshot(
        values={"documents": {"lease": {"valid_to": "2026-01-01"}}},
        verified={"documents.lease.valid_to": True},
    )
    result = evaluate_rule(spec(failure_outcome=RuleOutcome.NEEDS_REVIEW), snapshot)
    assert result.outcome == RuleOutcome.NEEDS_REVIEW


def test_not_applicable_short_circuits_the_condition():
    snapshot = Snapshot(values={"application": {"category": "new_technical"}})
    result = evaluate_rule(
        spec(applicability={"op": "eq", "left": {"field": "application.category"}, "right": {"literal": "existing_technical"}}),
        snapshot,
    )
    assert result.outcome == RuleOutcome.NOT_APPLICABLE


def test_unresolvable_applicability_is_not_applicable_guessing():
    snapshot = Snapshot(values={"application": {}})
    result = evaluate_rule(
        spec(applicability={"op": "eq", "left": {"field": "application.category"}, "right": {"literal": "x"}}),
        snapshot,
    )
    assert result.outcome == RuleOutcome.NOT_EVALUATED


def test_and_with_one_false_operand_is_decided():
    """A missing operand must not hide a definite failure."""
    snapshot = Snapshot(values={})
    result = evaluate_rule(
        spec(
            condition={
                "op": "and",
                "args": [
                    {"op": "exists", "field": "documents.missing.doc"},
                    {"op": "eq", "left": {"field": "documents.a.b"}, "right": {"literal": 1}},
                ],
            }
        ),
        snapshot,
    )
    assert result.outcome == RuleOutcome.FAIL
    # The absent field is reported for transparency, but it did not decide the
    # outcome: the other operand is definitely false.
    assert result.missing_inputs == ["documents.a.b"]


def test_exists_does_not_require_field_verification():
    snapshot = Snapshot(values={"documents": {"affidavit": {"document_id": "d1"}}})
    result = evaluate_rule(
        spec(condition={"op": "exists", "field": "documents.affidavit.document_id"}),
        snapshot,
    )
    assert result.outcome == RuleOutcome.PASS


def test_determinism_and_ordering():
    snapshot = Snapshot(
        values={"documents": {"lease": {"valid_to": "2028-03-31"}}},
        verified={"documents.lease.valid_to": True},
    )
    specs = [spec(key="B"), spec(key="A")]
    first = [r.as_dict() for r in evaluate_rules(specs, snapshot)]
    second = [r.as_dict() for r in evaluate_rules(list(reversed(specs)), snapshot)]
    assert first == second
    assert [r["rule_key"] for r in first] == ["A", "B"]
    assert rule_set_version(specs) == rule_set_version(list(reversed(specs)))


def test_unrestricted_operator_is_rejected():
    with pytest.raises(InvalidRuleDefinition):
        validate_condition({"op": "eval", "code": "__import__('os').system('true')"})
    with pytest.raises(InvalidRuleDefinition):
        validate_condition({"op": "and", "args": []})
    with pytest.raises(InvalidRuleDefinition):
        validate_condition({"op": "gte", "left": {"field": "a"}})


def test_between_and_contains():
    snapshot = Snapshot(values={"application": {"days_in_state": 12, "cycle": "2026-27"}})
    between = evaluate_rule(
        spec(
            condition={
                "op": "between",
                "left": {"field": "application.days_in_state"},
                "lower": {"literal": 10},
                "upper": {"literal": 15},
            }
        ),
        snapshot,
    )
    contains = evaluate_rule(
        spec(
            condition={
                "op": "contains",
                "left": {"field": "application.cycle"},
                "right": {"literal": "2026"},
            }
        ),
        snapshot,
    )
    assert between.outcome == RuleOutcome.PASS
    assert contains.outcome == RuleOutcome.PASS


def test_unmet_blocking_rules_include_review_and_not_evaluated():
    snapshot = Snapshot(values={"documents": {}})
    results = [evaluate_rule(spec(blocking=True), snapshot)]
    assert unmet_blocking_rules(results) == results
    assert MISSING is not None
