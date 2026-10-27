"""Phase 5.10 synthetic site-move fixture contract (FR-38, FR-42, FR-44)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services import doc_classifier, evidence_crosschecks, site_checks
from app.services.rule_engine import Snapshot

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "phase5_site_move"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_phase5_demo_pack_is_labelled_and_drives_advisory_checks():
    eoa = _fixture("eoa_master_record.json")
    noc = _fixture("format_2_noc.json")
    resolution = _fixture("format_3_resolution.json")

    assert "SYNTHETIC" in eoa["fixture_label"]
    assert "SYNTHETIC" in noc["fixture_label"]
    assert "SYNTHETIC" in resolution["fixture_label"]
    assert "NOT AN OFFICIAL FORM" in noc["fixture_label"]
    assert "NOT AN OFFICIAL FORM" in resolution["fixture_label"]

    assert doc_classifier.classify(page_texts=[noc["text"]])["label_id"] == "format_2_noc"
    assert doc_classifier.classify(page_texts=[resolution["text"]])["label_id"] == "format_3_resolution"

    snapshot = Snapshot(
        values={
            "documents": {
                "eoa_letter": eoa,
                "university_noc": noc,
                "format_3_resolution": resolution,
            }
        },
        verified={},
        sources={},
    )
    crosschecks = evidence_crosschecks.evaluate(snapshot)
    site01 = next(row for row in site_checks.evaluate(snapshot) if row["rule_id"] == "RULE-SITE-01")
    site02 = next(row for row in site_checks.evaluate(snapshot) if row["rule_id"] == "RULE-SITE-02")

    assert all(row["comparison"] == "matches_on_available_fields" for row in crosschecks)
    assert site01["programme_comparison"] == "all_listed"
    assert site01["outcome"] == "REVIEW REQUIRED"
    assert site02["jurisdiction_conclusion"] == "none"
    assert site02["outcome"] == "REVIEW REQUIRED"
