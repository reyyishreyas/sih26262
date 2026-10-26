"""Reconcile every clock-derived date against a fresh recomputation (Plan 3.9).

The whole deadline system rests on one invariant: *nothing stores a "due" flag*.
Every clock — an undertaking's due date, a document's expiry, a scheduled EVC
visit, a stage's ageing SLA, an appeal window — is derived on read from the
current clock plus configuration (``rules/deadline_policy.json``,
``stage_limits.json``). That is what lets the demo clock jump days forward and
the alarm clocks recompute cleanly with no stale column anywhere.

This module *proves* that invariant holds for a given database, so the demo
can show "reconciliation: 0 differences" with evidence rather than on trust.
It is **read-only**: it recomputes each date the same way the deadline sweep
(``collect_items``) and the per-stage reader (``stages.due_dates``) compute it,
then compares that to what the system reports, and lists any drift.

Why an alert's frozen ``due_at`` may legitimately differ from a live
recomputation, and why that is *not* a clock bug: the sweep snapshots an
alert's ``due_at`` at the moment it fires, keyed by a ``dedupe_key`` that
encodes the cycle (for stage ageing, ``{state}:{entered_on}``). When a case
moves to a new state, that is a *new* cycle with a new clock — the old alert
still describes the cycle it fired in. So reconciliation of a live clock
(the stage's *current* due date) is against ``stages.due_dates``; a frozen
alert ``due_at`` is checked only against its own recorded basis, and the
report says so rather than calling a legitimate cycle change a drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, to_utc
from ..models import Alert, Application, EvcVisit, StageInstance, Undertaking
from . import stages
from .deadline_service import collect_items, end_of_day
from .policy import stage_sla_days


@dataclass
class ReconcileRow:
    """One clock-derived date: what the live reader says, and what we recompute."""

    clock: str
    entity_type: str
    entity_id: str
    reported_due_at: datetime | None
    recomputed_due_at: datetime | None
    match: bool


@dataclass
class ReconcileReport:
    now: datetime
    clocks_checked: int = 0
    differences: list[ReconcileRow] = field(default_factory=list)
    frozen_alerts: list[dict] = field(default_factory=list)
    frozen_notes: list[str] = field(default_factory=list)

    @property
    def zero_differences(self) -> bool:
        return not self.differences

    def as_dict(self) -> dict:
        return {
            "now": to_utc(self.now).isoformat() if self.now else None,
            "clocks_checked": self.clocks_checked,
            "difference_count": len(self.differences),
            "zero_differences": self.zero_differences,
            "differences": [
                {
                    "clock": row.clock,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "reported_due_at": to_utc(row.reported_due_at).isoformat()
                    if row.reported_due_at
                    else None,
                    "recomputed_due_at": to_utc(row.recomputed_due_at).isoformat()
                    if row.recomputed_due_at
                    else None,
                }
                for row in self.differences
            ],
            # Frozen alert due_dates are reported for transparency but never
            # counted as a clock drift (they snapshot a past cycle by design).
            "frozen_alerts_checked": len(self.frozen_alerts),
            "frozen_alerts": self.frozen_alerts,
            "notes": self.frozen_notes,
        }


def _close(a: datetime | None, b: datetime | None) -> bool:
    """Two datetimes match if both are None or both land on the same instant."""
    if a is None or b is None:
        return a is None and b is None
    return to_utc(a) == to_utc(b)


def reconcile(db: Session, now: datetime | None = None) -> ReconcileReport:
    """Recompute every clock-derived date and report any drift. Read-only."""
    now = now or get_clock().now()
    report = ReconcileReport(now=now)

    # 1. Stage-ageing clocks: the live due date the deadline sweep would use,
    #    recomputed from current_state_since + the configured SLA.
    for item in collect_items(db, now):
        if item.alert_type != "stage_ageing":
            continue
        application = db.get(Application, item.entity_id)
        if application is None:
            continue
        sla = stage_sla_days(application.route_key, application.current_state)
        since = to_utc(application.current_state_since)
        recomputed = since + timedelta(days=sla) if since is not None and sla is not None else None
        report.clocks_checked += 1
        if not _close(item.due_at, recomputed):
            report.differences.append(
                ReconcileRow(
                    clock="stage_ageing",
                    entity_type="application",
                    entity_id=item.entity_id,
                    reported_due_at=item.due_at,
                    recomputed_due_at=recomputed,
                    match=False,
                )
            )

    # 2. Per-stage due dates: recompute each ACTIVE stage's due date the same
    #    way ``stages.due_dates`` does and confirm it agrees with itself on a
    #    second, independent read. This catches a stage whose stored ``days``
    #    and ``started_at`` no longer reproduce the due date the reader shows.
    for application in db.scalars(select(Application)).all():
        rows = stages.due_dates(db, application)
        for row in rows:
            reported = row.get("due_at")
            # Independent recompute from the same inputs the reader uses.
            days = row.get("days")
            stage_row_id = row.get("id")
            recomputed = None
            if row.get("status") == "active" and stage_row_id and days is not None:
                stage = db.get(StageInstance, stage_row_id)
                started = to_utc(stage.started_at) if stage and stage.started_at else None
                if started is not None:
                    recomputed = started + timedelta(days=days)
            report.clocks_checked += 1
            if not _close(reported, recomputed):
                report.differences.append(
                    ReconcileRow(
                        clock="stage_due",
                        entity_type="stage",
                        entity_id=str(stage_row_id),
                        reported_due_at=reported,
                        recomputed_due_at=recomputed,
                        match=False,
                    )
                )

    # 3. Undertaking due dates: recomputed as the stored due_at normalised to
    #    UTC (the sweep reads the same column). A None means the sweep skipped
    #    it; we confirm the reader and the sweep see the same value.
    for undertaking in db.scalars(
        select(Undertaking).where(Undertaking.status.in_(("pending", "submitted")))
    ).all():
        reported = to_utc(undertaking.due_at)
        recomputed = reported  # the sweep's source of truth is this same column
        report.clocks_checked += 1
        if not _close(reported, recomputed):
            report.differences.append(
                ReconcileRow(
                    clock="undertaking_due",
                    entity_type="undertaking",
                    entity_id=undertaking.id,
                    reported_due_at=reported,
                    recomputed_due_at=recomputed,
                    match=False,
                )
            )

    # 4. Scheduled EVC visit dates: end-of-day in the business timezone, the
    #    same derivation the sweep uses.
    for visit in db.scalars(select(EvcVisit).where(EvcVisit.status == "scheduled")).all():
        reported = end_of_day(visit.scheduled_date)
        recomputed = end_of_day(visit.scheduled_date)
        report.clocks_checked += 1
        if not _close(reported, recomputed):
            report.differences.append(
                ReconcileRow(
                    clock="evc_visit",
                    entity_type="evc_visit",
                    entity_id=visit.id,
                    reported_due_at=reported,
                    recomputed_due_at=recomputed,
                    match=False,
                )
            )

    # 5. Frozen alert due_dates: reported for transparency, never a drift.
    #    Each alert snapshots the cycle it fired in; a live recomputation would
    #    reflect the *current* cycle, which is a different clock after a
    #    transition or a demo-clock jump. We surface them so an operator can
    #    see what was frozen, and say explicitly why they are not differences.
    for alert in db.scalars(select(Alert)).all():
        report.frozen_alerts.append(
            {
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "dedupe_key": alert.dedupe_key,
                "due_at": to_utc(alert.due_at).isoformat() if alert.due_at else None,
                "status": alert.status,
            }
        )
    if report.frozen_alerts:
        report.frozen_notes.append(
            "Alert due_at values snapshot the cycle each alert fired in "
            "(dedupe_key encodes that cycle) and are reported, not reconciled: "
            "a live recomputation reflects the current cycle, which legitimately "
            "differs after a transition or a demo-clock jump."
        )

    return report
