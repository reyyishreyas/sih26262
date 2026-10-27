"""Phase 3 exit check: demo clock → alerts at lead times → L0→L1→L2 → 0 drift.

The plan's Phase 3 exit check reads: *"advance demo clock → alerts fire at
configured lead times → escalate L0→L1→L2; reconciliation shows 0 diff."*
Every individual piece has its own suite (test_alerts, test_escalation,
test_reconcile, test_demo_clock); this file proves the pieces compose into
the demo narrative end to end, on one seeded case, with no hand-rolled time
plumbing — time moves through the real ``demo_clock`` service (Phase 3.8),
alerts come from the real sweep, and drift is judged by the real reconcile.

The ladder walked here is entirely configuration:

- stage limit: ``stage_limits.json`` → existing_technical / scrutiny = 10 days
- alert lead times: ``deadline_policy.json`` → stage_ageing = due_soon at
  limit−2 days, overdue at the limit, escalated at limit+5 days
- escalation levels: ``escalation_chain.json`` → 70/90% L0, 100% L1,
  125% L2 (payload ``escalation_level``, Phase 3.4)

The case under test is the seeded ``app-existing-0003`` (scrutiny, 10-day
limit); its ``current_state_since`` is pinned to the demo clock's baseline so
the percentages land exactly on the configured thresholds.
"""

from __future__ import annotations

import pytest
from fastapi import status

from app.core.clock import FixedClock, set_clock
from app.models import Alert, Application, User
from app.services import deadline_service, demo_clock, reconcile
from tests.conftest import DEMO_NOW

EXISTING = "app-existing-0003"


def _user_id(db, email: str) -> str:
    return db.query(User).filter_by(email=email).one().id


def _pin_stage_entry(db) -> None:
    """Start the case's scrutiny stint exactly at the demo-clock baseline."""
    application = db.get(Application, EXISTING)
    application.current_state_since = DEMO_NOW
    db.commit()


def _alerts_for_the_case(db) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(
            Alert.entity_type == "application",
            Alert.entity_id == EXISTING,
            Alert.alert_type == "stage_ageing",
        )
        .order_by(Alert.fired_at, Alert.level)
        .all()
    )


def _levels_present(db) -> set[str]:
    return {alert.level for alert in _alerts_for_the_case(db)}


def _jump(db, access_for, days: float) -> None:
    """Advance the demo clock through the real admin service (audited)."""
    demo_clock.advance(db, access_for("admin@demo.local"), days)


@pytest.fixture(autouse=True)
def _isolated_clock():
    """The demo clock is process-wide; never leak a jump into another test."""
    set_clock(FixedClock(DEMO_NOW))
    yield
    set_clock(FixedClock(DEMO_NOW))


# ------------------------------------------------------------- the ladder


def test_nothing_fires_before_the_configured_lead_time(db, access_for):
    """Day 0 of a 10-day stage: the first lead time is day 8 — silence first."""
    _pin_stage_entry(db)

    deadline_service.sweep(db)

    assert _levels_present(db) == set()


def test_due_soon_fires_at_the_lead_time_and_reports_L0(db, access_for):
    """80% of the 10-day limit = day 8, the configured due_soon lead time."""
    _pin_stage_entry(db)

    _jump(db, access_for, 8)
    deadline_service.sweep(db)

    alerts = _alerts_for_the_case(db)
    assert [alert.level for alert in alerts] == ["due_soon"]
    assert alerts[0].payload["escalation_level"] == "L0"
    assert alerts[0].payload["sla_days"] == 10
    assert alerts[0].payload["days_in_state"] == 8


def test_the_limit_itself_fires_overdue_and_escalates_to_L1(db, access_for):
    """100% of the limit: the overdue alert, whose level is L1 — the regional
    officer joins the recipients (alert severity critical, Phase 3.4)."""
    _pin_stage_entry(db)

    _jump(db, access_for, 10)
    deadline_service.sweep(db)

    overdue = [a for a in _alerts_for_the_case(db) if a.level == "overdue"]
    assert len(overdue) == 1
    assert overdue[0].payload["escalation_level"] == "L1"
    # Who is told grows with severity: institution + assignee always, plus the
    # region's regional officer at critical.
    assert _user_id(db, "regional@demo.local") in overdue[0].recipients


def test_overshooting_the_limit_escalates_to_L2(db, access_for):
    """150% of the limit (day 15): the escalated alert reaches L2 — the
    supervisory officer (placeholder Regulation Bureau) is among recipients."""
    _pin_stage_entry(db)

    _jump(db, access_for, 15)
    deadline_service.sweep(db)

    escalated = [a for a in _alerts_for_the_case(db) if a.level == "escalated"]
    assert len(escalated) == 1
    assert escalated[0].payload["escalation_level"] == "L2"
    assert _user_id(db, "supervisor@demo.local") in escalated[0].recipients


def test_the_whole_walkthrough_is_one_idempotent_sequence(db, access_for):
    """The demo narrative in one test: silence → L0 → L1 → L2, never a
    duplicate, reconciliation clean at every stop."""
    _pin_stage_entry(db)

    assert reconcile.reconcile(db).zero_differences

    deadline_service.sweep(db)
    assert _levels_present(db) == set()

    _jump(db, access_for, 8)
    deadline_service.sweep(db)
    assert _levels_present(db) == {"due_soon"}
    assert reconcile.reconcile(db).zero_differences

    _jump(db, access_for, 2)
    deadline_service.sweep(db)
    assert _levels_present(db) == {"due_soon", "overdue"}
    assert reconcile.reconcile(db).zero_differences

    _jump(db, access_for, 5)
    deadline_service.sweep(db)
    assert _levels_present(db) == {"due_soon", "overdue", "escalated"}
    assert reconcile.reconcile(db).zero_differences

    # Re-running the sweep on the same clock creates nothing new — the
    # dedupe_key encodes the stage's cycle, so the nag never repeats.
    again = deadline_service.sweep(db)
    assert again.created == 0
    assert len(_alerts_for_the_case(db)) == 3


def test_the_escalation_endpoint_agrees_with_the_alerts_after_the_jumps(
    db, client, as_user, access_for
):
    """The advisory snapshot (GET .../escalation) reads the same clock the
    sweep used, so after the walk it answers L2 — one time source."""
    _pin_stage_entry(db)
    _jump(db, access_for, 15)

    response = client.get(
        f"/api/v1/applications/{EXISTING}/escalation",
        headers=as_user("scrutiny@demo.local"),
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["days_in_stage"] == 15
    assert payload["percent_used"] == 150
    assert payload["level"] == "L2"


def test_the_admin_sweep_endpoint_drives_the_same_ladder(db, client, as_user, access_for):
    """The API path the demo actually uses: POST /internal/deadline-sweep
    after a demo-clock jump produces the same L1 alert, idempotently."""
    _pin_stage_entry(db)
    _jump(db, access_for, 10)

    headers = as_user("admin@demo.local")
    first = client.post("/api/v1/internal/deadline-sweep", headers=headers)
    assert first.status_code == status.HTTP_200_OK

    levels = _levels_present(db)
    assert "overdue" in levels

    second = client.post("/api/v1/internal/deadline-sweep", headers=headers)
    assert second.status_code == status.HTTP_200_OK
    assert second.json()["created"] == 0

    report = client.get("/api/v1/internal/reconcile-clocks", headers=headers)
    assert report.status_code == status.HTTP_200_OK
    assert report.json()["zero_differences"] is True
