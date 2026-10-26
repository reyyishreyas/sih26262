"""Working calendar: IST, working days, holidays, and application windows.

Answers come from configuration only — ``rules/calendars.json`` (PRD FR-37:
"Load yearly Public Notice dates and Academic Calendar; apply to all
clocks", APH cl. 2.2 / 2.25), loaded through ``policy.calendars()`` like the
other rule files.

Two rules shape everything here:

1. **No invented date.** The PRD and ``rules.json``/``rules2.json`` record
   no actual Public Notice or Academic Calendar date (they are Unverified
   placeholders). So ``calendars.json`` ships with an empty ``years`` map,
   and every lookup for a year that is not recorded answers ``None``/``()``
   — never a guessed window (Master Prompt §2 rules 2 and 4). A clock can
   therefore only be computed once a human records the year.
2. **Configurable working-day maths.** The timezone, weekend convention and
   holiday list are read from config (PRD: "Working-day calendar from
   config"), never hard-coded, so changing the convention is an edit to
   ``calendars.json`` and not to code.

These functions are pure date maths over configuration. They make no
decision, gate nothing, and write nothing — the cut-off *decision* ("tag
the next Academic Year, never reject") is task 2.2.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..core.clock import to_utc
from ..services.policy import calendars as _calendars

# Bound the working-day walk so a calendar with no working day at all
# raises instead of hanging (see add_working_days).
_MAX_WORKDAY_STEPS = 3660  # ~10 years of calendar days


def calendars() -> dict[str, Any]:
    """The raw calendar configuration (``rules/calendars.json``)."""
    return _calendars()


def timezone() -> ZoneInfo:
    """The business timezone (IST) every clock reads in."""
    return ZoneInfo(str(calendars()["timezone"]))


def business_date(moment: datetime) -> date:
    """The business-timezone calendar date for an instant.

    Naive datetimes (SQLite returns them) are treated as UTC, matching
    ``core.clock.to_utc``, so a naive value is never misread as IST.
    """
    aware = to_utc(moment)
    assert aware is not None  # to_utc only returns None for a None input
    return aware.astimezone(timezone()).date()


# ------------------------------------------------------------------ lookups


def _year_entry(year: int, cfg: dict[str, Any] | None) -> dict[str, Any] | None:
    config = cfg if cfg is not None else calendars()
    entry = config.get("years", {}).get(str(year))
    return entry if isinstance(entry, dict) else None


def public_notice(year: int, cfg: dict[str, Any] | None = None) -> dict | None:
    """The recorded Public Notice block for `year`, or None if not recorded.

    None means "no official date has been recorded for this year" — a
    reviewer must record it, never a caller guessing.
    """
    entry = _year_entry(year, cfg)
    if entry is None:
        return None
    block = entry.get("public_notice")
    return block if isinstance(block, dict) else None


def public_notice_cutoff(year: int, cfg: dict[str, Any] | None = None) -> date | None:
    """The recorded Public Notice cut-off for `year`, or None if not recorded.

    This is the date after which an application is queued for the next
    Academic Year (FR-02). Returning None must be read as "window not
    recorded / needs review", never as "no cut-off applies".
    """
    block = public_notice(year, cfg)
    if not block or not block.get("closes_on"):
        return None
    return date.fromisoformat(str(block["closes_on"]))


def academic_calendar(year: int, cfg: dict[str, Any] | None = None) -> dict | None:
    """The recorded Academic Calendar block for `year`, or None if not recorded.

    Holds ``starts_on``/``ends_on``/``last_grant_date`` (FR-32: no EoA
    letter after the Academic Calendar's last date).
    """
    entry = _year_entry(year, cfg)
    if entry is None:
        return None
    block = entry.get("academic_calendar")
    return block if isinstance(block, dict) else None


def holidays_for(year: int, cfg: dict[str, Any] | None = None) -> tuple[date, ...]:
    """Recorded holidays in `year` as dates; empty tuple if none/not recorded.

    A malformed ISO date in config raises (fails loudly) rather than being
    silently dropped, so a typo in a holiday is visible in the tests.
    """
    entry = _year_entry(year, cfg)
    if entry is None:
        return ()
    return tuple(
        date.fromisoformat(str(item)) for item in entry.get("holidays", [])
    )


# -------------------------------------------------- working-day arithmetic


def _weekend_days(cfg: dict[str, Any]) -> frozenset[int]:
    return frozenset(int(d) for d in cfg.get("weekend_days", []))


def is_working_day(day: date, cfg: dict[str, Any] | None = None) -> bool:
    """True when `day` is neither a configured weekend day nor a holiday."""
    config = cfg if cfg is not None else calendars()
    if day.weekday() in _weekend_days(config):
        return False
    return day not in holidays_for(day.year, config)


def add_working_days(start: date, days: int, cfg: dict[str, Any] | None = None) -> date:
    """`start` advanced by `days` working days (negative walks backwards).

    Non-working days (weekend + holidays from config) are skipped and not
    counted. `start` itself is not counted — the walk moves first, so from a
    Friday, +1 working day is the following Monday.

    Raises ValueError instead of looping forever when the configuration
    contains no working day at all (e.g. every day marked a weekend).
    """
    if days == 0:
        return start
    step = 1 if days > 0 else -1
    remaining = abs(days)
    cursor = start
    for _ in range(_MAX_WORKDAY_STEPS):
        cursor += timedelta(days=step)
        if is_working_day(cursor, cfg):
            remaining -= 1
            if remaining == 0:
                return cursor
    raise ValueError(
        f"no working day found within {_MAX_WORKDAY_STEPS} days of {start}; "
        "check calendars.json weekend_days/holidays"
    )
