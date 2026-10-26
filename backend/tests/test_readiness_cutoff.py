"""Readiness cut-off check: tag next AY, never reject (Phase 2.2).

PRD FR-02 / §6 routing rule 7: an application submitted after the Public
Notice cut-off is queued for the next Academic Year. The plan (2.2)
implements **only the tag** — "never reject" — because PRD §0 forbids an
Unverified rule from blocking or rejecting (see IMPL-0017).

Two safety properties are the point of this file:

- **Nothing is guessed.** No cut-off date is recorded (calendars.json
  ships empty), or no submission time exists, and the answer is
  ``needs_review`` — never a confident in-window pass (Master Prompt §2
  rule 4).
- **It never rejects.** The status vocabulary contains no rejected/blocked
  value, and after the cut-off the function only *names* the configured
  tag; it changes no state (rule 3).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.services import readiness

# Synthetic config so a *loaded* year can be exercised without putting an
# invented date in the shipped calendars.json (which must stay empty).
CAL_CFG = {
    "timezone": "Asia/Kolkata",
    "weekend_days": [5, 6],
    "years": {
        "2099": {
            "public_notice": {"opens_on": "2099-04-01", "closes_on": "2099-04-30"},
            "academic_calendar": {},
            "holidays": [],
        }
    },
}

POLICY = {
    "action_on_after_cutoff": "queue_for_next_academic_year",
    "reject": False,
    "source": "test fixture",
}


def check(submitted_at, **kwargs):
    kwargs.setdefault("policy_cfg", POLICY)
    return readiness.cut_off_check(submitted_at, **kwargs)


# ------------------------------------------------------------- the config


def test_the_cut_off_policy_is_loaded_and_is_unverified_and_advisory():
    policy = readiness.cut_off_policy()
    assert policy["status"] == "unverified"
    assert policy["advisory_only"] is True


def test_the_policy_points_at_fr_02_and_its_clauses():
    policy = readiness.cut_off_policy()
    assert "FR-02" in policy["source"]
    assert "2.2" in policy["source"] or "2.22" in policy["source"]


def test_the_policy_says_never_reject():
    """FR-02's reject half is deliberately not implemented (plan 2.2)."""
    assert readiness.cut_off_policy()["reject"] is False
    assert readiness.cut_off_policy()["action_on_after_cutoff"] == (
        "queue_for_next_academic_year"
    )


def test_the_status_vocabulary_contains_no_rejection():
    """Guard: a 'rejected'/'blocked' status can never appear unnoticed."""
    vocabulary = readiness.statuses()
    assert "rejected" not in vocabulary
    assert "blocked" not in vocabulary
    assert set(vocabulary) == {"within_window", "after_cutoff", "needs_review"}


# --------------------------------------------- nothing is guessed (rule 4)


def test_the_real_empty_calendars_mean_every_submission_needs_review():
    """calendars.json ships no year (IMPL-0016), so the honest answer is
    needs_review — not 'in window', not 'after cut-off'."""
    got = readiness.cut_off_check(
        datetime(2026, 5, 1, tzinfo=UTC), policy_cfg=POLICY
    )
    assert got["status"] == "needs_review"
    assert got["tag"] is None
    assert "no Public Notice cut-off recorded" in got["reason"]


def test_a_missing_submission_time_is_uncertain_not_a_pass():
    got = readiness.cut_off_check(None, policy_cfg=POLICY)
    assert got["status"] == "needs_review"
    assert got["tag"] is None
    assert got["submitted_on"] is None


def test_a_year_with_no_recorded_cutoff_is_never_read_as_no_cutoff():
    got = check(datetime(2098, 5, 1, tzinfo=UTC), calendars_cfg=CAL_CFG)
    assert got["status"] == "needs_review"
    assert got["cut_off"] is None


# ------------------------------------------------- a loaded year behaves


def test_a_submission_inside_the_window_is_within_window():
    got = check(datetime(2099, 4, 15, 6, 0, tzinfo=UTC), calendars_cfg=CAL_CFG)
    assert got["status"] == "within_window"
    assert got["tag"] is None
    assert got["cut_off"] == date(2099, 4, 30)


def test_on_the_cutoff_date_itself_is_still_within_window():
    # Cutoff is 2099-04-30 (IST); 04:00 IST on the 30th is before end of day.
    got = check(
        datetime(2099, 4, 29, 22, 30, tzinfo=UTC),  # 2099-04-30 04:00 IST
        calendars_cfg=CAL_CFG,
    )
    assert got["status"] == "within_window"


def test_a_submission_after_the_cutoff_names_the_queue_tag():
    got = check(datetime(2099, 5, 1, 6, 0, tzinfo=UTC), calendars_cfg=CAL_CFG)
    assert got["status"] == "after_cutoff"
    assert got["tag"] == "queue_for_next_academic_year"
    assert got["submitted_on"] == date(2099, 5, 1)


def test_after_the_cutoff_still_never_says_rejected():
    got = check(datetime(2099, 5, 2, tzinfo=UTC), calendars_cfg=CAL_CFG)
    assert "reject" not in got["status"]
    assert got["status"] not in ("rejected", "blocked")


def test_the_check_is_pure_it_changes_nothing_and_has_no_side_effects():
    """Calling twice yields the same dict — no state, no writes."""
    when = datetime(2099, 5, 1, 6, 0, tzinfo=UTC)
    first = check(when, calendars_cfg=CAL_CFG)
    second = check(when, calendars_cfg=CAL_CFG)
    assert first == second


# ------------------------------------------------------------ timezone


def test_a_naive_datetime_is_read_as_utc_not_as_ist():
    # 2099-05-01 22:00 naive == 22:00 UTC == 2099-05-02 03:30 IST -> after.
    got = check(datetime(2099, 5, 1, 22, 0), calendars_cfg=CAL_CFG)
    assert got["status"] == "after_cutoff"
    assert got["submitted_on"] == date(2099, 5, 2)


def test_the_business_date_is_in_ist_so_the_boundary_is_right():
    # 19:00 UTC on 2099-04-30 is 2099-05-01 00:30 IST -> the *next* day,
    # i.e. after a 04-30 cut-off. Proves the check uses IST, not UTC.
    got = check(datetime(2099, 4, 30, 19, 0, tzinfo=UTC), calendars_cfg=CAL_CFG)
    assert got["status"] == "after_cutoff"
    assert got["submitted_on"] == date(2099, 5, 1)
