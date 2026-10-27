"""Phase 5.7: outcome labels are advisory and never workflow gates."""

from __future__ import annotations

from app.services import precheck_status


def _checks(*, mismatch: bool = False, verified: bool = False) -> tuple[list[dict], list[dict]]:
    evidence = [
        {
            "rule_id": rule_id,
            "rule_status": "verified" if verified else "unverified",
            "comparison": "discrepancy_signal" if mismatch and rule_id == "RULE-E01" else "matches_on_available_fields",
        }
        for rule_id in ("RULE-E01", "RULE-E02", "RULE-E03")
    ]
    site = [
        {
            "rule_id": rule_id,
            "rule_status": "verified" if verified else "unverified",
            "diagnostic": "no_configured_signal_observed",
        }
        for rule_id in ("RULE-SITE-01", "RULE-SITE-02")
    ]
    return evidence, site


def test_policy_labels_are_exact_prd_outcomes_and_never_block():
    policy = precheck_status.config()
    assert policy["status"] == "proposed_unverified"
    assert policy["advisory_only"] is True
    assert set(policy["outcomes"].values()) == {
        "PRE-CHECK PASSED",
        "REVIEW REQUIRED",
        "DEFICIENCY CANDIDATE",
    }


def test_missing_or_unverified_inputs_are_review_required_and_nonblocking():
    result = precheck_status.classify([], [])
    assert result["outcome"] == "REVIEW REQUIRED"
    assert result["blocking"] is False
    assert result["creates_deficiency"] is False
    assert result["automatic_workflow_action"] is False


def test_unverified_discrepancy_is_candidate_only_not_a_formal_deficiency():
    evidence, site = _checks(mismatch=True)
    result = precheck_status.classify(evidence, site)
    assert result["outcome"] == "DEFICIENCY CANDIDATE"
    assert result["blocking"] is False
    assert result["creates_deficiency"] is False
    assert result["automatic_workflow_action"] is False
    assert "RULE-E01" in result["triggered_rules"]
    assert result["triggered_rule_statuses"]["RULE-E01"] == "unverified"


def test_a_pass_requires_every_rule_mapping_to_be_verified():
    evidence, site = _checks(verified=False)
    result = precheck_status.classify(evidence, site)
    assert result["outcome"] == "REVIEW REQUIRED"

    evidence, site = _checks(verified=True)
    result = precheck_status.classify(evidence, site)
    assert result["outcome"] == "PRE-CHECK PASSED"
    assert result["blocking"] is False
    assert result["creates_deficiency"] is False


def test_any_discrepancy_takes_candidate_label_even_if_other_checks_are_unresolved():
    evidence, site = _checks(mismatch=True)
    site[1]["diagnostic"] = "insufficient_evidence"
    result = precheck_status.classify(evidence, site)
    assert result["outcome"] == "DEFICIENCY CANDIDATE"
    assert result["blocking"] is False
