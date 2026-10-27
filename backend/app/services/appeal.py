"""Verified Chapter II appeal window and supporting deadline reminder.

Plan 3.5 (AGENT-02) models the PRD §7/§11 appeal clock as configuration plus
pure lookups. Phase 6.6 implements the human SAC/Council appeal records.

AICTE Approval Process Handbook 2024–27 Chapter II §§2.23.3–2.24(a-f),
recorded as SRC-APH-APPEAL-2024-27, provides the appeal path: one appeal to the
Council within 7 days of Executive Committee decision upload, considered by
SAC, with the Council's final decision published on the portal. The 7-day
trigger is the linked Speaking Order upload time.

Two constraints shape this module:

1. **Verified scope only.** Chapter II §§2.23.3–2.24 support the current
   appeal permission and workflow. The configuration and endpoints do not
   extend these rules to other APH chapters or decision makers.
2. **The trigger must exist.** Chapter II §§2.23.3–2.24 starts the seven-day
   period when the Executive Committee decision is uploaded. A prior decision
   without its Speaking Order upload has no verified filing deadline and is
   not eligible for the Phase 6.6 filing endpoint.

For new Executive Committee decisions, the window starts at the linked Speaking
Order's ``uploaded_at`` time. Legacy decisions without that link continue to use
``current_state_since``. Both views remain advisory while the regulatory duration
is Unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import iso, to_utc
from ..models import Appeal, Application, WorkflowTransition
from .policy import appeal_policy

DECISION_STATES = frozenset({"approved", "rejected"})


def config() -> dict[str, Any]:
    """The raw appeal configuration (``rules/appeal_policy.json``)."""
    return appeal_policy()


def window_days() -> int:
    """Verified Chapter II appeal period in elapsed days."""
    return int(config().get("window_days", 0))


def max_appeals() -> int:
    """One appeal per Executive Committee decision, per Chapter II §2.24(a)."""
    return int(config().get("max_appeals", 1))


def appeal_action() -> str:
    """The workflow action that records a filed appeal (config, not code)."""
    return str(config().get("appeal_action", "file_appeal"))


def in_verified_scope(application: Application) -> bool:
    """Only enable the appeal rule on route keys mapped to APH Chapter II."""
    return application.route_key in config().get("applicable_route_keys", ())


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
    return in_verified_scope(application) and application.current_state in DECISION_STATES


def appeals_filed(db: Session, application_id: str) -> int:
    """Count persisted appeal rows for the application."""
    return int(
        db.scalar(select(func.count(Appeal.id)).where(Appeal.application_id == application_id))
        or 0
    )


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

    decision_at = to_utc(decision_at)
    if decision_at is None:
        return None

    days = window_days()
    opens_at = decision_at
    closes_at = decision_at + timedelta(days=days)
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
    """Use the accepted decision record with its linked order as the trigger."""
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
        return to_utc(transition.created_at)
    return None


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
    if not in_verified_scope(application):
        return {
            "application_id": application.id,
            "status": "outside_verified_scope",
            "decision_state": application.current_state,
            "window_days": window_days(),
            "max_appeals": max_appeals(),
            "appeals_filed": appeals_filed(db, application.id),
            "may_file": False,
            "placeholder": False,
            "advisory_only": False,
            "source": config_data.get("source"),
            "receiving_authority": config_data.get("receiving_authority"),
        }
    decision_at = _decision_upload_time(db, application)
    if decision_at is None:
        return {
            "application_id": application.id,
            "status": "decision_order_missing" if application.current_state in DECISION_STATES else "not_decided",
            "decision_state": application.current_state,
            "window_days": window_days(),
            "max_appeals": max_appeals(),
            "appeals_filed": appeals_filed(db, application.id),
            "may_file": False,
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", False),
            "source": config_data.get("source"),
            "receiving_authority": config_data.get("receiving_authority"),
        }
    window = window_for(
        application,
        now,
        decision_at=decision_at,
    )
    if window is None:
        reason = (
            "decision_order_missing"
            if _is_decided(application)
            else "not_decided"
        )
        return {
            "application_id": application.id,
            "status": reason,
            "decision_state": application.current_state,
            "window_days": window_days(),
            "max_appeals": max_appeals(),
            "appeals_filed": appeals_filed(db, application.id),
            "may_file": False,
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", False),
            "source": config_data.get("source"),
            "receiving_authority": config_data.get("receiving_authority"),
        }

    window = _with_appeals(db, window)
    snapshot = window.as_dict()
    snapshot.update(
        {
            "placeholder": config_data.get("placeholder", False),
            "advisory_only": config_data.get("advisory_only", False),
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
    if decision_at is None:
        return None
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
            "placeholder": False,
            "advisory_only": False,
        },
    )
