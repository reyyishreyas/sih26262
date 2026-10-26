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


# ------------------------------------------- FR-03 blocked-application flags
#
# PRD FR-03 (cl. 2.21f, 2.16.1a, 2.3.1, 2.6e, 2.27): flag five kinds of
# blocked application. PRD §7: the officer "clears/holds each flag". These
# functions are the *evaluation* half — a pure, three-valued read over
# configuration + recorded case data. Deciding (clear/hold) is the audited
# endpoint in ``api/readiness.py``; evaluation itself writes nothing and
# gates nothing (DEC-0003, PRD §0).

# Operators a config condition may use. A config typo on any other raises
# (fail loudly) rather than silently answering "needs_review" for the wrong
# reason — and the config-contract test pins the shipped rules to this set.
_CONDITION_OPERATORS = ("equals", "contains", "gte")


def blocked_flags_policy() -> dict[str, Any]:
    """The ``blocked_flags`` section of ``rules/readiness_policy.json``.

    Raises KeyError when missing so a deleted rule block fails loudly
    instead of the endpoint answering "no flags exist".
    """
    section = readiness_policy().get("blocked_flags")
    if not section:
        raise KeyError(
            "readiness_policy.json has no 'blocked_flags' rule block — the "
            "FR-03 flag rules are missing from configuration"
        )
    return dict(section)


def decision_vocabulary() -> tuple[str, ...]:
    """The officer decisions PRD §7 allows: cleared | held (from config)."""
    return tuple(blocked_flags_policy().get("decisions", ()))


def _build_context(application: Any) -> dict[str, Any]:
    """The case data that is actually recorded, as evaluation inputs.

    Only fields this repo genuinely stores appear here. A missing key is
    therefore *unknown data*, never a false value — in particular
    ``application.category_ids`` is omitted entirely when a case carries no
    Table 2.3 items (absent items are unknown, not "not an intake increase";
    same precedent as ``routing.unmet_prerequisites``).
    """
    context: dict[str, Any] = {
        "application.category": application.category,
        "application.route_key": application.route_key,
        "application.cycle": application.cycle,
    }
    items = list(application.items)
    if items:
        context["application.category_ids"] = {item.category_id for item in items}
    return context


def _conjunct_holds(conjunct: dict[str, Any], value: Any) -> bool:
    if "equals" in conjunct:
        holds = value == conjunct["equals"]
    elif "contains" in conjunct:
        if not hasattr(value, "__contains__"):
            raise ValueError(
                f"'contains' cannot be evaluated against {type(value).__name__} "
                f"for input {conjunct['field']!r}"
            )
        holds = conjunct["contains"] in value
    elif "gte" in conjunct:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"'gte' cannot be evaluated against {type(value).__name__} "
                f"for input {conjunct['field']!r}"
            )
        holds = value >= conjunct["gte"]
    else:
        raise ValueError(
            f"unsupported condition operator on {conjunct['field']!r}: "
            f"{sorted(set(conjunct) - {'field'})} — expected one of "
            f"{list(_CONDITION_OPERATORS)}"
        )
    return bool(holds)


def _evaluate_condition(
    condition: list[dict[str, Any]], context: dict[str, Any]
) -> tuple[bool | None, str]:
    """Three-valued AND over the rule's conditions.

    Returns ``(True, reason)`` only when every condition input is recorded
    and holds; ``(False, reason)`` when a *recorded* input provably fails a
    condition — the rule then cannot apply whatever the unknowns are;
    ``(None, reason)`` when nothing decides and at least one input is not
    recorded. All conditions are scanned before deciding, so one provable
    failure is not masked by an earlier unknown.
    """
    if not condition:
        return None, "the rule declares no condition to evaluate"
    unrecorded: list[str] = []
    for conjunct in condition:
        field = conjunct["field"]
        if field not in context:
            unrecorded.append(field)
            continue
        if not _conjunct_holds(conjunct, context[field]):
            return False, f"recorded input {field!r} does not satisfy the rule"
    if unrecorded:
        return None, "inputs not recorded: " + ", ".join(unrecorded)
    return True, "every required input is recorded and satisfies the rule"


def evaluate_blocked_flags(
    application: Any,
    *,
    cfg: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate the five FR-03 flags against one case — a pure read.

    Returns one dict per configured rule: the rule's identity and citation
    (``flag_id``/``rule``/``clause``/``source``/``status``/``advisory_only``),
    its three-valued ``evaluation`` (``flagged`` | ``clear`` | ``needs_review``)
    with a human ``reason``, the declared ``missing_inputs``, and a
    ``decision`` slot that is always ``None`` here — an officer's decision is
    merged in by the endpoint, never invented by evaluation. ``state`` is the
    evaluation until an officer decides.

    With the shipped configuration every case evaluates to ``needs_review``
    on four of the five rules (their inputs are not modelled); bf-04 alone
    can answer ``clear`` when the case carries Table 2.3 items and none of
    them is the intake-increase category. That is the honest state, not a
    limitation to paper over.
    """
    section = dict(cfg) if cfg is not None else blocked_flags_policy()
    ctx = _build_context(application) if context is None else dict(context)

    rows: list[dict[str, Any]] = []
    for rule in section.get("flags", []):
        holds, reason = _evaluate_condition(rule.get("condition", []), ctx)
        evaluation = (
            "flagged" if holds else "clear" if holds is False else "needs_review"
        )
        missing = [
            entry["field"]
            for entry in rule.get("inputs", [])
            if entry["field"] not in ctx
        ]
        rows.append(
            {
                "flag_id": rule["flag_id"],
                "rule": rule["rule"],
                "clause": rule["clause"],
                "source": rule["source"],
                "status": rule.get("status", "unverified"),
                "advisory_only": bool(rule.get("advisory_only", True)),
                "evaluation": evaluation,
                "reason": reason,
                "missing_inputs": missing,
                "decision": None,
                "decided_by": None,
                "decided_at": None,
                "note": None,
                "state": evaluation,
            }
        )
    return rows
