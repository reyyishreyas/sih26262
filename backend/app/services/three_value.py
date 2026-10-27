"""The three-value model: Extraction / Claim / Master (FR-41, RULE-EDIT-01).

PRD §8 line 140: *every field keeps all three* — **Extraction Value**
(what the document says), **Claim Value** (what the institution
confirms/edits), **Master Record Value** (AICTE's record). Rules run on
the Extraction Value only; an edit is flagged, both values kept, a reason
required, and **an edit can never clear a failed rule**. Wording stays
neutral ("edited after extraction").

RULE-EDIT-01 (`md/rules.json`) says the same from the data side:
*"Preserve original extraction and store the correction as a separate
value with actor, time, reason, and version. Do not silently overwrite
the source extraction."*

What this module guarantees:

1. **The extraction value is never written here.** A claim lands in its
   own columns (`claim_value`, `claim_reason`, `claimed_by`,
   `claimed_at`); `field.value` is read and left alone — which is also
   why an edit can never clear a failed rule: the rule engine's snapshot
   is built from the extraction columns only.
2. **An edit without a reason is refused** with a 400 and *nothing* is
   recorded — no half-correction, no silent overwrite (FR-41: "edits
   flagged with reason").
3. **The Master Record Value stays unknown.** No master source is
   integrated (`md/rules.json`: *"if one is actually integrated"*), so
   it answers `None` with the caveat attached — never a guess, never a
   copy of the extraction pretending to be a record.
4. **RULE-EDIT-01 answers in the spec's vocabulary** (`continue` /
   `REVIEW REQUIRED`) and only ever about *provenance of the edit* — it
   is not a compliance verdict and never says pass/fail.

Nothing here approves, rejects, returns or blocks anything (DEC-0003):
the claim is data; officers still decide what a value means.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from ..models import ExtractedField
from .policy import three_value_policy


def config() -> dict[str, Any]:
    """The three-value policy (rules/three_value_policy.json)."""
    return three_value_policy()


def values(field: ExtractedField) -> dict[str, Any]:
    """The field's three slots, with honest absence for the unknown ones."""
    cfg = config()
    claim = field.claim_value
    edited = claim is not None and claim != field.value
    if claim is None:
        label = None
    elif edited:
        label = cfg["claim"]["edited_label"]
    else:
        label = cfg["claim"]["confirm_label"]
    return {
        "extraction": field.value,
        "claim": claim,
        # No trusted master source is integrated; unknown, never guessed.
        "master": None,
        "master_note": cfg["master_source"]["note"],
        "edited": edited,
        "label": label,
    }


def record_claim(
    field: ExtractedField,
    *,
    value: object,
    reason: str,
    actor_id: str,
    at: datetime,
) -> dict[str, Any]:
    """Records the institution's claim on a field — as a *separate* value.

    A claim equal to the extraction is a confirmation; a different one is
    an edit, and an edit requires a reason (400 with nothing recorded
    otherwise). The extraction value, the verification status and every
    provenance column are untouched.
    """
    cfg = config()
    clean_reason = (reason or "").strip() or None
    edited = value != field.value

    if edited and (clean_reason is None or len(clean_reason) < cfg["claim"]["reason_min_length"]):
        # Refused BEFORE anything is written: RULE-EDIT-01's
        # missing_required_reason_or_actor must not be creatable through
        # the API — the rule stays as the honesty net for other paths.
        raise HTTPException(
            400,
            "a reason is required when the claim differs from the extracted value",
        )

    field.claim_value = value
    field.claim_reason = clean_reason
    field.claimed_by = actor_id
    field.claimed_at = at

    return {
        "edited": edited,
        "note": (
            cfg["claim"]["edited_label"] if edited else cfg["claim"]["confirm_label"]
        ),
        "extraction_value": field.value,
        "claim_value": value,
    }


def rule_edit01(field: ExtractedField) -> dict[str, Any]:
    """RULE-EDIT-01: is a correction fully provenanced? (advisory).

    Applicable only when a claim exists **and differs** from the
    extraction — a confirmation is not a correction, and a field with no
    claim has nothing to prove. Answers in `md/rules.json`'s own outcome
    vocabulary (pinned to the spec file by a test):

    * reason + actor present ⇒ ``complete_provenance`` → "continue";
    * either missing ⇒ ``missing_required_reason_or_actor`` →
      "REVIEW REQUIRED".

    "continue" is about provenance — it never means the application
    passed, cleared or was approved of anything, and this result feeds no
    transition (DEC-0003).
    """
    cfg = config()
    claim = field.claim_value
    base: dict[str, Any] = {
        "rule_id": "RULE-EDIT-01",
        "applicable": False,
        "outcome": None,
        "label": None,
        "extraction_value": field.value,
        "claim_value": claim,
        "has_reason": bool(field.claim_reason),
        "has_actor": bool(field.claimed_by),
        "human_review": None,
    }
    if claim is None or claim == field.value:
        # No claim, or a confirmation: not a correction, so the rule does
        # not apply (md/rules.json applicability: "when a user corrects
        # or overrides an extracted field").
        return base

    base["applicable"] = True
    if field.claim_reason and field.claimed_by:
        outcome = "complete_provenance"
        human_review = None
    else:
        outcome = "missing_required_reason_or_actor"
        human_review = cfg["human_review"]
    base["outcome"] = outcome
    base["label"] = cfg["outcomes"][outcome]
    base["human_review"] = human_review
    return base
