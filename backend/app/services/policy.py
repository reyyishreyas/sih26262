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
    route = workflow_routes()["routes"].get(route_key)
    if not route:
        return None
    value = route.get("stage_sla_days", {}).get(state)
    return int(value) if value is not None else None
