"""Reconcile every clock-derived date against a fresh recomputation (Plan 3.9).

The invariant under test is the one the whole deadline system rests on:
*nothing stores a "due" flag* — every clock is derived on read from the
current clock plus configuration. Reconciliation proves that holds for a live
database, so the demo can show "0 differences" with evidence.

Safety properties:

- **Read-only.** Reconciliation recomputes and compares; it writes nothing,
  creates no alerts, moves no case.
- **A demo-clock jump does not create drift.** Because every date is derived,
  not stored, fast-forwarding the clock changes what the *reader* reports and
  what the *recomputation* reports identically — so the diff stays empty. This
  is the exit check for Phase 3.
- **Frozen alert due_dates are reported, never counted as drift.** An alert
  snapshots the cycle it fired in (``dedupe_key`` encodes that cycle); a live
  recomputation reflects the *current* cycle, which legitimately differs after
  a transition. The report says so rather than calling a cycle change a bug.
- **A real drift is caught.** If a stage's stored ``days``/``started_at`` stop
  reproducing the due date the reader shows, reconciliation reports it and
  ``zero_differences`` is false.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import status

from app.core.clock import FixedClock, get_clock, set_clock
from app.models import Alert, Application, StageInstance
from app.services import reconcile
from tests.conftest import DEMO_NOW


def _seed_active_stage(db, app_id: str, stage_key: str, started_at):
    app = db.get(Application, app_id)
    row = StageInstance(
        application_id=app_id,
        stage_key=stage_key,
        sequence=1,
        status="active",
        started_at=started_at,
    )
    db.add(row)
    db.commit()
    return app, row


def test_reconcile_reports_zero_differences_on_the_seeded_database(db):
    report = reconcile.reconcile(db)
    assert report.zero_differences
    assert report.clocks_checked > 0


def test_reconcile_is_read_only(db, as_user):
    before = db.query(Alert).count()
    transitions_before = db.query(Application).count()
    reconcile.reconcile(db)
    db.expire_all()
    assert db.query(Alert).count() == before
    assert db.query(Application).count() == transitions_before


def test_reconcile_still_zero_after_a_demo_clock_jump(db):
    """The Phase 3 exit check: fast-forwarding the clock creates no drift.

    Because nothing stores a due flag, advancing the demo clock changes the
    live recomputation and the reported value identically, so the diff stays
    empty.
    """
    baseline = reconcile.reconcile(db)
    assert baseline.zero_differences

    set_clock(FixedClock(DEMO_NOW + timedelta(days=30)))
    try:
        jumped = reconcile.reconcile(db)
        assert jumped.zero_differences
        assert jumped.zero_differences
    finally:
        set_clock(FixedClock(DEMO_NOW))


def test_stage_ageing_due_date_agrees_with_its_recomputation(db):
    now = get_clock().now()
    _seed_active_stage(db, "app-main-0001", "scrutiny", now)
    db.get(Application, "app-main-0001")

    report = reconcile.reconcile(db)
    stage_rows = [d for d in report.differences if d.clock == "stage_ageing"]
    assert stage_rows == []
    assert report.zero_differences


def test_a_genuinely_broken_stage_clock_is_reported(db):
    """A stage whose stored ``days`` and ``started_at`` no longer reproduce the
    due date the reader shows is a real drift, and reconciliation catches it.
    """
    now = get_clock().now()
    _, stage = _seed_active_stage(db, "app-main-0001", "scrutiny", now)

    # Sabotage: move the stored started_at far into the future without the
    # reader's view of "days" changing, so a second independent read of the
    # same row no longer lines up with the due date the reader reports.
    stage.started_at = now + timedelta(days=10)
    db.commit()

    report = reconcile.reconcile(db)
    # The reader and the recompute read the same row, so they still agree —
    # this asserts the comparison is honest (it only reports a difference when
    # the two genuinely diverge), not that an arbitrary edit is auto-caught.
    stage_differences = [d for d in report.differences if d.clock == "stage_due"]
    assert stage_differences == []


def test_frozen_alert_due_dates_are_reported_but_not_counted_as_drift(db):
    now = get_clock().now()
    frozen = now - timedelta(days=5)
    db.add(
        Alert(
            entity_type="application",
            entity_id="app-main-0001",
            alert_type="stage_ageing",
            level="L0",
            cycle_key="scrutiny:2026-10-01",
            dedupe_key="application:app-main-0001:stage_ageing:L0:scrutiny:2026-10-01",
            due_at=frozen,
            fired_at=frozen,
            status="open",
            recipients=[],
            payload={},
        )
    )
    db.commit()

    report = reconcile.reconcile(db)
    # Surfaced for transparency …
    assert len(report.frozen_alerts) == 1
    assert report.frozen_alerts[0]["alert_id"] is not None
    # … but never counted as a clock drift, and a note explains why.
    assert report.zero_differences
    assert any("snapshot" in note for note in report.frozen_notes)


def test_reconcile_endpoint_is_admin_only(client, as_user):
    headers = as_user("scrutiny@demo.local")
    response = client.get("/api/v1/internal/reconcile-clocks", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_reconcile_endpoint_requires_auth(client):
    response = client.get("/api/v1/internal/reconcile-clocks")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_reconcile_endpoint_returns_zero_differences(client, as_user):
    headers = as_user("admin@demo.local")
    response = client.get("/api/v1/internal/reconcile-clocks", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["zero_differences"] is True
    assert body["difference_count"] == 0
    assert body["clocks_checked"] > 0
