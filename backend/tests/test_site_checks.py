"""Phase 5.6: SITE-01/02 remain diagnostic and never decide applicability."""

from __future__ import annotations

from app.services import site_checks
from app.services.rule_engine import Snapshot


def _snapshot(values: dict) -> Snapshot:
    return Snapshot(values=values, verified={}, sources={})


def test_site_policies_are_unverified_and_jurisdiction_data_is_synthetic():
    policy = site_checks.config()
    jurisdiction = site_checks.jurisdiction_config()
    assert policy["status"] == "unverified"
    assert policy["advisory_only"] is True
    assert jurisdiction["status"] == "synthetic_fixture_only"
    assert jurisdiction["unverified"] is True
    assert all("SYNTHETIC" in row["university"] for row in jurisdiction["entries"])


def test_site01_reports_configured_phrase_and_programme_discrepancies_as_review():
    snapshot = _snapshot(
        {
            "documents": {
                "format_3_resolution": {
                    "resolution_text": "Partial shifting may occur.",
                    "programmes_covered": ["AI", "Civil"],
                },
                "eoa_letter": {"approved_programmes": ["AI", "Civil", "Mechanical"]},
            }
        }
    )
    site01 = next(item for item in site_checks.evaluate(snapshot) if item["rule_id"] == "RULE-SITE-01")
    assert site01["diagnostic"] == "potential_partial_coverage"
    assert site01["phrase_signal"] is True
    assert site01["programme_comparison"] == "some_not_listed"
    assert site01["outcome"] == "REVIEW REQUIRED"
    assert site01["advisory_only"] is True


def test_site01_missing_lists_or_text_remain_insufficient_evidence():
    site01 = next(
        item
        for item in site_checks.evaluate(_snapshot({"documents": {}}))
        if item["rule_id"] == "RULE-SITE-01"
    )
    assert site01["diagnostic"] == "insufficient_evidence"
    assert site01["programme_comparison"] == "unavailable"
    assert site01["outcome"] == "REVIEW REQUIRED"


def test_site01_complete_fixture_comparison_is_not_a_formal_pass():
    site01 = next(
        item
        for item in site_checks.evaluate(
            _snapshot(
                {
                    "documents": {
                        "format_3_resolution": {
                            "resolution_text": "The resolution addresses relocation.",
                            "programmes_covered": ["AI", "Civil"],
                        },
                        "eoa_letter": {"approved_programmes": ["AI", "Civil"]},
                    }
                }
            )
        )
        if item["rule_id"] == "RULE-SITE-01"
    )
    assert site01["diagnostic"] == "no_configured_signal_observed"
    assert site01["outcome"] == "REVIEW REQUIRED"


def test_site02_only_matches_synthetic_fixture_and_never_claims_outside():
    policy = site_checks.config()["site_02"]
    fixture = site_checks.jurisdiction_config()
    university_field = policy["university_path"].split(".")[-1]
    region_field = policy["proposed_region_path"].split(".")[-1]
    entry = fixture["entries"][0]
    values = {
        "documents": {
            "university_noc": {
                university_field: entry["university"],
                region_field: entry["regions"][0],
            }
        }
    }
    site02 = next(
        item for item in site_checks.evaluate(_snapshot(values)) if item["rule_id"] == "RULE-SITE-02"
    )
    assert site02["diagnostic"] == "synthetic_fixture_match"
    assert site02["outcome"] == "REVIEW REQUIRED"
    assert site02["jurisdiction_conclusion"] == "none"

    values["documents"]["university_noc"][region_field] = "Unlisted Region"
    unknown = next(
        item
        for item in site_checks.evaluate(_snapshot(values))
        if item["rule_id"] == "RULE-SITE-02"
    )
    assert unknown["diagnostic"] == "no_synthetic_fixture_match"
    assert unknown["jurisdiction_conclusion"] == "none"
    assert unknown["outcome"] == "REVIEW REQUIRED"


def test_site02_missing_values_are_not_classed_outside_jurisdiction():
    site02 = next(
        item
        for item in site_checks.evaluate(_snapshot({"documents": {}}))
        if item["rule_id"] == "RULE-SITE-02"
    )
    assert site02["diagnostic"] == "insufficient_evidence"
    assert site02["jurisdiction_conclusion"] == "none"
    assert site02["outcome"] == "REVIEW REQUIRED"
