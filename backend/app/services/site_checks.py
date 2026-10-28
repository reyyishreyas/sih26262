"""Unverified SITE-01/02 diagnostics (FR-43/FR-44).

The resolution phrase list and jurisdiction fixture demonstrate prototype
lookup behavior only. Neither can establish a formal compliance outcome.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from .policy import jurisdiction_policy, site_check_policy
from .rule_engine import MISSING, Snapshot


def config() -> dict[str, Any]:
    return site_check_policy()


def jurisdiction_config() -> dict[str, Any]:
    return jurisdiction_policy()


def _normalise_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(text.split())


def _path_value(snapshot: Snapshot, path: str) -> object:
    value = snapshot.resolve(path)
    return None if value is MISSING else value


def _programme_names(value: object) -> set[str] | None:
    """Approved/covered programme names from a stored value.

    Two shapes arrive at the paths (both documented in the site policy):
    a list of names (the synthetic Phase 5.10 fixtures) and the visual
    comma list the real Format-2/3 parser stores (so its bbox can be
    placed on the printed line). Anything else — a blank list, anything
    but names — is honestly unreadable, not an empty set.
    """
    if isinstance(value, str) and value.strip():
        names = [name.strip() for name in value.split(",") if name.strip()]
    elif isinstance(value, list) and value:
        names = value
    else:
        return None
    if any(not isinstance(name, str) or not name.strip() for name in names):
        return None
    return {_normalise_text(name) for name in names}


def _site01(snapshot: Snapshot, policy: dict[str, Any]) -> dict[str, Any]:
    rule = policy["site_01"]
    text = _path_value(snapshot, rule["resolution_text_path"])
    phrase_matches = []
    if isinstance(text, str) and text.strip():
        normalised_text = _normalise_text(text)
        phrase_matches = [
            phrase
            for phrase in rule["partial_shift_phrases"]
            if _normalise_text(phrase) in normalised_text
        ]

    approved_path = rule["approved_programmes_path"]
    covered_path = rule["programmes_covered_path"]
    approved = _programme_names(_path_value(snapshot, approved_path))
    covered = _programme_names(_path_value(snapshot, covered_path))
    missing_programmes = sorted(approved - covered) if approved and covered else []
    programme_comparison = (
        "some_not_listed"
        if missing_programmes
        else "all_listed"
        if approved is not None and covered is not None
        else "unavailable"
    )

    if phrase_matches or missing_programmes:
        diagnostic = "potential_partial_coverage"
    elif approved is not None and covered is not None and isinstance(text, str) and text.strip():
        diagnostic = "no_configured_signal_observed"
    else:
        diagnostic = "insufficient_evidence"

    return {
        "rule_id": rule["rule_id"],
        "title": rule["title"],
        "rule_status": rule["status"],
        "diagnostic": diagnostic,
        "outcome": policy["outcome"],
        "advisory_only": policy["advisory_only"],
        "human_review": policy["human_review"],
        "phrase_signal": bool(phrase_matches),
        "matched_phrases": phrase_matches,
        "programme_comparison": programme_comparison,
        "missing_programmes": missing_programmes,
        "evidence_paths": [rule["resolution_text_path"], approved_path, covered_path],
        "evidence_sources": [
            snapshot.source(rule["resolution_text_path"]),
            snapshot.source(approved_path),
            snapshot.source(covered_path),
        ],
        "note": rule["note"],
    }


def _site02(snapshot: Snapshot, policy: dict[str, Any]) -> dict[str, Any]:
    rule = policy["site_02"]
    fixture = jurisdiction_config()
    university = _path_value(snapshot, rule["university_path"])
    region = _path_value(snapshot, rule["proposed_region_path"])
    has_values = (
        isinstance(university, str)
        and bool(university.strip())
        and isinstance(region, str)
        and bool(region.strip())
    )
    found = False
    if has_values:
        university_key = _normalise_text(university)
        region_key = _normalise_text(region)
        found = any(
            _normalise_text(entry["university"]) == university_key
            and any(_normalise_text(item) == region_key for item in entry["regions"])
            for entry in fixture["entries"]
        )

    diagnostic = (
        "synthetic_fixture_match"
        if found
        else "no_synthetic_fixture_match"
        if has_values
        else "insufficient_evidence"
    )
    return {
        "rule_id": rule["rule_id"],
        "title": rule["title"],
        "rule_status": rule["status"],
        "diagnostic": diagnostic,
        "outcome": policy["outcome"],
        "advisory_only": policy["advisory_only"],
        "human_review": policy["human_review"],
        "jurisdiction_conclusion": "none",
        "fixture_status": fixture["status"],
        "evidence_paths": [rule["university_path"], rule["proposed_region_path"]],
        "evidence_sources": [
            snapshot.source(rule["university_path"]),
            snapshot.source(rule["proposed_region_path"]),
        ],
        "note": rule["note"],
    }


def evaluate(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Return review-only diagnostics; never infer an official jurisdiction."""
    policy = config()
    return [_site01(snapshot, policy), _site02(snapshot, policy)]
