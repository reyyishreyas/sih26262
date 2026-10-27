"""Deficiency report and compliance window (Plan 4.4, FR-15).

PRD FR-15 (line 187): *"Deficiency report, compliance window, compliance
upload to Re-Scrutiny"*, APH s2.3.3b/2.4 as the PRD cites it. The row-level
loop already exists (draft deficiencies are created during scrutiny,
``return_for_clarification`` issues them as ``open``, the institution's
corrective upload flips them to ``addressed``, the officer closes them, and
``resubmit`` hands the case back for Re-Scrutiny — see
``api/deficiencies.py``, ``workflow_service`` and ``test_deficiency_loop``).
This module adds the two composed views FR-15 names on top of that loop:

1. **The deficiency report** — one artefact the institution receives: the
   issued deficiencies, when they were issued, the reply window, and what
   has come back. Computed on read, never stored (same principle as the
   checklist and every clock in this repo).
2. **The compliance window** — the institution's reply clock, from the
   *issue instant* (the accepted ``return_for_clarification`` transition,
   structured data — never free-text parsing) plus the configured
   ``window_days``.

Four honesty rules the implementation keeps:

- **A draft report is officer-only and says so.** While deficiencies are
  ``draft`` and the case has not been returned, the report status is
  ``draft``; the institution is answered "no report has been issued", never
  shown drafts and never told drafts exist (mirrors the list endpoint's
  institution filter).
- **The window length is a labelled placeholder.** The PRD's s11 table
  gives the reminder cadence (7d, 2d, due date) but not the window length;
  PRD s19 Q1 leaves reply-time targets open. ``window_days`` therefore
  ships as clearly-labelled placeholder configuration
  (``rules/compliance_policy.json``) and the snapshot carries the
  placeholder/advisory labels with it.
- **An expired window never blocks anything** (DEC-0003). The report says
  ``overdue`` and the sweep raises the configured reminders (including the
  "Regional on miss" escalation level); the upload and resubmit routes are
  unchanged. A deadline in this product is a signal, not a lock.
- **The Re-Scrutiny leg is the existing workflow.** This module *surfaces*
  ``resubmitted_at``/``awaiting_re_scrutiny``; it never moves a case.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import iso, to_utc
from ..models import Application, Deficiency, WorkflowTransition
from . import working_calendar
from .policy import compliance_policy

ISSUE_ACTION = "return_for_clarification"
RESUBMIT_ACTION = "resubmit"
# The deficiency statuses that mean "the institution owes a reply".
OUTSTANDING = ("open", "addressed")


def config() -> dict[str, Any]:
    """The raw compliance configuration (``rules/compliance_policy.json``)."""
    return compliance_policy()


def window_days() -> int:
    """The configured compliance window length (placeholder, advisory)."""
    return int(config().get("window_days", 0))


def _issued_at(db: Session, application_id: str) -> datetime | None:
    """The issue instant: the latest accepted return-for-clarification.

    Structured data — the workflow transition row, never free text. A case
    that has never been returned has no issued report.
    """
    row = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application_id,
            WorkflowTransition.action == ISSUE_ACTION,
        )
        .order_by(WorkflowTransition.created_at.desc())
    ).first()
    return to_utc(row.created_at) if row else None


def _resubmitted_at(db: Session, application_id: str, since: datetime) -> datetime | None:
    """The latest resubmission *after* the current issue instant, if any."""
    row = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application_id,
            WorkflowTransition.action == RESUBMIT_ACTION,
        )
        .order_by(WorkflowTransition.created_at.desc())
    ).first()
    if row is None:
        return None
    moment = to_utc(row.created_at)
    return moment if moment is not None and moment > since else None


def _closes_at(issued_at: datetime) -> datetime:
    """Window close: end of the Nth calendar day after the issue day.

    The same end-of-day convention as every other deadline (appeal,
    undertaking, stage SLA). Calendar days, not working days — the s11
    table's cadence ("7d, 2d, due date") is written in plain days and no
    working-day rule for compliance is recorded anywhere in the PRD.
    """
    from .deadline_service import end_of_day

    day = working_calendar.business_date(issued_at) + timedelta(days=window_days() - 1)
    return end_of_day(day)


def _deficiency_rows(db: Session, application_id: str) -> list[Deficiency]:
    return list(
        db.scalars(
            select(Deficiency)
            .where(Deficiency.application_id == application_id)
            .order_by(Deficiency.created_at.asc())
        ).all()
    )


def _row_dict(row: Deficiency) -> dict[str, Any]:
    return {
        "id": row.id,
        "category": row.category,
        "field_name": row.field_name,
        "explanation": row.explanation,
        "corrective_action": row.corrective_action,
        "status": row.status,
        "document_id": row.document_id,
        "corrective_document_id": row.corrective_document_id,
        "created_at": iso(row.created_at),
        "resolved_at": iso(row.resolved_at),
        "resolution_note": row.resolution_note,
    }


def report_view(
    db: Session,
    application: Application,
    now: datetime,
    *,
    include_drafts: bool = True,
) -> dict[str, Any]:
    """The composed deficiency report for one case, computed on read.

    ``include_drafts=False`` is the institution's view: drafts are never
    returned and a never-returned case answers ``"not_issued"`` — an
    applicant must not learn that a draft exists (that would leak the
    officer's working notes through the API).

    Read-only: nothing here is stored, and the answer never gates the
    upload or resubmit routes (DEC-0003).
    """
    rows = _deficiency_rows(db, application.id)
    drafts = [r for r in rows if r.status == "draft"]
    issued_rows = [r for r in rows if r.status != "draft"]

    issued_at = _issued_at(db, application.id)
    config_data = config()
    labels = {
        "placeholder": config_data.get("placeholder", False),
        "advisory_only": config_data.get("advisory_only", True),
        "source": config_data.get("source"),
        "window_days": window_days(),
    }

    if issued_at is None:
        # The institution is told nothing about drafts — not even their
        # existence. "not_issued" is therefore the *only* answer a caller who
        # may not see drafts ever gets before the issue instant: answering
        # "none" when no drafts exist and "not_issued" when drafts do exist
        # would leak that a draft is waiting through the status value alone.
        if not include_drafts:
            status = "not_issued"
        elif drafts:
            status = "draft"
        else:
            status = "none"
        return {
            "application_id": application.id,
            "status": status,
            "issued_at": None,
            "closes_at": None,
            "window_status": "not_started",
            "days_remaining": None,
            "overdue": False,
            "resubmitted_at": None,
            "awaiting_re_scrutiny": False,
            "counts": _counts(issued_rows if include_drafts else [], drafts if include_drafts else []),
            "deficiencies": [
                _row_dict(r) for r in (issued_rows if include_drafts else [])
            ] + ([_row_dict(r) for r in drafts] if include_drafts else []),
            "note": (
                "Draft deficiencies are officer working notes and are not part "
                "of any issued report."
                if status == "draft"
                else None
            ),
            **labels,
        }

    closes_at = _closes_at(issued_at)
    resubmitted_at = _resubmitted_at(db, application.id, issued_at)
    outstanding = [r for r in issued_rows if r.status in OUTSTANDING]
    window_open = now <= closes_at
    # The institution's reply is *in* once it has resubmitted — that is the
    # PRD's "compliance upload to Re-Scrutiny" handover. Uploading corrective
    # documents alone (deficiencies flipping to "addressed") is progress, not
    # the reply: the case only re-enters scrutiny on resubmit.
    if resubmitted_at is not None:
        window_status = "received"
    elif window_open:
        window_status = "open"
    else:
        window_status = "overdue"
    days_remaining = max(0, (to_utc(closes_at) - now).days) if window_open else 0

    visible = issued_rows
    return {
        "application_id": application.id,
        "status": "issued",
        "issued_at": iso(issued_at),
        "closes_at": iso(closes_at),
        "window_status": window_status,
        "days_remaining": days_remaining,
        "overdue": window_status == "overdue",
        "resubmitted_at": iso(resubmitted_at),
        "awaiting_re_scrutiny": resubmitted_at is not None and bool(outstanding),
        "counts": _counts(visible, []),
        "deficiencies": [_row_dict(r) for r in visible],
        "note": (
            "The compliance window is advisory: an overdue report never blocks "
            "an upload or a resubmission — it raises the reminder ladder "
            "(PRD s11: 7d, 2d, due date; Regional on miss)."
            if window_status == "overdue"
            else None
        ),
        **labels,
    }


def _counts(issued: list[Deficiency], drafts: list[Deficiency]) -> dict[str, int]:
    counts = {"draft": len(drafts), "open": 0, "addressed": 0, "closed": 0}
    for row in issued:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def compliance_window_item(
    db: Session, application: Application, now: datetime
) -> Any | None:
    """A ``DeadlineItem`` for the sweep, or None for this case.

    Only a case whose report is issued and still awaiting the institution's
    reply produces an item; the sweep turns the configured 7d / 2d / due-date
    cadence (PRD s11 line 281) into alerts through the same idempotent path
    as every other deadline. Advisory — it raises reminders, never a gate.

    The cycle key encodes the issue instant, so a *re*-return after a
    re-scrutiny starts a fresh reminder cycle instead of reusing the old
    dedupe key.
    """
    from .deadline_service import DeadlineItem

    issued_at = _issued_at(db, application.id)
    if issued_at is None:
        return None
    # Reminders run while the institution still owes its reply. They stop the
    # moment it resubmits ("alerts stop when task closes", PRD s11); closing
    # every deficiency without a resubmit does NOT stop them, because the case
    # has not actually re-entered scrutiny.
    if _resubmitted_at(db, application.id, issued_at) is not None:
        return None
    rows = [r for r in _deficiency_rows(db, application.id) if r.status != "draft"]
    if not rows:
        # Nothing was actually issued with the return — no reminder to raise.
        return None

    closes_at = _closes_at(issued_at)
    return DeadlineItem(
        entity_type="application",
        entity_id=application.id,
        alert_type="compliance_window",
        due_at=closes_at,
        cycle_key=f"compliance:{issued_at.date().isoformat()}",
        application_id=application.id,
        payload={
            "issued_at": iso(issued_at),
            "window_days": window_days(),
            "placeholder": True,
            "advisory_only": True,
        },
    )
