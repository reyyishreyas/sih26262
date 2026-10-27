"""Scrutiny results: per checklist item and overall (Plan 4.3, FR-14).

PRD FR-14 (line 186): *"Result per checklist item and overall (Nil
Deficiency / Deficiency) with remarks"*, APH cl. 2.4. Phase 4.2 generates the
advisory Annexure-2 checklist; this service records the **scrutiny officer's
own verdict** on each of its lines and overall, both with remarks.

Three honesty rules the implementation keeps:

1. **The vocabulary is configuration.** "nil_deficiency" / "deficiency" come
   from ``aa_gate.scrutiny_results`` (the PRD's own FR-14 wording, already
   carried by the FR-10 gate) — never invented here, never extended here.
2. **A result can only be recorded against a real checklist line.** The
   category must be one the case actually records, and the item must exist
   in that category's configured Annexure-2 list. Anything else is refused
   loudly (a result attached to a line that does not exist would be a wrong
   regulatory record), and an untranscribed list answers "needs review" —
   never an empty accept.
3. **The record cannot contradict itself.** An overall "nil_deficiency" is
   refused while any item result is "deficiency": Nil Deficiency means no
   deficiency anywhere, so accepting both would put a self-contradictory
   verdict in the audit chain. The reverse is allowed — overall "deficiency"
   with all items clean, because a deficiency may exist outside the
   checklist (compliance findings, document contents).

Recording is never a workflow action: it moves no case, gates nothing and
is a separate audited step from any transition (DEC-0003). The overall
result feeds the FR-10 "AA" gate advisory lookup, which likewise never
moves a case by itself.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..models import (
    Application,
    ApplicationItem,
    Deficiency,
    ScrutinyItemResult,
    ScrutinyOverallResult,
)
from . import checklist, routing


def result_vocabulary() -> dict[str, list[str]]:
    """The configured result vocabulary (FR-14's own wording, via FR-10's gate)."""
    return dict(routing.aa_gate()["scrutiny_results"])


def _allowed_results() -> set[str]:
    vocabulary = result_vocabulary()
    return set(vocabulary["clean"]) | set(vocabulary["negative"])


def _validate_result(result: str) -> None:
    allowed = _allowed_results()
    if result not in allowed:
        raise ValueError(
            f"unknown scrutiny result {result!r}; "
            f"the configured vocabulary is {sorted(allowed)}"
        )


def _recorded_category_ids(db: Session, application_id: str) -> set[str]:
    rows = db.scalars(
        select(ApplicationItem.category_id).where(
            ApplicationItem.application_id == application_id
        )
    ).all()
    return set(rows)


def record_item_result(
    db: Session,
    application: Application,
    *,
    category_id: str,
    item_id: str,
    result: str,
    remarks: str = "",
    actor_id: str,
) -> ScrutinyItemResult:
    """Record (or re-record) the officer's result for one checklist line.

    Raises ``ValueError`` for anything that must not be silently accepted:
    an unknown result value, a category the case does not record, or an item
    that is not in that category's configured list (including the
    untranscribed-list case, which is missing data, not an empty list).
    """
    _validate_result(result)
    if category_id not in _recorded_category_ids(db, application.id):
        raise ValueError(
            f"this case does not record Table 2.3 category {category_id!r} — "
            "no checklist line exists to record a result against (needs review)"
        )
    items, entry = checklist.category_items(category_id)  # KeyError → unknown id
    if not items:
        raise ValueError(
            f"the Annexure-2 list for category {category_id!r} is not "
            f"transcribed yet — {entry.get('pending_note')} "
            "(needs review; a result cannot be recorded against an unknown list)"
        )
    if item_id not in {item["item_id"] for item in items}:
        raise ValueError(
            f"unknown checklist item {item_id!r} for category {category_id!r}; "
            f"the configured list has {sorted(item['item_id'] for item in items)}"
        )

    row = db.scalars(
        select(ScrutinyItemResult).where(
            ScrutinyItemResult.application_id == application.id,
            ScrutinyItemResult.category_id == category_id,
            ScrutinyItemResult.item_id == item_id,
        )
    ).first()
    if row is None:
        row = ScrutinyItemResult(
            application_id=application.id,
            category_id=category_id,
            item_id=item_id,
            result=result,
            remarks=remarks,
            recorded_by=actor_id,
        )
        db.add(row)
    else:
        # Re-recording updates the row; the audit timeline keeps both
        # judgements (same contract as ReadinessFlag re-decisions).
        row.result = result
        row.remarks = remarks
        row.recorded_by = actor_id
        row.recorded_at = get_clock().now()
    db.flush()
    return row


def record_overall_result(
    db: Session,
    application: Application,
    *,
    result: str,
    remarks: str = "",
    actor_id: str,
) -> ScrutinyOverallResult:
    """Record (or re-record) the officer's OVERALL result for the case.

    Raises ``ValueError`` for an unknown result value, and for the
    self-contradiction: overall "nil_deficiency" while any recorded item
    result is "deficiency". Overall "deficiency" is always accepted — a
    deficiency may exist outside the Annexure-2 checklist.
    """
    _validate_result(result)
    vocabulary = result_vocabulary()
    if result in vocabulary["clean"]:
        contradicting = db.scalars(
            select(ScrutinyItemResult).where(
                ScrutinyItemResult.application_id == application.id,
                ScrutinyItemResult.result.in_(vocabulary["negative"]),
            )
        ).all()
        if contradicting:
            lines = sorted(
                f"{row.category_id}/{row.item_id}" for row in contradicting
            )
            raise ValueError(
                "overall 'nil_deficiency' contradicts recorded item result(s) "
                f"{lines} — Nil Deficiency means no deficiency anywhere; "
                "correct the item result(s) or record 'deficiency' overall"
            )

    row = db.scalars(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == application.id
        )
    ).first()
    if row is None:
        row = ScrutinyOverallResult(
            application_id=application.id,
            result=result,
            remarks=remarks,
            recorded_by=actor_id,
        )
        db.add(row)
    else:
        row.result = result
        row.remarks = remarks
        row.recorded_by = actor_id
        row.recorded_at = get_clock().now()
    db.flush()
    return row


def _serialise_item_row(row: ScrutinyItemResult) -> dict[str, Any]:
    return {
        "category_id": row.category_id,
        "item_id": row.item_id,
        "result": row.result,
        "remarks": row.remarks,
        "recorded_by": row.recorded_by,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
    }


def _serialise_overall_row(row: ScrutinyOverallResult) -> dict[str, Any]:
    return {
        "result": row.result,
        "remarks": row.remarks,
        "recorded_by": row.recorded_by,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
    }


def results_view(db: Session, application: Application) -> dict[str, Any]:
    """The read model: checklist lines joined with what the officer recorded.

    Computed on read (nothing here is stored by this function): every
    configured checklist line carries its recorded result or ``None``, plus
    counts, a derived overall answer and the FR-10 gate's advisory opinion.
    A recorded result whose item no longer exists in configuration is kept
    and flagged, never silently dropped — an officer's judgement must not
    vanish because a rule file changed.
    """
    board = checklist.case_checklist(db, application)
    item_rows = list(
        db.scalars(
            select(ScrutinyItemResult).where(
                ScrutinyItemResult.application_id == application.id
            )
        ).all()
    )
    overall_row = db.scalars(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == application.id
        )
    ).first()

    recorded = {
        (row.category_id, row.item_id): row for row in item_rows
    }
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in board["items"]:
        key = (entry["category_id"], entry["item_id"])
        seen.add(key)
        row = recorded.get(key)
        items.append(
            {
                "category_id": entry["category_id"],
                "item_id": entry["item_id"],
                "title": entry["title"],
                "result": row.result if row else None,
                "remarks": row.remarks if row else "",
                "recorded_by": row.recorded_by if row else None,
                "recorded_at": (
                    row.recorded_at.isoformat()
                    if row and row.recorded_at
                    else None
                ),
            }
        )
    orphaned = [
        _serialise_item_row(row)
        for key, row in sorted(recorded.items())
        if key not in seen
    ]

    vocabulary = result_vocabulary()
    configured_count = len(items)
    recorded_count = sum(1 for entry in items if entry["result"] is not None)
    deficiency_count = sum(
        1
        for entry in items
        if entry["result"] in vocabulary["negative"]
    )
    if configured_count == 0:
        derived: str | None = None
    elif deficiency_count > 0:
        derived = vocabulary["negative"][0]
    elif recorded_count == configured_count:
        derived = vocabulary["clean"][0]
    else:
        # Not every line decided yet — an undecided overall is never guessed.
        derived = None

    open_deficiencies = len(
        db.scalars(
            select(Deficiency.id).where(
                Deficiency.application_id == application.id,
                Deficiency.status.in_(("open", "addressed")),
            )
        ).all()
    )
    overall_result = overall_row.result if overall_row else None

    notes: list[str] = []
    if board["status"] == "needs_review":
        notes.append(
            board.get("note")
            or "The Annexure-2 checklist for this case needs review, so item "
            "results cannot be compared against a complete list."
        )
    if orphaned:
        notes.append(
            "Some recorded item result(s) no longer match the configured "
            "checklist — they are kept and shown, but the match needs "
            "review: "
            + ", ".join(
                f"{row['category_id']}/{row['item_id']}" for row in orphaned
            )
        )
    if (
        overall_result is not None
        and derived is not None
        and overall_result in vocabulary["clean"]
        and derived in vocabulary["negative"]
    ):
        # Only reachable if rows predate the consistency rule; surface it.
        notes.append(
            "The overall result disagrees with the recorded item results "
            "— needs review."
        )

    return {
        "placeholder": board.get("placeholder", False),
        "source": board.get("source"),
        "checklist_status": board["status"],
        "items": items,
        "orphaned_item_results": orphaned,
        "overall": _serialise_overall_row(overall_row) if overall_row else None,
        "counts": {
            "items_configured": configured_count,
            "items_recorded": recorded_count,
            "items_deficiency": deficiency_count,
            "open_deficiencies": open_deficiencies,
        },
        "derived_overall": derived,
        # FR-10's advisory gate, composed with this case's recorded result.
        # It answers open/closed/needs_review and never moves the case.
        "aa_gate": routing.aa_stage_is_due(overall_result, open_deficiencies),
        "note": " ".join(notes) if notes else None,
    }
