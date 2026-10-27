"""Advisory aggregate for Phase 5 pre-check labels (FR-46)."""

from __future__ import annotations

from typing import Any

from .policy import precheck_policy


def config() -> dict[str, Any]:
    return precheck_policy()


def classify(
    evidence_checks: list[dict[str, Any]], site_checks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Label the review packet without creating a finding or gate."""
    policy = config()
    checks = [*evidence_checks, *site_checks]
    triggered = [
        item
        for item in evidence_checks
        if item.get("comparison") == "discrepancy_signal"
    ] + [
        item
        for item in site_checks
        if item.get("diagnostic") == "potential_partial_coverage"
    ]

    if triggered:
        outcome = policy["outcomes"]["deficiency_candidate"]
    else:
        complete = len(checks) == 5 and all(
            item.get("rule_status") == "verified"
            and (
                item.get("comparison") == "matches_on_available_fields"
                or item.get("diagnostic")
                in ("no_configured_signal_observed", "verified_inside_jurisdiction")
            )
            for item in checks
        )
        outcome = (
            policy["outcomes"]["passed"]
            if complete
            else policy["outcomes"]["review_required"]
        )

    return {
        "outcome": outcome,
        "rule_statuses": {item.get("rule_id"): item.get("rule_status") for item in checks},
        "triggered_rules": [item.get("rule_id") for item in triggered],
        "triggered_rule_statuses": {
            item.get("rule_id"): item.get("rule_status") for item in triggered
        },
        "checked_rules": len(checks),
        "blocking": policy["blocking"],
        "creates_deficiency": policy["creates_deficiency"],
        "automatic_workflow_action": policy["automatic_workflow_action"],
        "human_review_required": policy["human_review_required"],
        "advisory_only": policy["advisory_only"],
        "note": policy["note"],
    }
