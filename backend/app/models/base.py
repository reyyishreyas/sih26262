"""Shared model helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from ..core.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


__all__ = ["Base", "new_id", "utcnow", "canonical_json", "sha256_hex"]
