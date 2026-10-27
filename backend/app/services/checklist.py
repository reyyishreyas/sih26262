"""Annexure-2 document checklist beside the uploaded files (Plan 4.2, FR-13).

PRD FR-13 (line 185): *"Generate checklist from category's Annexure-2 list
beside uploaded docs"*. The checklist is advisory presentation only (DEC-0003):
it shows which documents the category's (Unverified) Annexure-2 list names and
which of them this case has uploaded. It never blocks, returns or rejects
anything — the workflow gate is unchanged.

Three honesty rules the implementation keeps:

1. **The item lists are data** (``rules/annexure_2.json``), one entry per
   Table 2.3 category. Only the Change of Site list has items today, taken
   from the recorded research (``things.md`` §1, APH printed pages); every
   other category ships an empty list with an explicit "pending" note. An
   empty list is rendered as *needs review — list not transcribed*, never as
   "nothing required". PRD §19 Q8 leaves the load order open.
2. **A case whose Table 2.3 categories are not recorded answers "needs
   review"**, not an empty all-clear. Nothing in the product creates
   ``ApplicationItem`` rows yet (application creation takes a free-text
   category), so this is the normal state of a seeded case — said out loud
   rather than papered over.
3. **Presence is not validity.** An uploaded (non-rejected) document marks an
   item *uploaded*; whether it is genuine, signed or sufficient is the
   scrutiny officer's job (and the compliance rules'), never this widget's.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, ApplicationItem, Document
from . import policy
from .routing import category as table_2_3_category


def _config() -> dict[str, Any]:
    return policy.annexure_2_policy()


def category_items(category_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The checklist items configured for one Table 2.3 category.

    Raises ``KeyError`` rather than answering with a default: an unknown
    category must reach a human as "no list known", never as an empty list
    that reads as "nothing required".
    """
    table_2_3_category(category_id)  # raises KeyError for unknown ids
    entry = _config().get("categories", {}).get(category_id)
    if entry is None:
        raise KeyError(f"annexure_2.json has no entry for category {category_id!r}")
    return list(entry.get("items", [])), entry


def _uploaded_doc_types(db: Session, application_id: str) -> set[str]:
    """Doc types this case has uploaded, ignoring rejected documents.

    A rejected document is one an officer struck off; it does not satisfy a
    checklist line. Version handling is the document service's job — for
    presence, any surviving version counts.
    """
    rows = db.scalars(
        select(Document.doc_type).where(
            Document.application_id == application_id,
            Document.status != "rejected",
        )
    ).all()
    return set(rows)


def case_checklist(db: Session, application: Application) -> dict[str, Any]:
    """The advisory checklist for one case, computed on read.

    Nothing is stored: the answer is the configured list joined against the
    documents that exist right now, so it can never go stale.
    """
    config = _config()
    item_rows = db.scalars(
        select(ApplicationItem).where(
            ApplicationItem.application_id == application.id
        )
    ).all()

    if not item_rows:
        # No Table 2.3 category is recorded on this case (nothing creates
        # ApplicationItem rows yet). That is missing data — "needs review",
        # never a guessed checklist and never an empty all-clear.
        return {
            "status": "needs_review",
            "placeholder": config.get("placeholder", False),
            "source": config.get("source"),
            "note": config.get("no_category_note"),
            "categories": [],
            "items": [],
        }

    uploaded = _uploaded_doc_types(db, application.id)
    categories: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    pending_anywhere = False

    for row in sorted(item_rows, key=lambda r: r.category_id):
        try:
            category_items_config, entry = category_items(row.category_id)
        except KeyError:
            # A recorded category the Table 2.3 no longer knows (or a corrupt
            # row) is missing data — surface it as needs review, never a 500
            # and never as an empty "nothing required" list.
            pending_anywhere = True
            categories.append(
                {
                    "category_id": row.category_id,
                    "category": row.category_id,
                    "status": "needs_review",
                    "note": (
                        "This case records a category the routing table does "
                        "not recognise — no checklist can be generated for it. "
                        "Needs review."
                    ),
                    "uploaded": 0,
                    "total": 0,
                }
            )
            continue
        category_label = table_2_3_category(row.category_id).get(
            "category", row.category_id
        )
        if not category_items_config:
            # The category is known but its Annexure-2 list has not been
            # transcribed: say so per category rather than implying completeness.
            pending_anywhere = True
            categories.append(
                {
                    "category_id": row.category_id,
                    "category": category_label,
                    "status": "needs_review",
                    "note": entry.get("pending_note"),
                    "uploaded": 0,
                    "total": 0,
                }
            )
            continue

        category_uploaded = 0
        for item in category_items_config:
            doc_types = list(item.get("doc_types", []))
            present = any(doc in uploaded for doc in doc_types)
            category_uploaded += 1 if present else 0
            items.append(
                {
                    "category_id": row.category_id,
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "doc_types": doc_types,
                    "status": "uploaded" if present else "missing",
                    "source": item.get("source"),
                    "note": item.get("note"),
                }
            )
        categories.append(
            {
                "category_id": row.category_id,
                "category": category_label,
                "status": "complete"
                if category_uploaded == len(category_items_config)
                else "incomplete",
                "note": entry.get("note"),
                "uploaded": category_uploaded,
                "total": len(category_items_config),
            }
        )

    if pending_anywhere:
        overall = "needs_review"
    elif any(entry["status"] == "missing" for entry in items):
        overall = "incomplete"
    else:
        overall = "complete"

    return {
        "status": overall,
        "placeholder": config.get("placeholder", False),
        "source": config.get("source"),
        "note": config.get("note"),
        "categories": categories,
        "items": items,
    }
