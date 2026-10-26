"""Security Deposit: the FR-33 penalty schedule and withdrawal marker.

Plan 3.6 (AGENT-02) models the PRD §7 security-deposit penalty rules as
configuration plus pure lookups, so nothing about "which penalty, and when"
is hard-coded.

PRD FR-33 (line 213) and the §7 rules table (line 244) record: the Security
Deposit proof + Affidavit 3 has a **15-day** window, a **10% penalty up to
31 May**, a **20% penalty up to 31 July**, and the case is **withdrawn after**
that (APH cl. 2.25f). §11 line 289 gives the institution-side reminder cadence
(**day 1, 10, 14** of the proof window, escalated to the Bureau).

Two constraints shape this module:

1. **No invented regulation, no silent activation.** The 15-day window, the
   10%/20% percentages and the fixed 31-May/31-July dates are AICTE regulatory
   values and ship as clearly-labelled placeholder configuration
   (``rules/security_deposit_policy.json``). Every snapshot returns the
   ``unverified``/``placeholder``/``advisory_only`` labels so a caller can
   never mistake a placeholder for a confirmed AICTE rule.
2. **Advisory only, no new state (DEC-0003, rule 15).** These functions
   compute which penalty band a date falls in and a ``withdrawal_flagged``
   marker for display. They gate nothing, move no case and write nothing.
   The actual withdrawal is a NEW REGULATORY STATE (rule 15 human gate) and
   is deliberately **not** triggered here — the marker is advisory, so an
   overdue deposit is never silently withdrawn by a clock.

The 15-day proof window itself is modelled as an **Undertaking** (obligation
+ due date + evidence, ``obligation_key`` ``security_deposit_proof``), so the
day-1/10/14 reminders ride the existing ``undertaking_due`` alert ladder
(``deadline_service``) instead of a second clock. This module only computes
the penalty schedule and the withdrawal marker from the configured fixed
dates, which are calendar-anchored (31 May / 31 July of the relevant year),
not relative to an entry instant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import to_utc
from ..models import Application, Undertaking
from .policy import security_deposit_policy

OBLIGATION_KEY = "security_deposit_proof"


def config() -> dict[str, Any]:
    """The raw security-deposit configuration (``rules/security_deposit_policy.json``)."""
    return security_deposit_policy()


def proof_window_days() -> int:
    """The configured proof window length in days (placeholder, advisory)."""
    return int(config().get("proof_window_days", 0))


def _month_day(value: str) -> tuple[int, int]:
    """Parse an ``MM-DD`` configured date into a (month, day) tuple."""
    month, day = value.split("-")
    return int(month), int(day)


def _deadline_on_or_before(value: str, year: int) -> date:
    """The calendar date the configured ``MM-DD`` falls on in ``year``.

    A malformed config value raises (fails loudly) rather than silently
    defaulting, so a typo in a penalty date is visible in the tests.
    """
    month, day = _month_day(value)
    return date(year, month, day)


@dataclass(frozen=True)
class PenaltyBand:
    """The penalty that applies on a given date (None = no penalty)."""

    band_id: str | None
    penalty_percent: int | None
    withdrawal_flagged: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "band_id": self.band_id,
            "penalty_percent": self.penalty_percent,
            "withdrawal_flagged": self.withdrawal_flagged,
        }


def penalty_for_date(on: date) -> PenaltyBand:
    """Which penalty band the date ``on`` falls in (pure date maths).

    Walks the configured schedule in order and returns the first band whose
    ``on_or_before`` date is on or after ``on``. A date after every band's
    deadline (and after the withdrawal ``after`` date) reports the withdrawal
    marker with no penalty percent — the honest answer, never a guess.
    ``band_id``/``penalty_percent`` are None when no band applies.
    """
    schedule = sorted(
        config().get("penalty_schedule", []),
        key=lambda entry: _deadline_on_or_before(entry["on_or_before"], on.year),
    )
    for entry in schedule:
        deadline = _deadline_on_or_before(entry["on_or_before"], on.year)
        if on <= deadline:
            return PenaltyBand(
                band_id=entry["id"],
                penalty_percent=int(entry["penalty_percent"]),
                withdrawal_flagged=False,
            )

    withdrawal_after = config().get("withdrawal_flag", {}).get("after")
    flagged = bool(withdrawal_after) and on > _deadline_on_or_before(withdrawal_after, on.year)
    return PenaltyBand(band_id=None, penalty_percent=None, withdrawal_flagged=flagged)


def proof_deadline(application: Application) -> date | None:
    """The configured proof-window deadline for a case, or None.

    The 15-day window runs from the grant/list date (the instant the case was
    approved). Until a first-class grant event exists to anchor it, the
    decision state's start (``current_state_since``) is the honest proxy, the
    same way the appeal clock (Phase 3.5) anchors on it. None means the case
    is not approved yet — there is no deposit to prove.
    """
    if application.current_state != "approved":
        return None
    decision_at = to_utc(application.current_state_since)
    if decision_at is None:
        return None
    from datetime import timedelta

    return (decision_at.date() + timedelta(days=proof_window_days()))


def _deposit_undertaking(db: Session, application_id: str) -> Undertaking | None:
    return db.scalars(
        select(Undertaking).where(
            Undertaking.application_id == application_id,
            Undertaking.obligation_key == OBLIGATION_KEY,
        )
    ).first()


def sd_snapshot(db: Session, application: Application, now: datetime) -> dict[str, Any]:
    """Advisory security-deposit view for one case, computed on read.

    Returns the configured labels plus the proof-window deadline and the
    penalty band that today's date falls in, plus the ``withdrawal_flagged``
    marker once past the last penalty date. Read-only — it moves no case,
    changes no state and writes nothing (DEC-0003), and it never withdraws a
    case (rule 15). A case that is not approved reports
    ``status: "not_applicable"`` rather than inventing a window.
    """
    config_data = config()
    proof_deadline_date = proof_deadline(application)
    if proof_deadline_date is None:
        return {
            "application_id": application.id,
            "status": "not_applicable",
            "decision_state": application.current_state,
            "proof_window_days": proof_window_days(),
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", True),
            "source": config_data.get("source"),
            "obligation": config_data.get("obligation"),
            "penalty": None,
            "withdrawal_flagged": False,
        }

    today = now.date()
    band = penalty_for_date(today)
    undertaking = _deposit_undertaking(db, application.id)
    return {
        "application_id": application.id,
        "status": "open",
        "decision_state": application.current_state,
        "proof_window_days": proof_window_days(),
        "proof_deadline": proof_deadline_date.isoformat(),
        "undertaking_status": undertaking.status if undertaking else None,
        "placeholder": config_data.get("placeholder", False),
        "advisory_only": config_data.get("advisory_only", True),
        "source": config_data.get("source"),
        "obligation": config_data.get("obligation"),
        "penalty": band.as_dict(),
        "withdrawal_flagged": band.withdrawal_flagged,
    }
