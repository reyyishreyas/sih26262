"""Injectable clock.

Deadlines are always computed as `f(now, entered_at, policy)`. Nothing stores a
"due" flag, so re-running a sweep, back-dating a demo, or fast-forwarding the
rehearsal clock cannot leave the database inconsistent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from .config import get_settings


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A frozen instant — used by tests and by the rehearsal/demo timeline."""

    def __init__(self, fixed_at: datetime) -> None:
        if fixed_at.tzinfo is None:
            fixed_at = fixed_at.replace(tzinfo=UTC)
        self._fixed_at = fixed_at

    def now(self) -> datetime:
        return self._fixed_at

    def advance(self, **kwargs: float) -> None:
        self._fixed_at = self._fixed_at + timedelta(**kwargs)


class OffsetClock:
    def __init__(self, offset: timedelta) -> None:
        self._offset = offset

    def now(self) -> datetime:
        return datetime.now(UTC) + self._offset


_clock: Clock | None = None


def get_clock() -> Clock:
    global _clock
    if _clock is None:
        _clock = build_clock()
    return _clock


def set_clock(clock: Clock | None) -> None:
    global _clock
    _clock = clock


def build_clock() -> Clock:
    s = get_settings()
    mode = s.clock_mode.lower()
    if mode == "fixed":
        if not s.clock_fixed_at:
            raise RuntimeError("clock_mode=fixed requires clock_fixed_at")
        return FixedClock(datetime.fromisoformat(s.clock_fixed_at))
    if mode == "offset":
        return OffsetClock(timedelta(days=s.clock_offset_days))
    return SystemClock()


def to_utc(value: datetime | None) -> datetime | None:
    """Normalise DB datetimes (SQLite returns naive) to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: datetime | None) -> str | None:
    normalised = to_utc(value)
    return normalised.isoformat().replace("+00:00", "Z") if normalised else None
