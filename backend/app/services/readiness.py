"""Readiness cut-off check: tag for next AY, never reject (Phase 2.2).

PRD FR-02 (P0): "Reject from processing and tag for next AY any
application submitted/paid after cut-off" (APH cl. 2.2, 2.22), and §6
routing rule 7: "applications after the Public Notice cut-off are queued
for the next Academic Year."

The plan (2.2) deliberately implements only the **tag** half — "cut-off
check → tag next AY, **never reject**" — because PRD §0 says Unverified
rules "never block, return or reject an application". So this check:

- is advisory and pure: it returns what it found and the tag a caller
  *may* apply; it changes no state, writes nothing, and has no reject path
  (Master Prompt §2 rule 3);
- answers ``needs_review`` whenever the cut-off date or the submission
  time is not recorded — never a guessed in-window pass (rule 4). The
  cut-off dates live in ``calendars.json`` and were shipped **empty**
  (IMPL-0016), so today every real submission is ``needs_review`` until a
  human records an official Public Notice date;
- reads the action (and ``reject: false``) from
  ``rules/readiness_policy.json``, so the rule is configuration, not code.

Persisting the tag onto a case (and an officer clearing/holding it) is
task 2.3's flag flow, not this check.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import working_calendar
from .policy import readiness_policy

# The only statuses this check may ever return. Deliberately contains no
# "rejected"/"blocked": FR-02's reject half is not implemented (never reject).
_STATUS_VOCABULARY = ("within_window", "after_cutoff", "needs_review")


def cut_off_policy() -> dict[str, Any]:
    """The cut-off rule from ``rules/readiness_policy.json``.

    Raises KeyError when the config is missing or empty so a deleted rule
    fails loudly instead of silently answering "no cut-off applies".
    """
    section = readiness_policy().get("cut_off")
    if not section:
        raise KeyError(
            "readiness_policy.json has no 'cut_off' rule — the intake "
            "cut-off rule is missing from configuration"
        )
    return dict(section)


def cut_off_check(
    submitted_at: datetime | None,
    *,
    calendars_cfg: dict[str, Any] | None = None,
    policy_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Is this submission after the Public Notice cut-off?

    Returns a dict with ``status`` (one of ``within_window``,
    ``after_cutoff``, ``needs_review``), the ``cut_off`` date and
    ``submitted_on`` business date when known, the ``tag`` to apply when
    ``after_cutoff`` (else None), a human ``reason``, and ``source`` /
    ``advisory_only`` markers.

    **Never rejects and never blocks.** After the cut-off it only *names*
    the configured queue-for-next-AY tag; applying that tag to a case is a
    separate, audited act (task 2.3), not something this function does.

    Uncertainty is evaluated first-class: no recorded cut-off for the
    submission's year, or no submission time at all, both answer
    ``needs_review`` (Master Prompt §2 rule 4).

    The submission instant is converted to a business date in IST via
    ``working_calendar.business_date`` (naive read as UTC), then the
    cut-off is looked up **for that calendar year** — a year with no
    recorded cut-off is ``needs_review``, never "no cut-off applies".
    """
    policy = dict(policy_cfg) if policy_cfg is not None else cut_off_policy()
    action = policy.get("action_on_after_cutoff")
    source = policy.get("source", "md/1_PRD.md FR-02 (APH cl. 2.2, 2.22)")

    base: dict[str, Any] = {
        "advisory_only": True,
        "source": source,
        "action": action,
        "cut_off": None,
        "submitted_on": None,
        "tag": None,
    }

    if submitted_at is None:
        # Cannot tell a draft from a record missing its time — do not assume
        # it is safely in-window (rule 4).
        return {
            **base,
            "status": "needs_review",
            "reason": "no submission time recorded",
        }

    submitted_on = working_calendar.business_date(submitted_at)
    year = submitted_on.year
    cut_off = working_calendar.public_notice_cutoff(year, cfg=calendars_cfg)

    if cut_off is None:
        # The honest state today: calendars.json ships no year (IMPL-0016).
        return {
            **base,
            "submitted_on": submitted_on,
            "status": "needs_review",
            "reason": f"no Public Notice cut-off recorded for {year}",
        }

    if submitted_on <= cut_off:
        return {
            **base,
            "submitted_on": submitted_on,
            "cut_off": cut_off,
            "status": "within_window",
            "reason": "submitted on or before the cut-off",
        }

    # After the cut-off: name the queue tag. `reject` stays false in config;
    # flipping it on for an Unverified cut-off is a human approval gate.
    return {
        **base,
        "submitted_on": submitted_on,
        "cut_off": cut_off,
        "status": "after_cutoff",
        "tag": action,
        "reason": "submitted after the Public Notice cut-off",
    }


def statuses() -> tuple[str, ...]:
    """The complete status vocabulary — asserted by tests so a new status
    cannot be added without noticing it here."""
    return _STATUS_VOCABULARY
