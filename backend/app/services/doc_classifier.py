"""Advisory document classification (PRD FR-38, section 8 pipeline step 1).

The PRD's ingest step classifies an upload as one of five named things —
*EoA letter, Format-2 NOC, Format-3 Resolution, lease, affidavit* — plus the
catch-all *other Annexure-2 item*. This module does that from configuration
(``backend/rules/doc_classifier.json``) and the text the reader already
produced: phrase lists, weighted counting, no model call, no decision.

Safety properties (each is a way classification could quietly overreach):

- **It is a suggestion, never a change.** The recorded ``doc_type`` is the
  uploader's declaration; a disagreement is flagged for review (and surfaced
  as an upload warning) but never corrected, never rejected, never blocking
  (DEC-0003; PRD line 137: "None blocks or rejects").
- **It is honest about its evidence.** No readable text answers ``no_text``
  (the reader is a mock or the scan failed), text matching nothing answers
  ``unclassified``, an equal tie answers ``ambiguous`` — each with
  ``needs_review``. A classification resting only on the file name is
  always needs-review: a name is a label someone typed, not page content.
- **The phrase lists are labelled placeholders.** The official Format-2 /
  Format-3 templates are not available yet (PRD section 19 asks), so the
  lists are prototype evidence, not authority — the config says so.
"""

from __future__ import annotations

import re
from typing import Any

from .policy import doc_classifier_policy


def config() -> dict[str, Any]:
    """The raw classifier configuration (``rules/doc_classifier.json``)."""
    return doc_classifier_policy()


def classes() -> list[dict[str, Any]]:
    """The five PRD-named classes, in configured order."""
    return list(config()["classes"])


def _normalise(text: str) -> str:
    """Collapses whitespace so phrases survive PDF line breaks and OCR gaps."""
    return re.sub(r"\s+", " ", text).strip()


def _matches(phrase: str, text: str) -> bool:
    rules = config()["matching"]
    if rules.get("word_boundary", True):
        pattern = r"\b" + re.escape(phrase) + r"\b"
    else:
        pattern = re.escape(phrase)
    flags = 0 if rules.get("case_sensitive", False) else re.IGNORECASE
    return re.search(pattern, text, flags) is not None


def _evidence(*, page_texts: list[str] | None, file_name: str) -> dict[str, Any]:
    """Phrase hits per class, from the page text and (weakly) the file name."""
    rules = config()["matching"]
    text = _normalise("\n".join(t for t in (page_texts or []) if t and t.strip()))
    name = _normalise(file_name or "")
    per_class: dict[str, dict[str, Any]] = {}

    for entry in classes():
        text_hits = [p for p in entry["phrases"] if text and _matches(p, text)]
        name_hits = [p for p in entry["phrases"] if name and _matches(p, name)]
        if not text_hits and not name_hits:
            continue
        score = (
            int(rules["text_weight"]) * len(text_hits)
            + int(rules["file_name_weight"]) * len(name_hits)
        )
        signals = []
        if text_hits:
            signals.append("text")
        if name_hits:
            signals.append("file_name")
        per_class[entry["class_id"]] = {
            "class_id": entry["class_id"],
            "label": entry["label"],
            "phrases": sorted(set(text_hits) | set(name_hits)),
            "signals": signals,
            "score": score,
        }

    hits = sorted(
        per_class.values(), key=lambda row: (-row["score"], row["class_id"])
    )
    return {"text": text, "hits": hits}


def classify(
    *,
    page_texts: list[str] | None = None,
    file_name: str = "",
    declared_doc_type: str | None = None,
) -> dict[str, Any]:
    """Which configured class this upload most looks like — advisory only.

    Computed from the caller's inputs and the configuration; stores nothing
    and decides nothing.
    """
    cfg = config()
    evidence = _evidence(page_texts=page_texts, file_name=file_name)
    hits: list[dict[str, Any]] = evidence["hits"]
    has_text = bool(evidence["text"])

    label_id: str | None = None
    label: str | None = None
    candidates: list[str] = []
    evidence_source: str | None = None
    note: str | None = None

    if not has_text:
        status = "no_text"
        note = (
            "The file produced no readable text (a scan the reader could not "
            "read, or a demo reader that does not read bytes), so nothing "
            "could be classified."
        )
        if hits:
            note += " The file name alone suggests: " + ", ".join(
                row["label"] for row in hits
            ) + "."
    elif not hits:
        status = "unclassified"
        note = cfg["fallback"]["note"]
    else:
        top_score = hits[0]["score"]
        top = [row for row in hits if row["score"] == top_score]
        if len(top) > 1:
            status = "ambiguous"
            candidates = [row["class_id"] for row in top]
            note = (
                "Two document types matched equally ("
                + " and ".join(row["label"] for row in top)
                + ") — a checker will decide which this is."
            )
        else:
            status = "classified"
            label_id = top[0]["class_id"]
            label = top[0]["label"]
            evidence_source = (
                "text" if "text" in top[0]["signals"] else "file_name"
            )

    agrees: bool | None = None
    if label_id is not None and declared_doc_type:
        declared_types = next(
            entry["declared_doc_types"]
            for entry in classes()
            if entry["class_id"] == label_id
        )
        agrees = declared_doc_type in declared_types

    mismatch_note: str | None = None
    if agrees is False:
        mismatch_note = (
            f"Uploaded as '{declared_doc_type}' but the content reads more "
            f"like: {label}. The recorded type is unchanged — a checker will "
            "confirm which it is."
        )

    needs_review = (
        status != "classified"
        or agrees is False
        or evidence_source == "file_name"
    )
    if status == "classified":
        # Both caveats are independent and can be true at once: a checker
        # shown "reads more like X" must also know when X rests only on the
        # file name the uploader typed (BUG-0018).
        parts = []
        if evidence_source == "file_name":
            parts.append(
                "Classified from the file name only — the page text did not "
                "confirm it."
            )
        if mismatch_note:
            parts.append(mismatch_note)
        note = " ".join(parts) or None

    return {
        "classifier_id": cfg["classifier_id"],
        "status": status,
        "label_id": label_id,
        "label": label,
        "candidates": candidates,
        "hits": hits,
        "declared_doc_type": declared_doc_type,
        "agrees_with_declared": agrees,
        "evidence": evidence_source,
        "needs_review": needs_review,
        "mismatch_note": mismatch_note,
        "note": note,
        "human_review": cfg["human_review"],
        "placeholder": cfg.get("placeholder", False),
        "advisory_only": cfg.get("advisory_only", True),
        "source": cfg.get("source"),
    }
