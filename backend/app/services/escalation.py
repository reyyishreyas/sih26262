"""Escalation chain: who a missed or nearly-missed clock is escalated to.

Plan 3.4 (AGENT-02) implements the PRD §11 escalation ladder as configuration
plus pure lookups, so nothing about "who gets told, and when" is hard-coded.

PRD §11 (lines 274-293) defines two things this module models:

1. **The chain** — L0 assignee → L1 Regional officer → L2 Regulation Bureau
   → L3 competent authority. The *designated authority* per level/Region is
   an open question (§19 Q5), so ``rules/escalation_chain.json`` maps ROLES
   (not named people) as a clearly-labelled placeholder, and L3 — which has
   no matching role in the prototype at all — is deliberately ``unmapped``:
   it resolves to no recipients rather than inventing an authority.
2. **The triggers** — the near-limit percentage ladder (70/90/100/125% of
   the stage limit) and the "unassigned in queue" rules (Regional after 1
   working day, L2 after 3). PRD line 12 records that these operational
   thresholds are *project proposals, not AICTE rules*, so they ship as
   Unverified advisory configuration.

Everything here is advisory and side-effect free (DEC-0003): these functions
compute a level and a recipient list for display, and by themselves never
gate, move or reject a case. The percentages are always relative to the
configured stage limit (``rules/stage_limits.json`` — the same day counts the
ageing sweep uses), never a second clock; the working-day counts use the
configured calendar (``rules/calendars.json``), never a hard-coded weekend.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..core.clock import to_utc
from ..models import Application, Institution
from . import alert_service, policy, working_calendar
from .deadline_service import TERMINAL_STATES
from .policy import escalation_chain_policy


def chain() -> list[dict[str, Any]]:
    """The ordered L0..L3 escalation chain (config, placeholder)."""
    return list(escalation_chain_policy().get("chain", []))


def level_for_percentage(elapsed_days: int, limit_days: int | None) -> str | None:
    """The highest escalation level reached at a share of the stage limit.

    ``limit_days`` comes from ``stage_limits.json`` (via
    ``policy.stage_sla_days``). A missing/zero limit answers None — there is
    no clock to run a percentage against, so we never guess one. The ladder
    (70/90/100/125%) is PRD §11 line 278 and is advisory (project proposal,
    PRD line 12); the highest crossed threshold wins.
    """
    if not limit_days or limit_days <= 0:
        return None
    percent = elapsed_days / limit_days * 100
    level: str | None = None
    ladder = sorted(
        escalation_chain_policy().get("percentage_thresholds", []),
        key=lambda entry: entry["percent"],
    )
    for entry in ladder:
        if percent >= entry["percent"]:
            level = entry["level"]
    return level


def unassigned_level(working_days: int) -> str | None:
    """The highest level a case unassigned in the queue has reached.

    ``working_days`` is measured with the configured calendar (see
    ``working_days_between``). The 1-day → L1 and 3-day → L2 rules are PRD
    §11 line 280 and are advisory (project proposal, PRD line 12).
    """
    level: str | None = None
    rules = sorted(
        escalation_chain_policy().get("unassigned_in_queue", []),
        key=lambda entry: entry["after_working_days"],
    )
    for entry in rules:
        if working_days >= entry["after_working_days"]:
            # `notifies` is ordered lowest→highest; the last is the rung reached.
            level = entry["notifies"][-1]
    return level


def working_days_between(
    start: date, end: date, cfg: dict[str, Any] | None = None
) -> int:
    """Working days strictly after ``start`` up to and including ``end``.

    Uses the configured weekend/holiday calendar (``calendars.json``), never a
    hard-coded convention. ``end <= start`` is zero, not an error.
    """
    if end <= start:
        return 0
    count = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        if working_calendar.is_working_day(cursor, cfg):
            count += 1
    return count


def _entry_for(level: str) -> dict[str, Any] | None:
    return next(
        (entry for entry in chain() if entry["level"] == level),
        None,
    )


def recipients_for_level(
    db: Session, application: Application, level: str
) -> list[str]:
    """Resolve an escalation level to the user ids who sit at it.

    Resolution follows the level's configured ``recipient_kind``:

    - ``assignee`` (L0) → the case's own assigned officer.
    - ``regional_officer`` (L1) / ``supervisory_officer`` (L2) → users holding
      that role scoped to the institution's Region.
    - ``unmapped`` (L3) → nobody. No competent-authority role exists in the
      prototype and §19 Q5 leaves it open, so this resolves to an empty list
      rather than inventing a person.

    An unknown level also resolves to nobody.
    """
    entry = _entry_for(level)
    if entry is None:
        return []
    kind = entry["recipient_kind"]
    if kind == "assignee":
        return [application.assigned_officer_id] if application.assigned_officer_id else []
    if kind == "unmapped":
        return []

    institution = db.get(Institution, application.institution_id)
    if institution is None:
        return []
    if kind == "regional_officer":
        return alert_service.regional_officers(db, institution.region_id)
    if kind == "supervisory_officer":
        return alert_service.supervisory_officers(db, institution.region_id)
    return []


def escalation_snapshot(
    db: Session, application: Application, now
) -> dict[str, Any]:
    """Advisory escalation view for one case, computed on read.

    Combines the two §11 triggers into one display record: how far the case
    is through its stage limit (percentage → level → recipients) and whether
    it has been sitting unassigned in the queue (working days → level). This
    is read-only — it moves no case, changes no state and writes nothing
    (DEC-0003); the sweep's alerts and the monitoring view are unchanged.
    """
    config = escalation_chain_policy()
    since = to_utc(application.current_state_since)
    days_in_stage = max(0, (now - since).days) if since else 0
    limit = policy.stage_sla_days(application.route_key, application.current_state)
    percent = round(days_in_stage / limit * 100) if limit else None
    level = level_for_percentage(days_in_stage, limit)
    recipients = recipients_for_level(db, application, level) if level else []

    in_queue = application.current_state not in TERMINAL_STATES
    unassigned = in_queue and application.assigned_officer_id is None
    unassigned_days = (
        working_days_between(since.date(), now.date()) if (unassigned and since) else 0
    )
    unassigned_to = unassigned_level(unassigned_days) if unassigned else None

    return {
        "status": config.get("status"),
        "placeholder": config.get("placeholder", False),
        "stage_limit_days": limit,
        "days_in_stage": days_in_stage,
        "percent_used": percent,
        "level": level,
        "recipients": recipients,
        "unassigned": unassigned,
        "unassigned_working_days": unassigned_days,
        "unassigned_level": unassigned_to,
    }
