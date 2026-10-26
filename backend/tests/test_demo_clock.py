"""Demo clock control (Phase 3.8) — advance / reset the injectable clock.

Tests exercise the service directly with an ``EffectiveAccess`` (the pattern
used by the rehearsal tests) plus a few thin HTTP checks through the client to
confirm the router wires the right permission gate. The properties covered are
the ones that make the demo clock safe to ship: advance/reset/set move time and
are audited, production refuses outright (the hard guard in
``demo_clock._refuse_production``), a deployment whose clock is not injectable
refuses rather than pretending, and reset without a configured baseline fails
loudly instead of inventing an epoch.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.clock import FixedClock, SystemClock, get_clock, set_clock
from app.models.audit import AuditEvent
from app.services import demo_clock
from tests.conftest import DEMO_NOW

ADMIN = "admin@demo.local"
SCRUTINY = "scrutiny@demo.local"


def _reset_clock() -> None:
    set_clock(FixedClock(DEMO_NOW))


@pytest.fixture(autouse=True)
def restore_clock():
    """Every test starts and ends on the pinned demo instant."""
    _reset_clock()
    yield
    _reset_clock()


def test_status_view_reports_the_live_fixed_clock():
    body = demo_clock.status_view()
    assert body["mode"] == "fixed"
    assert body["enabled"] is True
    assert body["now"] == DEMO_NOW.isoformat().replace("+00:00", "Z")


def test_status_view_is_disabled_on_a_system_clock(monkeypatch):
    """On a live system clock the panel hides: ``enabled`` is False.

    ``mode`` still echoes the configured ``clock_mode`` (the deployment's
    declared setting), but the panel keys off ``enabled``, which requires a
    ``FixedClock`` to be actually installed. We patch settings so ``mode``
    reports ``system``, matching the clock we install.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(
        "app.services.demo_clock.get_settings",
        lambda: get_settings().model_copy(update={"clock_mode": "system"}),
    )
    set_clock(SystemClock())
    body = demo_clock.status_view()
    assert body["enabled"] is False
    assert body["mode"] == "system"


def test_advance_moves_time_forward_and_is_audited(db, access_for):
    access = access_for(ADMIN)
    before = get_clock().now()

    result = demo_clock.advance(db, access, 3)

    after = get_clock().now()
    assert after == before + timedelta(days=3)
    assert result["mode"] == "fixed"

    event = (
        db.query(AuditEvent)
        .filter_by(action="demo_clock.advance")
        .order_by(AuditEvent.seq.desc())
        .first()
    )
    assert event is not None
    assert event.entity_type == "clock"
    assert event.outcome == "accepted"
    assert event.actor_id == access.user_id


def test_advance_accepts_fractional_days(db, access_for):
    access = access_for(ADMIN)
    before = get_clock().now()
    demo_clock.advance(db, access, 0.5)
    assert get_clock().now() == before + timedelta(hours=12)


def test_reset_returns_to_the_configured_baseline(db, access_for):
    access = access_for(ADMIN)
    demo_clock.advance(db, access, 10)
    assert get_clock().now() != DEMO_NOW

    demo_clock.reset(db, access)
    assert get_clock().now() == DEMO_NOW


def test_set_to_an_explicit_instant(db, access_for):
    access = access_for(ADMIN)
    demo_clock.set_to(db, access, "2026-12-01T00:00:00+00:00")
    assert get_clock().now().isoformat().startswith("2026-12-01")


def test_set_rejects_a_malformed_instant(db, access_for):
    access = access_for(ADMIN)
    with pytest.raises(HTTPException) as exc:
        demo_clock.set_to(db, access, "not-a-date")
    assert exc.value.status_code == 422


def test_non_admin_is_denied_by_the_router(client, as_user):
    """The router, not the service, enforces the ADMIN_USERS gate."""
    headers = as_user(SCRUTINY)
    response = client.get("/api/v1/admin/demo-clock", headers=headers)
    assert response.status_code == 403


def test_unauthenticated_caller_is_rejected(client):
    response = client.get("/api/v1/admin/demo-clock")
    assert response.status_code == 401


def test_production_refuses_to_move_time(monkeypatch):
    """The hard guard: production refuses even an administrator's advance."""
    from app.core.config import get_settings

    prod = get_settings().model_copy(update={"env": "production", "clock_mode": "system"})
    monkeypatch.setattr("app.services.demo_clock.get_settings", lambda: prod)

    with pytest.raises(HTTPException) as exc:
        demo_clock._refuse_production()
    assert exc.value.status_code == 403
    assert "production" in exc.value.detail


def test_advance_refuses_when_the_clock_is_not_injectable(db, access_for):
    """On a live system clock there is nothing to move — refuse, don't pretend."""
    access = access_for(ADMIN)
    set_clock(SystemClock())
    with pytest.raises(HTTPException) as exc:
        demo_clock.advance(db, access, 1)
    assert exc.value.status_code == 409
    assert "SIH_CLOCK_MODE=fixed" in exc.value.detail


def test_reset_without_a_baseline_refuses(monkeypatch, db, access_for):
    from app.core.config import get_settings

    no_baseline = get_settings().model_copy(update={"clock_fixed_at": None})
    monkeypatch.setattr("app.services.demo_clock.get_settings", lambda: no_baseline)
    access = access_for(ADMIN)
    with pytest.raises(HTTPException) as exc:
        demo_clock.reset(db, access)
    assert exc.value.status_code == 409
    assert "SIH_CLOCK_FIXED_AT" in exc.value.detail
