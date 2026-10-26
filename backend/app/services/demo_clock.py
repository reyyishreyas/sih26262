"""Demo clock control: advance / reset the injectable clock (PRD "Demo extras").

Phase 3.8. The PRD's demo narrative (line 334) needs time to be moved so
reminders and escalation can be shown without waiting for real days: "a demo
clock that advances time to show reminders and escalation". Nothing stores a
"due" flag (see ``core/clock``), so fast-forwarding the clock cannot leave the
database inconsistent — every deadline is recomputed from ``now`` on read.

Two safety rules are enforced here, not left to convention:

1. **Production refuses, always.** ``Settings.is_production`` makes every
   mutating call a refusal. A demo clock that could move time in production
   would silently re-age every case and fire every reminder, so the refusal is
   a hard guard at the top of every handler, not a hidden UI affordance.
2. **The clock must be injectable.** The control only operates when a
   ``FixedClock`` is installed (``SIH_CLOCK_MODE=fixed``). On a live
   ``SystemClock`` there is nothing to move — ``advance``/``reset`` refuse
   rather than pretending, so the demo panel can never be mistaken for a
   working control that quietly does nothing.

Every change is audited (who moved time, from what, to what) so a demo that
moves the clock is as traceable as a decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status

from ..core.clock import FixedClock, get_clock, iso, set_clock, to_utc
from ..core.config import get_settings
from .audit_service import AuditService
from .authorization_service import EffectiveAccess


def _refuse_production() -> None:
    if get_settings().is_production:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "the demo clock is disabled in production; time cannot be moved",
        )


def _require_fixed_clock() -> FixedClock:
    clock = get_clock()
    if not isinstance(clock, FixedClock):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the demo clock needs SIH_CLOCK_MODE=fixed (the injectable clock is "
            "not installed on this deployment)",
        )
    return clock


def status_view() -> dict:
    """Read-only view of the current clock for the demo panel.

    Production reports ``enabled: false`` and the real system time, so the
    panel can hide itself without a second config round-trip.
    """
    settings = get_settings()
    clock = get_clock()
    installed = isinstance(clock, FixedClock)
    return {
        "enabled": (not settings.is_production) and installed,
        "production": settings.is_production,
        "mode": "fixed" if installed else settings.clock_mode,
        "now": iso(clock.now()),
    }


def _move(
    db,
    access: EffectiveAccess,
    kind: str,
    target: datetime,
    *,
    request_id: str | None = None,
) -> dict:
    """Move the fixed clock to ``target`` and audit the jump.

    Shared by ``advance``/``set_to``/``reset`` so the guard, the install check
    and the audit row are written once.
    """
    _refuse_production()
    clock = _require_fixed_clock()
    before = iso(clock.now())
    set_clock(FixedClock(to_utc(target) or target))
    AuditService(db).append(
        action=f"demo_clock.{kind}",
        entity_type="clock",
        entity_id="demo",
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=f"demo clock {kind} to {iso(target)}",
        before={"now": before},
        after={"now": iso(target)},
        request_id=request_id,
    )
    db.commit()
    return {"mode": "fixed", "now": iso(target)}


def advance(
    db,
    access: EffectiveAccess,
    days: float,
    *,
    request_id: str | None = None,
) -> dict:
    """Move the demo clock forward by ``days`` (fractional days allowed)."""
    clock = _require_fixed_clock()
    return _move(
        db, access, "advance", clock.now() + timedelta(days=days), request_id=request_id
    )


def set_to(
    db,
    access: EffectiveAccess,
    moment: str,
    *,
    request_id: str | None = None,
) -> dict:
    """Move the demo clock to an explicit instant (ISO-8601)."""
    _require_fixed_clock()
    try:
        target = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"invalid instant {moment!r}; use ISO-8601 (e.g. 2026-11-01T09:00:00Z)",
        ) from exc
    return _move(db, access, "set", to_utc(target) or target, request_id=request_id)


def reset(
    db,
    access: EffectiveAccess,
    *,
    request_id: str | None = None,
) -> dict:
    """Return the demo clock to the configured fixed instant.

    The configured instant is re-read from settings on every reset, so the
    panel always returns to the deployment's own demo baseline rather than a
    hard-coded date.
    """
    settings = get_settings()
    if not settings.clock_fixed_at:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no SIH_CLOCK_FIXED_AT configured; the demo clock has no baseline to reset to",
        )
    _require_fixed_clock()
    return _move(
        db,
        access,
        "reset",
        datetime.fromisoformat(settings.clock_fixed_at),
        request_id=request_id,
    )
