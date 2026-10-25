"""Persisted sign-in throttling.

The limit is evaluated against two keys: the account/client-address pair (stops
credential guessing against one account) and the client address alone (stops
spraying many accounts from one host). State lives in the operational database so
it survives restarts and is shared by every API replica.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..models import LoginAttempt


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0
    reason: str = ""


def wall_now() -> datetime:
    """Real time, always.

    Sign-in throttling runs on the wall clock, never on the injected demo
    clock. The failure window and the lockout are operational security
    windows, not part of the case narrative: with the rehearsal clock frozen,
    every attempt would carry the same instant, so the window could never age
    out, the retention purge could never run, and ``unlock_at - now`` would
    stay pinned at the full lockout — five wrong passwords would lock an
    account *permanently* while still promising "try again in 15 minutes".
    """
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def throttle_keys(email: str, client_ip: str) -> tuple[str, str]:
    normalised = email.strip().lower()
    return (
        _hash(f"account:{normalised}|{client_ip}"),
        _hash(f"ip:{client_ip}"),
    )


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone-aware columns."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _oldest_failure(
    db: Session, key_hash: str, since: datetime
) -> datetime | None:
    value = db.scalar(
        select(LoginAttempt.attempted_at)
        .where(
            LoginAttempt.key_hash == key_hash,
            LoginAttempt.successful.is_(False),
            LoginAttempt.attempted_at >= since,
        )
        .order_by(LoginAttempt.attempted_at)
        .limit(1)
    )
    return _aware(value) if value is not None else None


def _failure_count(db: Session, key_hash: str, since: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.key_hash == key_hash,
                LoginAttempt.successful.is_(False),
                LoginAttempt.attempted_at >= since,
            )
        )
        or 0
    )


def evaluate(
    db: Session,
    *,
    email: str,
    client_ip: str,
    now: datetime,
    settings: Settings,
) -> ThrottleDecision:
    account_key, ip_key = throttle_keys(email, client_ip)
    since = now - timedelta(seconds=settings.login_window_seconds)

    account_failures = _failure_count(db, account_key, since)
    ip_failures = _failure_count(db, ip_key, since)
    account_blocked = account_failures >= settings.login_max_attempts
    ip_blocked = ip_failures >= settings.login_max_attempts_per_ip
    if not account_blocked and not ip_blocked:
        return ThrottleDecision(allowed=True)

    blocked_key = account_key if account_blocked else ip_key
    oldest = _oldest_failure(db, blocked_key, since)
    retry_after = settings.login_lockout_seconds
    if oldest is not None:
        unlock_at = oldest + timedelta(seconds=settings.login_lockout_seconds)
        retry_after = max(1, int((unlock_at - now).total_seconds()) + 1)
    reason = "too_many_account_attempts" if account_blocked else "too_many_ip_attempts"
    return ThrottleDecision(
        allowed=False, retry_after_seconds=retry_after, reason=reason
    )


def record(
    db: Session,
    *,
    email: str,
    client_ip: str,
    now: datetime,
    successful: bool,
    settings: Settings,
) -> None:
    keys = throttle_keys(email, client_ip)
    if successful:
        # A correct sign-in clears the failure window for this account/address only.
        # The address-only counter is deliberately left alone: one valid account must
        # not reset the spraying limit for every other account behind the same address.
        db.execute(
            delete(LoginAttempt).where(
                LoginAttempt.key_hash == keys[0],
                LoginAttempt.successful.is_(False),
            )
        )
    for key_hash in keys:
        db.add(
            LoginAttempt(
                key_hash=key_hash,
                attempted_at=now,
                successful=successful,
            )
        )
    # Keep the table bounded. Twice the longest relevant interval is enough for
    # both the counting window and the lockout calculation.
    retention = max(settings.login_window_seconds, settings.login_lockout_seconds) * 2
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.attempted_at < now - timedelta(seconds=retention)
        )
    )
