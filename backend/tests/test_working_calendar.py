"""Working calendar, holidays and application windows (Phase 2.1).

PRD FR-37: "Load yearly Public Notice dates and Academic Calendar; apply
to all clocks" (APH cl. 2.2, 2.25). The calendar is configuration
(``rules/calendars.json``), loaded through the same ``policy.py`` loader
as the other rule files.

Safety rules honoured here:

- **No invented dates.** Neither the PRD nor ``rules.json``/``rules2.json``
  record an actual Public Notice or Academic Calendar date — ``rules.json``
  marks them ``unverified``/``null`` ("fill only after ... verified") and
  ``rules2.json`` says a cut-off may be enforced "only when the applicable
  notice and time basis are verified". So the shipped config loads **no
  year**, and every lookup for an unconfigured year answers ``None``/``()``
  — never a guessed date (Master Prompt §2 rules 2 and 4).
- **Working-day maths is configurable, not hard-coded**: the weekend
  convention and the holiday list come from config (PRD: "Working-day
  calendar from config"), so changing them is a config edit.
- These functions are pure date maths over configuration. They make no
  decision and gate nothing — the cut-off *decision* is task 2.2.
- The ``SAMPLE`` year below is a **synthetic fixture used only to exercise
  the "a year IS loaded" paths**. It is not a real notice; the shipped
  config contains no year (see the last test).
"""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta

from app.core.config import get_settings
from app.services import working_calendar as cal

# Synthetic fixture dates — chosen far in the future (2099) so they can
# never be mistaken for, or collide with, a real application year.
SAMPLE = {
    "timezone": "Asia/Kolkata",
    "weekend_days": [5, 6],  # Saturday, Sunday (Python weekday())
    "years": {
        "2099": {
            "academic_year": "2099-2100",
            "public_notice": {
                "opens_on": "2099-04-01",
                "closes_on": "2099-04-30",  # the cut-off
                "status": "unverified",
                "source_refs": [],
            },
            "academic_calendar": {
                "starts_on": "2099-07-01",
                "ends_on": "2100-06-30",
                "last_grant_date": "2099-08-31",
                "status": "unverified",
                "source_refs": [],
            },
            "holidays": ["2099-01-26"],
        }
    },
}


