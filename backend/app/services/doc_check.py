"""RULE-DOC-01 document pre-check: required docs, Affidavit 2, DSC (4.5, FR-06).

PRD FR-06 (line 183): *"Confirm Affidavit 2 and DSC-signed docs; list missing
items as deficiency draft"*, APH cl. 2.3.4 as the PRD cites it. The PRD's
rule table (line 145) records RULE-DOC-01's outcome as a **Deficiency
candidate**, and ``md/rules.json`` spells the rule out with a four-value
outcome vocabulary, ``status: proposed_unverified`` and *"human_review:
Required before issuing a formal deficiency."* This module evaluates that
rule as configuration plus pure lookups:

- **the inventory leg** is the Phase 4.2 Annexure-2 checklist (only a
  transcribed category can answer; untranscribed/unknown is *review
  required*, never an empty all-clear);
- **the Affidavit 2 leg** maps FR-06's named document onto the prototype's
  single ``affidavit`` upload type — a labelled placeholder, since Affidavit
  1/2/3 cannot be told apart here;
- **the DSC leg** is a stub (``md/2_ARCHITECTURE.md`` line 117), so no
  signature data exists to evaluate: it can only ever answer *needs review*.

Four honesty rules the implementation keeps:

1. **The outcome vocabulary is md/rules.json's own** — the four keys and
   their labels are read from config, and a test pins them to the spec file
   so the two can never drift.
2. **Nothing here issues, gates or moves anything** (DEC-0003). The read
   proposes *candidates*; staging them as ``draft`` deficiencies is a
   separate, audited officer act — and a draft is never visible to the
   institution or counted in any issued report (Phase 4.4).
3. **An unverified leg never produces a pass.** The DSC leg answers
   ``needs_review`` on every evaluation, so the response always carries
   ``needs_review: true`` beside the outcome and the human-review line.
4. **A candidate that a live deficiency already covers is named, not
   duplicated** — re-running the check (or the staging POST) is idempotent
   while a draft/open/addressed row exists for the same line; only a
   *closed* row lets the line be raised again (a past acceptance must not
   hide a document that has gone missing since).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Deficiency, Document
from . import checklist as checklist_service
from .policy import doc_check_policy

RULE_ID = "RULE-DOC-01"
# A deficiency row in one of these states still covers its line.
LIVE_STATUSES = ("draft", "open", "addressed")


def config() -> dict[str, Any]:
    """The raw rule configuration (``rules/doc_check_policy.json``)."""
    return doc_check_policy()


def outcome_labels() -> dict[str, str]:
    """The md/rules.json outcome vocabulary, keyed by outcome code."""
    return dict(config()["outcomes"])


def _uploaded_doc_types(db: Session, application_id: str) -> set[str]:
    """Doc types this case has uploaded, ignoring rejected documents.

    Same presence rule as the 4.2 checklist: a rejected document never
    satisfies a line.
    """
    return set(
        db.scalars(
            select(Document.doc_type).where(
                Document.application_id == application_id,
                Document.status != "rejected",
            )
        ).all()
    )


def _live_by_field(db: Session, application_id: str) -> dict[str, Deficiency]:
    """Live (draft/open/addressed) deficiency rows keyed by their line key."""
    rows = db.scalars(
        select(Deficiency).where(
            Deficiency.application_id == application_id,
            Deficiency.status.in_(LIVE_STATUSES),
            Deficiency.field_name.is_not(None),
        )
    ).all()
    return {row.field_name: row for row in rows}


def evaluate(db: Session, application: Application) -> dict[str, Any]:
    """Evaluate RULE-DOC-01 for one case, computed on read.

    Nothing is stored: the answer joins the configured rule against the
    documents that exist right now, so it can never go stale.
    """
    cfg = config()
    labels = outcome_labels()
    legs: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []

    # --- Leg 1: the required-document inventory (Annexure-2, Phase 4.2).
    case_list = checklist_service.case_checklist(db, application)
    if not case_list["items"]:
        # No recorded category, an unrecognised one, or an untranscribed
        # list: missing data says "needs review", never "nothing required".
        inventory_known = False
        inventory_leg = {
            "leg": "required_documents",
            "status": "needs_review",
            "needs_review": True,
            "note": case_list.get("note") or cfg["inventory"]["note"],
            "source": cfg["inventory"].get("source"),
        }
    else:
        inventory_known = True
        not_uploaded = [i for i in case_list["items"] if i["status"] == "missing"]
        for item in not_uploaded:
            missing_items.append(
                {
                    "field_name": f"annexure:{item['category_id']}:{item['item_id']}",
                    "title": item["title"],
                    "category_id": item["category_id"],
                    "item_id": item["item_id"],
                    "doc_types": list(item.get("doc_types", [])),
                    "explanation": (
                        f"Required document not uploaded: {item['title']}."
                    ),
                    "corrective_action": f"Upload {item['title']}.",
                    "source": item.get("source"),
                }
            )
        inventory_leg = {
            "leg": "required_documents",
            "status": "missing" if not_uploaded else "satisfied",
            "needs_review": False,
            "note": case_list.get("note"),
            "source": cfg["inventory"].get("source"),
            "missing_count": len(not_uploaded),
        }
    legs.append(inventory_leg)

    # --- Leg 2: Affidavit 2 (FR-06's own named document).
    affidavit_cfg = cfg["affidavit_2"]
    affidavit_types = list(affidavit_cfg["doc_types"])
    affidavit_present = any(
        doc_type in _uploaded_doc_types(db, application.id)
        for doc_type in affidavit_types
    )
    if affidavit_present:
        legs.append(
            {
                "leg": "affidavit_2",
                "status": "satisfied",
                # Present is not the same as *confirmed to be Affidavit 2*:
                # the upload vocabulary cannot number the affidavit.
                "needs_review": True,
                "confirmed": False,
                "note": affidavit_cfg["note"],
            }
        )
    else:
        legs.append(
            {
                "leg": "affidavit_2",
                "status": "missing",
                "needs_review": False,
                "confirmed": False,
                "note": affidavit_cfg["note"],
            }
        )
        missing_items.append(
            {
                "field_name": "affidavit_2",
                "title": "Affidavit 2",
                "category_id": None,
                "item_id": None,
                "doc_types": affidavit_types,
                "explanation": (
                    "No affidavit is uploaded for this application "
                    "(RULE-DOC-01 / FR-06 requires Affidavit 2)."
                ),
                "corrective_action": "Upload Affidavit 2.",
                "source": cfg["source"],
            }
        )

    # --- Leg 3: the DSC signature — a stub, so it can only be needs review.
    dsc_cfg = cfg["dsc"]
    dsc_checkable = bool(dsc_cfg.get("checkable", False))
    legs.append(
        {
            "leg": "dsc_signature",
            "status": (
                "satisfied" if dsc_checkable else dsc_cfg["status_when_unavailable"]
            ),
            "needs_review": not dsc_checkable,
            "checkable": dsc_checkable,
            "note": dsc_cfg["note"],
        }
    )

    # --- The outcome, in md/rules.json's own vocabulary and the configured
    # precedence (a concrete missing document beats an unknown inventory).
    if missing_items:
        outcome = "one_or_more_required_documents_missing"
    elif not inventory_known:
        outcome = "checklist_unknown_or_route_unverified"
    else:
        outcome = "all_required_documents_present"

    live = _live_by_field(db, application.id)
    for candidate in missing_items:
        existing = live.get(candidate["field_name"])
        candidate["existing_deficiency"] = (
            {"id": existing.id, "status": existing.status} if existing else None
        )

    return {
        "application_id": application.id,
        "rule_id": RULE_ID,
        "rule_status": cfg["status"],
        "version": cfg["version"],
        "outcome": outcome,
        "outcome_label": labels[outcome],
        # True whenever any leg is unverifiable — including on a "PRE-CHECK
        # PASSED" outcome, where it means "presence only, DSC not confirmed".
        "needs_review": any(leg.get("needs_review") for leg in legs),
        "human_review": cfg["human_review"],
        "legs": legs,
        "missing_items": missing_items,
        "placeholder": cfg.get("placeholder", False),
        "advisory_only": cfg.get("advisory_only", True),
        "source": cfg.get("source"),
        "note": cfg.get("note"),
    }


def stage_drafts(
    db: Session, application: Application, actor_id: str
) -> dict[str, Any]:
    """Stage the check's uncovered candidates as DRAFT deficiencies.

    The officer's deliberate act behind FR-06's "list missing items as
    deficiency draft": drafts are officer-only working notes — never
    issued, never shown to the institution, never part of an issued report
    (Phase 4.4) — and staging never moves or gates the case.

    Idempotent by line key: a candidate already covered by a live
    (draft/open/addressed) row is skipped and reported; a *closed* row does
    not cover the line any more, so a document that has gone missing since
    an earlier acceptance can be raised again (history stays in the audit
    trail and the closed row itself).
    """
    report = evaluate(db, application)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in report["missing_items"]:
        covered = candidate["existing_deficiency"]
        if covered is not None:
            skipped.append(
                {
                    "field_name": candidate["field_name"],
                    "title": candidate["title"],
                    "deficiency_id": covered["id"],
                    "status": covered["status"],
                }
            )
            continue
        row = Deficiency(
            application_id=application.id,
            category="document_deficiency",
            rule_key=RULE_ID,
            field_name=candidate["field_name"],
            explanation=candidate["explanation"],
            corrective_action=candidate["corrective_action"],
            status="draft",
            created_by=actor_id,
        )
        db.add(row)
        db.flush()
        created.append(
            {
                "field_name": candidate["field_name"],
                "title": candidate["title"],
                "deficiency_id": row.id,
                "status": row.status,
            }
        )

    return {
        "created": created,
        "skipped": skipped,
        "outcome": report["outcome"],
        "outcome_label": report["outcome_label"],
        "needs_review": report["needs_review"],
    }
