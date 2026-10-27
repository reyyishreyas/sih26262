"""Phase 6.2: EVC visit reminders use the plan's 7/2/1-day cadence.

The lead times are operational placeholders, not confirmed AICTE deadlines.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services import policy
from app.services.deadline_service import eligible_thresholds


def test_evc_reminder_policy_is_labeled_and_uses_seven_two_one_days():
    note = policy.deadline_policy()["note"].lower()
    assert "evc" in note and "placeholder" in note and "unverified" in note
    assert [
        (item.level, item.offset_days)
        for item in policy.thresholds("evc_visit")
    ][:3] == [
        ("visit_reminder_7", -7),
        ("visit_reminder_2", -2),
        ("visit_reminder_1", -1),
    ]
    assert [(item.level, item.offset_days) for item in policy.thresholds("evc_visit")][3:] == [
        ("visit_overdue", 1),
        ("visit_escalated", 10),
    ]


def test_evc_reminders_become_eligible_at_each_configured_lead_time():
    due_at = datetime(2026, 12, 20, 18, 29, 59, tzinfo=UTC)
    thresholds = policy.thresholds("evc_visit")
    for threshold in thresholds:
        threshold_at = due_at + timedelta(days=threshold.offset_days)
        before = threshold_at - timedelta(seconds=1)
        assert threshold not in list(eligible_thresholds("evc_visit", due_at, before))
        assert threshold in list(
            eligible_thresholds("evc_visit", due_at, threshold_at)
        )