def _first_weekday(year: int) -> date:
    """A known weekday in `year` — derived, never assumed."""
    day = date(year, 1, 1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _first_weekend_day(year: int) -> date:
    """A known Saturday/Sunday in `year` — derived, never assumed."""
    day = date(year, 1, 1)
    while day.weekday() < 5:
        day += timedelta(days=1)
    return day


# ---------------------------------------------------------------- the config


def test_the_calendar_config_loads_and_is_unverified_and_advisory():
    cfg = cal.calendars()
    assert cfg["status"] == "unverified"
    assert cfg["advisory_only"] is True


def test_the_config_points_at_the_fr_and_clauses_it_came_from():
    source = cal.calendars()["source"]
    assert "FR-37" in source
    assert "2.2" in source or "2.25" in source


def test_it_ships_a_template_so_a_reviewer_knows_the_shape_to_fill():
    template = cal.calendars()["template"]
    assert template["public_notice"]["status"] == "unverified"
    assert template["academic_calendar"]["status"] == "unverified"
    assert template["holidays"] == []
    # Nothing filled in: the template is a shape, not a value.
    assert template["public_notice"]["closes_on"] is None
    assert template["academic_calendar"]["last_grant_date"] is None


def test_no_year_is_loaded_because_no_official_date_is_recorded():
    """The honest state: the PRD records no PN/AC date, so we load none."""
    assert cal.calendars()["years"] == {}


# ------------------------------------------------------- timezone and clocks


def test_the_business_timezone_is_ist():
    assert str(cal.timezone()) == "Asia/Kolkata"


def test_the_calendar_timezone_and_the_settings_timezone_cannot_diverge():
    """Two sources of truth for the timezone must agree or fail loudly."""
    assert str(cal.timezone()) == get_settings().business_timezone


def test_an_instant_is_read_as_a_business_date_in_ist():
    # 19:30 UTC is already 01:30 the *next* day in IST (+05:30).
    moment = datetime(2099, 1, 1, 19, 30, tzinfo=UTC)
    assert cal.business_date(moment) == date(2099, 1, 2)


def test_an_early_morning_instant_stays_on_the_same_business_date():
    moment = datetime(2099, 1, 1, 0, 0, tzinfo=UTC)  # 05:30 IST
    assert cal.business_date(moment) == date(2099, 1, 1)


def test_a_naive_datetime_is_read_as_utc_not_as_ist():
    # SQLite hands back naive datetimes; they must not be read as IST.
    assert cal.business_date(datetime(2099, 1, 1, 12, 0)) == date(2099, 1, 1)


# ------------------------------------------------ lookups: never a guessed date


def test_an_unconfigured_year_answers_none_not_a_guessed_date():
    assert cal.public_notice_cutoff(2098) is None
    assert cal.public_notice(2098) is None
    assert cal.academic_calendar(2098) is None
    assert cal.holidays_for(2098) == ()


def test_the_real_config_has_no_loaded_year_so_every_lookup_is_none():
    assert cal.public_notice_cutoff(2026) is None
    assert cal.academic_calendar(2026) is None


def test_a_loaded_year_returns_its_exact_configured_cutoff():
    got = cal.public_notice_cutoff(2099, cfg=SAMPLE)
    assert got == date(2099, 4, 30)


def test_a_loaded_year_returns_its_academic_calendar():
    got = cal.academic_calendar(2099, cfg=SAMPLE)
    assert got is not None
    assert got["last_grant_date"] == "2099-08-31"
    assert got["starts_on"] == "2099-07-01"


def test_holidays_are_returned_as_dates_for_a_loaded_year():
    assert cal.holidays_for(2099, cfg=SAMPLE) == (date(2099, 1, 26),)


def test_a_year_entry_missing_its_public_notice_does_not_crash():
    bare = {"timezone": "Asia/Kolkata", "weekend_days": [5, 6],
            "years": {"2099": {"holidays": []}}}
    assert cal.public_notice_cutoff(2099, cfg=bare) is None
    assert cal.academic_calendar(2099, cfg=bare) is None


# ----------------------------------------------------- working-day arithmetic


def test_a_weekday_is_a_working_day():
    assert cal.is_working_day(_first_weekday(2099), cfg=SAMPLE) is True


def test_a_weekend_day_is_not_a_working_day():
    assert cal.is_working_day(_first_weekend_day(2099), cfg=SAMPLE) is False


def test_a_configured_holiday_is_not_a_working_day():
    # Force a holiday onto a *weekday* so the answer can only come from the
    # holiday list, not from the weekend rule.
    cfg = copy.deepcopy(SAMPLE)
    weekday = _first_weekday(2099)
    cfg["years"]["2099"]["holidays"] = [weekday.isoformat()]
    assert cal.is_working_day(weekday, cfg=cfg) is False


def test_the_weekend_convention_comes_from_config_not_from_code():
    """Move the weekend to Mon+Tue and Saturday must become a working day."""
    cfg = copy.deepcopy(SAMPLE)
    cfg["weekend_days"] = [0, 1]  # Monday, Tuesday
    saturday = _first_weekend_day(2099)  # derived, not assumed
    assert cal.is_working_day(saturday, cfg=cfg) is True
    monday = date(2099, 1, 4)
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    assert cal.is_working_day(monday, cfg=cfg) is False
    # ...and with the shipped Mon-Fri convention the same Saturday is off.
    assert cal.is_working_day(saturday, cfg=SAMPLE) is False


def test_add_working_days_skips_weekends():
    friday = _first_weekday(2099)
    while friday.weekday() != 4:
        friday += timedelta(days=1)
    # +1 working day from a Friday lands on Monday, not Saturday.
    assert cal.add_working_days(friday, 1, cfg=SAMPLE) == friday + timedelta(
        days=3
    )


def test_add_working_days_skips_configured_holidays():
    cfg = copy.deepcopy(SAMPLE)
    monday = date(2099, 1, 4)
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    # A clean walk of +2 working days from a Monday would be the Wednesday.
    assert cal.add_working_days(monday, 2, cfg=copy.deepcopy(cfg)) == monday + timedelta(
        days=2
    )
    # Now make the Tuesday a holiday: the walk must skip it and land Thursday.
    cfg["years"]["2099"]["holidays"] = [
        (monday + timedelta(days=1)).isoformat()
    ]
    got = cal.add_working_days(monday, 2, cfg=cfg)
    assert got == monday + timedelta(days=3)
    assert cal.is_working_day(got, cfg=cfg) is True


def test_add_zero_working_days_returns_the_start_date():
    day = _first_weekday(2099)
    assert cal.add_working_days(day, 0, cfg=SAMPLE) == day


def test_adding_working_days_backwards_walks_the_other_way():
    day = _first_weekday(2099)
    back = cal.add_working_days(day, -1, cfg=SAMPLE)
    assert back < day
    assert cal.is_working_day(back, cfg=SAMPLE) is True


def test_a_calendar_with_no_working_day_fails_loudly_instead_of_hanging():
    cfg = copy.deepcopy(SAMPLE)
    cfg["weekend_days"] = list(range(7))  # every day is a weekend
    try:
        cal.add_working_days(date(2099, 1, 1), 1, cfg=cfg)
    except ValueError as exc:
        assert "working day" in str(exc)
    else:  # pragma: no cover - guards against an infinite loop regression
        raise AssertionError("expected ValueError when no working day exists")
