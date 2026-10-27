"""Advisory E01-E03 comparisons over extraction values (FR-42).

The PRD's field paths are placeholders until official templates and source
mappings are confirmed. `md/rules.json` marks the rules blocked, so this
service reports comparison diagnostics only and never emits a compliance
pass/fail or a workflow decision.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from .policy import evidence_crosschecks_policy
from .rule_engine import MISSING, Snapshot


def config() -> dict[str, Any]:
    return evidence_crosschecks_policy()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(text.split())


def evaluate(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Compare only extracted fields; Claim and master values are never read."""
    policy = config()
    results: list[dict[str, Any]] = []
    for rule in policy["rules"]:
        comparisons: list[dict[str, Any]] = []
        for left_path, right_path in rule["field_pairs"]:
            left = snapshot.resolve(left_path)
            right = snapshot.resolve(right_path)
            available = (
                left is not MISSING
                and right is not MISSING
                and left is not None
                and right is not None
                and bool(str(left).strip())
                and bool(str(right).strip())
            )
            matches = _normalise(left) == _normalise(right) if available else None
            comparisons.append(
                {
                    "extraction_path": left_path,
                    "comparison_path": right_path,
                    "extraction_value": None if left is MISSING else left,
                    "comparison_value": None if right is MISSING else right,
                    "comparison": (
                        "match" if matches else "mismatch" if matches is False else "unavailable"
                    ),
                    "extraction_verified": snapshot.is_verified(left_path),
                    "comparison_verified": snapshot.is_verified(right_path),
                    "extraction_source": snapshot.source(left_path),
                    "comparison_source": snapshot.source(right_path),
                }
            )

        if any(item["comparison"] == "mismatch" for item in comparisons):
            comparison = "discrepancy_signal"
        elif comparisons and all(item["comparison"] == "match" for item in comparisons):
            comparison = "matches_on_available_fields"
        else:
            comparison = "insufficient_evidence"

        results.append(
            {
                "rule_id": rule["rule_id"],
                "title": rule["title"],
                "rule_status": rule["status"],
                "comparison": comparison,
                "outcome": policy["outcome"],
                "advisory_only": policy["advisory_only"],
                "human_review": policy["human_review"],
                "comparisons": comparisons,
            }
        )
    return results
