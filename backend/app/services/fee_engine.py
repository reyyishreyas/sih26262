"""Fee lookup and guarded payment gate evaluation (FR-21, FR-25).

Candidate amounts live in ``rules/fee_table.json``. Until an authorized,
source-backed review marks the table Verified, this service returns no due
amount and never blocks an action. Institution type is not currently modeled,
so callers must pass it explicitly; unknown values stay unresolved.
"""

from __future__ import annotations

from typing import Any

from .policy import fee_table_policy

FEE_EVENTS = frozenset({"additional_evc", "additional_scrutiny_shc_sac"})


def config() -> dict[str, Any]:
    """Return a copy of fee configuration so callers cannot mutate the cache."""
    import copy

    return copy.deepcopy(fee_table_policy())


def evaluate(
    event: str,
    *,
    institution_class: str | None,
    visit_mode: str | None = None,
    payment_verified: bool = False,
) -> dict[str, Any]:
    """Resolve one configured fee without inferring a payment or authority.

    Only a table marked Verified with a named reviewer, edition and clause
    can produce an amount or a payment gate. Candidate values remain clearly
    separate while the table is unverified.
    """
    table = config()
    if event not in FEE_EVENTS:
        raise ValueError(f"unknown fee event: {event}")
    event_config = table.get("fees", {}).get(event, {})
    class_key = {
        "government": "government",
        "other": "other",
    }.get(institution_class or "")
    candidates = event_config.get("candidate_amounts_inr", {})
    candidate = candidates.get(class_key) if class_key else None
    if event == "additional_evc":
        candidate = candidate.get(visit_mode) if isinstance(candidate, dict) else None

    verification = table.get("verification", {})
    verified = (
        table.get("status") == "verified"
        and not table.get("placeholder", True)
        and bool(verification.get("source_id"))
        and bool(verification.get("reviewer"))
        and bool(verification.get("edition"))
        and bool(verification.get("clause"))
        and bool(verification.get("verified_at"))
    )
    amount = candidate if verified and isinstance(candidate, int) else None
    payment_required = amount is not None
    return {
        "event": event,
        "status": "verified" if verified else "unverified",
        "institution_class": class_key,
        "visit_mode": visit_mode if event == "additional_evc" else None,
        "amount_inr": amount,
        "candidate_amount_inr": candidate if not verified else None,
        "payment_required": payment_required,
        "payment_verified": bool(payment_verified),
        "may_proceed": not payment_required or payment_verified,
        "blocking": payment_required and not payment_verified,
        "placeholder": not verified,
        "advisory_only": not verified,
        "note": table.get("note"),
    }
