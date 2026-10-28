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
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
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


def proof_deadline(intimation_date: date | None) -> date | None:
    """Configured placeholder deadline from the date on a recorded notice."""
    if intimation_date is None:
        return None
    return intimation_date + timedelta(days=proof_window_days())


def _deposit_undertaking(db: Session, application_id: str) -> Undertaking | None:
    return db.scalars(
        select(Undertaking).where(
            Undertaking.application_id == application_id,
            Undertaking.obligation_key == OBLIGATION_KEY,
        )
    ).first()


def ensure_proof_undertaking(
    db: Session,
    application: Application,
    *,
    intimation_date: date,
    intimation_document_id: str,
) -> tuple[Undertaking, bool]:
    """Create the proof undertaking from a notice an officer explicitly records.

    This is never called from an approval transition. The supplied date and
    linked document preserve the separate intimation event that the Phase 6
    exit check requires. Timing stays placeholder/advisory configuration.
    """
    obligation = config().get("obligation", {})
    existing = _deposit_undertaking(db, application.id)
    if existing is not None:
        return existing, False

    if application.current_state != "approved":
        raise ValueError("a Security Deposit notice can only be recorded for an approved case")
    deadline = proof_deadline(intimation_date)
    if deadline is None:
        raise ValueError("a notice date is required to calculate the advisory window")

    window = proof_window_days()
    business_tz = ZoneInfo(get_settings().business_timezone)
    item = Undertaking(
        application_id=application.id,
        obligation_key=OBLIGATION_KEY,
        title=str(obligation.get("label", "Security Deposit proof")),
        condition_text=(
            f"Submit {obligation.get('label', 'Security Deposit proof')} and the "
            f"Affidavit 3 within the configured {window}-day window measured "
            "from the date recorded on the linked AICTE notice. An officer "
            "must review the source; dates and reminders remain advisory "
            "placeholder configuration."
        ),
        evidence_required=str(obligation.get("evidence_required", "")),
        source_received_on=intimation_date,
        source_document_id=intimation_document_id,
        due_at=datetime.combine(deadline, time(23, 59, 59), tzinfo=business_tz).astimezone(UTC),
        status="pending",
        reminder_policy={
            "profile": "security_deposit",
            "placeholder": bool(config().get("placeholder", True)),
            "advisory_only": bool(config().get("advisory_only", True)),
        },
    )
    db.add(item)
    db.flush()
    return item, True



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
    if application.current_state != "approved":
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

    undertaking = _deposit_undertaking(db, application.id)
    proof_deadline_date = proof_deadline(
        undertaking.source_received_on if undertaking else None
    )
    if undertaking is None or proof_deadline_date is None:
        return {
            "application_id": application.id,
            "status": "awaiting_intimation",
            "decision_state": application.current_state,
            "proof_window_days": proof_window_days(),
            "proof_deadline": None,
            "intimation_date": None,
            "source_document_id": None,
            "undertaking_status": None,
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", True),
            "source": config_data.get("source"),
            "obligation": config_data.get("obligation"),
            "penalty": None,
            "withdrawal_flagged": False,
        }

    today = now.date()
    band = penalty_for_date(today)
    return {
        "application_id": application.id,
        "status": "open",
        "decision_state": application.current_state,
        "proof_window_days": proof_window_days(),
        "proof_deadline": proof_deadline_date.isoformat(),
        "intimation_date": undertaking.source_received_on.isoformat(),
        "source_document_id": undertaking.source_document_id,
        "undertaking_status": undertaking.status if undertaking else None,
        "placeholder": config_data.get("placeholder", False),
        "advisory_only": config_data.get("advisory_only", True),
        "source": config_data.get("source"),
        "obligation": config_data.get("obligation"),
        "penalty": band.as_dict(),
        "withdrawal_flagged": band.withdrawal_flagged,
    }
