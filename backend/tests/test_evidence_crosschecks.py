"""Phase 5.5: unverified E01-E03 diagnostics use extraction values only."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import ExtractedField
from app.services import evidence_crosschecks
from app.services.rule_engine import Snapshot
from app.services.three_value import record_claim


def _snapshot() -> Snapshot:
    return Snapshot(
        values={
            "documents": {
                "university_noc": {
                    "trust_name": "North Trust",
                    "old_address": "Plot 1, Example Road",
                    "survey_number": "42/3",
                    "institution_name": "North Institute",
                    "pid": "PID-001",
                    "institution_type": "technical",
                },
                "eoa_letter": {
                    "trust_name": "South Trust",
                    "institution_address": "Plot 1, Example Road",
                    "survey_number": "42/3",
                    "institution_name": "North Institute",
                    "pid": "PID-001",
                    "institution_type": "technical",
                },
            }
        },
        verified={
            "documents.university_noc.trust_name": True,
            "documents.eoa_letter.trust_name": True,
            "documents.university_noc.old_address": True,
            "documents.eoa_letter.institution_address": True,
            "documents.university_noc.survey_number": True,
            "documents.eoa_letter.survey_number": True,
            "documents.university_noc.institution_name": True,
            "documents.eoa_letter.institution_name": True,
            "documents.university_noc.pid": True,
            "documents.eoa_letter.pid": True,
            "documents.university_noc.institution_type": True,
            "documents.eoa_letter.institution_type": True,
        },
        sources={
            "documents.university_noc": "document:noc-v1",
            "documents.eoa_letter": "document:eoa-v1",
        },
    )


def test_policy_keeps_placeholder_rules_unverified_and_advisory():
    policy = evidence_crosschecks.config()
    assert policy["status"] == "unverified"
    assert policy["placeholder"] is True
    assert policy["advisory_only"] is True
    assert [rule["rule_id"] for rule in policy["rules"]] == [
        "RULE-E01",
        "RULE-E02",
        "RULE-E03",
    ]
    assert all(rule["status"] == "unverified" for rule in policy["rules"])


def test_e01_reports_a_discrepancy_but_never_a_formal_failure():
    e01 = evidence_crosschecks.evaluate(_snapshot())[0]
    assert e01["comparison"] == "discrepancy_signal"
    assert e01["comparisons"][0]["comparison"] == "mismatch"
    assert e01["outcome"] == "REVIEW REQUIRED"
    assert e01["rule_status"] == "unverified"
    assert e01["advisory_only"] is True
    assert e01["human_review"]


def test_e02_and_e03_only_report_match_when_all_configured_inputs_exist():
    results = {item["rule_id"]: item for item in evidence_crosschecks.evaluate(_snapshot())}
    assert results["RULE-E02"]["comparison"] == "matches_on_available_fields"
    assert results["RULE-E03"]["comparison"] == "matches_on_available_fields"
    assert all(item["outcome"] == "REVIEW REQUIRED" for item in results.values())


def test_missing_values_remain_review_required_instead_of_becoming_a_pass():
    snapshot = _snapshot()
    del snapshot.values["documents"]["eoa_letter"]["pid"]
    result = next(
        item for item in evidence_crosschecks.evaluate(snapshot) if item["rule_id"] == "RULE-E03"
    )
    assert result["comparison"] == "insufficient_evidence"
    assert any(item["comparison"] == "unavailable" for item in result["comparisons"])
    assert result["outcome"] == "REVIEW REQUIRED"


def test_claim_edits_cannot_change_e01_extraction_diagnostic():
    field = ExtractedField(
        document_id="synthetic-doc",
        field_name="trust_name",
        value="North Trust",
    )

    def current_snapshot() -> Snapshot:
        return _snapshot_with_trust_extraction(field.value)

    before = evidence_crosschecks.evaluate(current_snapshot())
    record_claim(
        field,
        value="South Trust",
        reason="synthetic claim edit",
        actor_id="synthetic-actor",
        at=datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
    )
    after = evidence_crosschecks.evaluate(current_snapshot())
    assert after == before
    assert after[0]["comparisons"][0]["extraction_value"] == "North Trust"
    assert after[0]["comparisons"][0]["comparison_value"] == "South Trust"
    assert after[0]["outcome"] == "REVIEW REQUIRED"


def _snapshot_with_trust_extraction(extraction: object) -> Snapshot:
    snapshot = _snapshot()
    snapshot.values["documents"]["university_noc"]["trust_name"] = extraction
    return snapshot
