"""Appeal window: the FR-27 seven-day clock on a decision, and who may appeal.

Plan 3.5 (AGENT-02) models the PRD §7/§11 appeal clock as configuration plus
pure lookups, so nothing about "how long, and how often" is hard-coded.

PRD FR-27 (line 206) and the §7 rules table (line 288) record: an appeal to
the Council runs **once, within 7 days of the decision upload** (APH cl.
2.24a); §11 line 288 gives the institution-side reminder cadence (**day 3 and
day 6 of 7, window closes day 7**). ``md/rules2.json`` REG-APPEAL-001 records
the 7-day figure as an *unverified example* and instructs that it must not be
activated as binding, so every value here ships as clearly-labelled
placeholder configuration (``rules/appeal_policy.json``).

Two constraints shape this module:

1. **No invented regulation, no silent activation.** The day counts, the
   one-appeal limit and the receiving authority (SAC — an open human question,
   like the §19 Q5 designated authority) all live in config and carry
   ``unverified``/``placeholder``/``advisory_only`` labels that are returned
   on every snapshot, so a caller can never mistake a placeholder for a
   confirmed AICTE rule.
2. **Advisory only, no new state (DEC-0003, Phase 6.6).** These functions
   compute a window and a "may file" flag for display. They gate nothing, move
   no case and write nothing. There is deliberately no ``file_appeal``
   transition — Phase 6.6 implements that separately — so an appeal is counted from any recorded
   ``WorkflowTransition`` whose action matches the configured
   ``appeal_action`` once Phase 6.6 adds it, and today that count is simply
   zero.

For new Executive Committee decisions, the window starts at the linked Speaking
Order's ``uploaded_at`` time. Legacy decisions without that link continue to use
``current_state_since``. Both views remain advisory while the regulatory duration
is Unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import iso, to_utc
from ..models import Application, Document, WorkflowTransition
from . import working_calendar
from .policy import appeal_policy

DECISION_STATES = frozenset({"approved", "rejected"})


def config() -> dict[str, Any]:
    """The raw appeal configuration (``rules/appeal_policy.json``)."""
    return appeal_policy()


def window_days() -> int:
    """The configured appeal window length in days (placeholder, advisory)."""
    return int(config().get("window_days", 0))


def max_appeals() -> int:
    """How many appeals a case may carry (FR-27: once — placeholder)."""
    return int(config().get("max_appeals", 1))


def appeal_action() -> str:
    """The workflow action that records a filed appeal (config, not code)."""
    return str(config().get("appeal_action", "file_appeal"))


@dataclass(frozen=True)
class AppealWindow:
    """The computed appeal clock for one decided case.

    ``opens_at``/``closes_at`` are end-of-day instants in the business
    timezone (the same convention as every other deadline), stored in UTC.
    """

    application_id: str
    decision_state: str | None
    decision_at: datetime | None
    opens_at: datetime | None
    closes_at: datetime | None
    appeals_filed: int
    may_file: bool
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "decision_state": self.decision_state,
            "decision_at": iso(self.decision_at),
            "opens_at": iso(self.opens_at),
            "closes_at": iso(self.closes_at),
            "window_days": window_days(),
            "appeals_filed": self.appeals_filed,
            "max_appeals": max_appeals(),
            "may_file": self.may_file,
            "status": self.status,
        }


def _is_decided(application: Application) -> bool:
    return application.current_state in DECISION_STATES


def appeals_filed(db: Session, application_id: str) -> int:
    """How many appeals are recorded for this case (0 until Phase 6.6).

    Counted from ``WorkflowTransition`` rows whose action matches the
    configured ``appeal_action`` — structured data, never free-text guesswork.
    With no such transition defined yet this is always zero, which keeps the
    "one appeal only" limit honest rather than assumed.
    """
    rows = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == application_id,
            WorkflowTransition.action == appeal_action(),
        )
    ).all()
    return len(rows)


def window_for(
    application: Application,
    now: datetime,
    *,
    decision_at: datetime | None = None,
) -> AppealWindow | None:
    """The appeal window for a case, or None when it is not in a decision state.

    Pure date maths over configuration — no DB, no writes. A case still in the
    queue (or in draft) has no decision to appeal, so there is no window.
    """
    if not _is_decided(application):
        return None

    decision_at = to_utc(decision_at or application.current_state_since)
    if decision_at is None:
        return None

    from .deadline_service import end_of_day

    days = window_days()
    opens_at = end_of_day(working_calendar.business_date(decision_at))
    closes_at = end_of_day(
        working_calendar.business_date(decision_at) + timedelta(days=days - 1)
    )
    return AppealWindow(
        application_id=application.id,
        decision_state=application.current_state,
        decision_at=decision_at,
        opens_at=opens_at,
        closes_at=closes_at,
        appeals_filed=0,  # filled by the caller when a DB session is available
        may_file=now <= closes_at,
        status="open" if now <= closes_at else "lapsed",
    )


def _decision_upload_time(db: Session, application: Application) -> datetime | None:
    """Use the linked Speaking Order upload as the appeal-clock trigger."""
    transition = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application.id,
            WorkflowTransition.to_state == application.current_state,
            WorkflowTransition.action.in_(("approve", "reject")),
            WorkflowTransition.reverted_at.is_(None),
        )
        .order_by(WorkflowTransition.created_at.desc(), WorkflowTransition.id.desc())
    ).first()
    if transition and transition.speaking_order_document_id:
        document = db.get(Document, transition.speaking_order_document_id)
        if document is not None:
            return to_utc(document.uploaded_at)
    # Existing decisions predate first-class Speaking Orders. Preserve their
    # advisory clock until they are superseded by a newly recorded decision.
    return to_utc(application.current_state_since)


def _with_appeals(db: Session, window: AppealWindow) -> AppealWindow:
    """Stamp the real filed-appeal count onto a computed window."""
    filed = appeals_filed(db, window.application_id)
    may = window.status == "open" and filed < max_appeals()
    return AppealWindow(
        application_id=window.application_id,
        decision_state=window.decision_state,
        decision_at=window.decision_at,
        opens_at=window.opens_at,
        closes_at=window.closes_at,
        appeals_filed=filed,
        may_file=may,
        status=window.status,
    )


def appeal_snapshot(db: Session, application: Application, now: datetime) -> dict[str, Any]:
    """Advisory appeal view for one case, computed on read.

    Returns the configured labels plus the window and the "may file" answer
    (open window **and** under the one-appeal limit). Read-only — it moves no
    case, changes no state and writes nothing (DEC-0003); the sweep's alerts
    and the workflow are unchanged. A case that is not decided reports
    ``status: "not_decided"`` rather than inventing a window.
    """
    config_data = config()
    window = window_for(
        application,
        now,
        decision_at=_decision_upload_time(db, application),
    )
    if window is None:
        return {
            "application_id": application.id,
            "status": "not_decided",
            "decision_state": application.current_state,
            "window_days": window_days(),
            "max_appeals": max_appeals(),
            "appeals_filed": appeals_filed(db, application.id),
            "may_file": False,
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", True),
            "source": config_data.get("source"),
            "receiving_authority": config_data.get("receiving_authority"),
        }

    window = _with_appeals(db, window)
    snapshot = window.as_dict()
    snapshot.update(
        {
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", True),
            "source": config_data.get("source"),
            "receiving_authority": config_data.get("receiving_authority"),
        }
    )
    return snapshot


def appeal_window_item(
    application: Application,
    now: datetime,
    db: Session | None = None,
) -> Any | None:
    """A ``DeadlineItem`` for the appeal-window sweep, or None.

    Only a decided case still inside (or just past) its window produces an
    item; the sweep turns the configured day-3 / day-6 reminders into alerts
    through the same idempotent path as every other deadline. Advisory — it
    raises a reminder, never a gate.
    """
    from .deadline_service import DeadlineItem

    decision_at = _decision_upload_time(db, application) if db is not None else None
    window = window_for(application, now, decision_at=decision_at)
    if window is None or window.closes_at is None:
        return None
    return DeadlineItem(
        entity_type="application",
        entity_id=application.id,
        alert_type="appeal_window",
        due_at=window.closes_at,
        cycle_key=f"appeal:{application.current_state}:{window.decision_at.date().isoformat()}",
        application_id=application.id,
        payload={
            "decision_state": window.decision_state,
            "decision_at": iso(window.decision_at),
            "window_days": window_days(),
            "placeholder": True,
            "advisory_only": True,
        },
    )
