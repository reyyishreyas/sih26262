"""Policy-as-data loaders.

Timelines, escalation ladders and the verified rule set live in ``backend/rules``.
Changing a deadline is a configuration change, not a deploy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def _load(name: str) -> dict[str, Any]:
    path = RULES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"policy file missing: {path}")
    with path.open() as handle:
        return json.load(handle)


@lru_cache
def compliance_rules() -> dict[str, Any]:
    return _load("compliance_rules.json")


@lru_cache
def workflow_routes() -> dict[str, Any]:
    return _load("workflow_routes.json")


@lru_cache
def deadline_policy() -> dict[str, Any]:
    return _load("deadline_policy.json")


@lru_cache
def calendars() -> dict[str, Any]:
    return _load("calendars.json")


@lru_cache
def readiness_policy() -> dict[str, Any]:
    return _load("readiness_policy.json")


@lru_cache
def portal_feed_policy() -> dict[str, Any]:
    return _load("portal_feed.json")


@lru_cache
def stage_graph_policy() -> dict[str, Any]:
    return _load("stage_graph.json")


@lru_cache
def reason_codes_policy() -> dict[str, Any]:
    return _load("reason_codes.json")


@lru_cache
def stage_limits_policy() -> dict[str, Any]:
    return _load("stage_limits.json")


@lru_cache
def escalation_chain_policy() -> dict[str, Any]:
    return _load("escalation_chain.json")


@lru_cache
def annexure_2_policy() -> dict[str, Any]:
    return _load("annexure_2.json")


@lru_cache
def appeal_policy() -> dict[str, Any]:
    return _load("appeal_policy.json")


@lru_cache
def security_deposit_policy() -> dict[str, Any]:
    return _load("security_deposit_policy.json")


@lru_cache
def assignment_policy() -> dict[str, Any]:
    return _load("assignment_policy.json")


@lru_cache
def compliance_policy() -> dict[str, Any]:
    return _load("compliance_policy.json")


@lru_cache
def doc_check_policy() -> dict[str, Any]:
    return _load("doc_check_policy.json")


@lru_cache
def doc_classifier_policy() -> dict[str, Any]:
    return _load("doc_classifier.json")


@dataclass(frozen=True)
class Threshold:
    level: str
    offset_days: int
    severity: str


def thresholds(kind: str) -> list[Threshold]:
    return [
        Threshold(entry["level"], int(entry["offset_days"]), entry["severity"])
        for entry in deadline_policy().get(kind, [])
    ]


def stage_sla_days(route_key: str, state: str) -> int | None:
    """Placeholder day count for a case sitting in `state` (config, advisory).

    Lives in `stage_limits.json` since Phase 3.3 (the counts moved out of
    workflow_routes.json unchanged — a pinned test proves it). The count
    belongs to the PRD stage the state maps to (stage_graph.json), with
    per-state overrides where one stage counts differently by state (a
    booked vs a held EVC visit); states no stage owns (sac_review) have
    their own unmapped-state counts. None means no clock is configured —
    never a default guess. All counts are labelled placeholders until
    AICTE answers §19 Q1.
    """
    limits = stage_limits_policy()["routes"].get(route_key)
    if not limits:
        return None

    for stage_key, entry in limits.items():
        graph_stage = next(
            (
                stage
                for stage in stage_graph_policy()["routes"][route_key]
                if stage["stage_key"] == stage_key
            ),
            None,
        )
        if graph_stage is None or state not in graph_stage["active_states"]:
            continue
        overrides = entry.get("state_overrides", {})
        value = overrides.get(state, entry.get("days"))
        return int(value) if value is not None else None

    # A state no stage owns: its count rides outside the stage list.
    unmapped = stage_limits_policy().get("unmapped_state_days", {}).get(route_key, {})
    value = unmapped.get(state)
    return int(value) if value is not None else None
