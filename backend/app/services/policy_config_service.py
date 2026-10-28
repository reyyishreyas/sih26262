"""Draft validation, immutable snapshots and four-eyes publication."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PolicyConfigVersion
from . import policy

POLICY_FILES = {
    "routes": policy.workflow_routes,
    "deadlines": policy.deadline_policy,
    "fees": policy.fee_table_policy,
    "escalation": policy.escalation_chain_policy,
    "templates": None,
}


def baseline(policy_key: str) -> dict[str, Any]:
    if policy_key not in POLICY_FILES:
        raise ValueError("unsupported policy category")
    loader = POLICY_FILES[policy_key]
    if loader is None:
        return {"version": 1, "templates": [], "note": "No active message templates are configured."}
    return loader()


def active(db: Session, policy_key: str) -> dict[str, Any]:
    latest = db.scalars(
        select(PolicyConfigVersion)
        .where(
            PolicyConfigVersion.policy_key == policy_key,
            PolicyConfigVersion.status == "approved",
        )
        .order_by(PolicyConfigVersion.version.desc())
    ).first()
    return latest.content if latest is not None else baseline(policy_key)


def validate(policy_key: str, content: dict[str, Any]) -> dict[str, Any]:
    if policy_key not in POLICY_FILES:
        raise ValueError("unsupported policy category")
    if not isinstance(content, dict) or len(json.dumps(content)) > 50_000:
        raise ValueError("policy content must be a JSON object under 50 KB")
    if policy_key == "deadlines":
        current = baseline("deadlines")
        if set(content) != set(current):
            raise ValueError("deadline draft must preserve the configured policy sections")
        for kind, entries in content.items():
            if kind == "note":
                if not isinstance(entries, str):
                    raise ValueError("deadline policy note must be text")
                continue
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"deadline section {kind} must contain thresholds")
            levels: set[str] = set()
            for entry in entries:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("level"), str)
                    or not isinstance(entry.get("offset_days"), int)
                    or abs(entry["offset_days"]) > 3650
                    or entry.get("severity") not in {"info", "warning", "critical", "escalated"}
                ):
                    raise ValueError(f"invalid threshold in deadline section {kind}")
                if entry["level"] in levels:
                    raise ValueError(f"duplicate threshold level in deadline section {kind}")
                levels.add(entry["level"])
    elif policy_key == "routes":
        if not isinstance(content.get("routes"), dict) or not content["routes"]:
            raise ValueError("route draft must contain a routes object")
    elif policy_key == "fees":
        if not isinstance(content.get("fees"), dict) or content.get("status") not in {"unverified", "verified"}:
            raise ValueError("fee draft must contain fee entries and a known verification status")
        if content.get("status") == "verified":
            verification = content.get("verification", {})
            if not all(verification.get(key) for key in ("source_id", "reviewer", "edition", "clause", "verified_at")):
                raise ValueError("verified fee policy requires source, named reviewer, edition, clause and date")
    elif policy_key == "escalation":
        if not isinstance(content.get("chain"), list) or not content["chain"]:
            raise ValueError("escalation draft must contain a non-empty chain")
    elif policy_key == "templates":
        templates = content.get("templates")
        if not isinstance(templates, list) or len(templates) > 100:
            raise ValueError("template draft must contain a list of at most 100 templates")
        for entry in templates:
            if not isinstance(entry, dict) or not all(
                isinstance(entry.get(key), str) and entry[key].strip()
                for key in ("key", "title", "body")
            ):
                raise ValueError("each template requires key, title and body text")
    return json.loads(json.dumps(content))


def content_hash(content: dict[str, Any]) -> str:
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
