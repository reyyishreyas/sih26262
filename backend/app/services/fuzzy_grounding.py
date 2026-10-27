"""Fuzzy grounding: a model value counts only if it is found on the page.

PRD FR-40 / section 8 step 3 (line 135): *"a model value counts only if
its text is found on the page (fuzzy match to OCR words); else
`REVIEW_REQUIRED`"* — repeated as Essentials rule 10 for vision-model
values. The reasoning: an LLM can produce a plausible, complete,
confident-sounding value that simply is not in the document. Only the
page can vouch for it, and the page is read by OCR, which misreads
characters — so the match is fuzzy, tolerant of a substitution, but not
of absence.

What this module deliberately does **not** do: it never changes a value,
never touches `verification_status`, never rejects or blocks anything.
It answers one question — *can this text be found on the page?* — and
records the answer as field provenance. An ungrounded value stays stored
as a candidate with `REVIEW_REQUIRED` and a warning, for a human (DEC-0003,
Essentials rule 16: missing or uncertain data is review, never a guessed
pass).

Thresholds live in `rules/fuzzy_grounding.json` as labelled placeholders:
the PRD requires fuzzy matching but states no numbers.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ..adapters.ocr.base import ExtractedFieldCandidate
from .policy import fuzzy_grounding_policy


def config() -> dict[str, Any]:
    """The grounding policy (rules/fuzzy_grounding.json)."""
    return fuzzy_grounding_policy()


def _display_value(value: object) -> str:
    """The text of a value that must be found on the page.

    The Gemini path stores ``{"value": ..., "source_quote": ...}``; the
    *value* is what FR-40 grounds (the quote is its citation, not the
    claim itself). Anything else is rendered as its string form.
    """
    if isinstance(value, dict):
        inner = value.get("value")
        return _display_value(inner) if inner is not None else ""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_display_value(item) for item in value)
    return str(value)


def _normalise(text: str, *, case_sensitive: bool) -> str:
    """NFKC + optional casefold + punctuation to single spaces.

    The page says ``Sub-Registrar of Records,`` and the value says
    ``sub registrar of records`` — same words, so same tokens. Underscores
    count as separators too (``\\w`` keeps them).
    """
    normalised = unicodedata.normalize("NFKC", text)
    if not case_sensitive:
        normalised = normalised.casefold()
    return re.sub(r"[\W_]+", " ", normalised, flags=re.UNICODE).strip()


def ground(
    *,
    value: object,
    page_texts: list[str] | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grounds one value against the words the page actually contains.

    Returns ``grounded`` (bool), ``status`` (config's vocabulary:
    ``grounded`` / ``REVIEW_REQUIRED``), ``similarity`` (mean best
    per-token match ratio, 0..1), ``matched``/``tokens`` counts and a
    human-readable ``reason``. Honest failures — no page text, an empty
    value, or too little to check — all answer ``REVIEW_REQUIRED``, never
    a pass (Essentials rule 16).
    """
    cfg = policy or config()
    matching = cfg["matching"]
    statuses = cfg["statuses"]
    review_status = statuses["review_required"]

    def _review(reason: str) -> dict[str, Any]:
        return {
            "grounded": False,
            "status": review_status,
            "similarity": 0.0,
            "matched": 0,
            "tokens": 0,
            "reason": reason,
        }

    pages = [page for page in (page_texts or []) if page and page.strip()]
    if not pages:
        return _review("no_page_text")

    case_sensitive = bool(matching.get("case_sensitive", False))
    text = _display_value(value)
    normalised_value = _normalise(text, case_sensitive=case_sensitive)
    if not normalised_value:
        return _review("empty_value")

    min_length = int(matching["min_token_length"])
    tokens = [token for token in normalised_value.split() if len(token) >= min_length]
    if not tokens:
        # e.g. a bare "12": nothing long enough to check honestly, so a
        # human decides — guessing "found" would be exactly the failure
        # FR-40 exists to prevent.
        return _review("no_significant_tokens")

    page_words = _normalise(" ".join(pages), case_sensitive=case_sensitive).split()
    page_set = set(page_words)

    matched = 0
    ratios: list[float] = []
    missing: list[str] = []
    threshold = float(matching["token_similarity"])
    for token in tokens:
        if token in page_set:
            matched += 1
            ratios.append(1.0)
            continue
        # Fuzzy leg: the closest word on any page. OCR noise is a
        # substitution or two, which SequenceMatcher forgives; absence is
        # not closeness, and a low best-ratio is exactly "not on page".
        best = (
            max(SequenceMatcher(None, token, page_word).ratio() for page_word in page_words)
            if page_words
            else 0.0
        )
        ratios.append(best)
        if best >= threshold:
            matched += 1
        else:
            missing.append(token)

    similarity = round(sum(ratios) / len(ratios), 4)
    matched_ratio = matched / len(tokens)
    grounded = matched_ratio + 1e-9 >= float(matching["min_match_ratio"])
    return {
        "grounded": grounded,
        "status": statuses["grounded"] if grounded else review_status,
        "similarity": similarity,
        "matched": matched,
        "tokens": len(tokens),
        "reason": (
            "all_tokens_found"
            if grounded
            else "not on page: " + ", ".join(missing[:3])
        ),
    }


def ground_candidates(
    candidates: list[ExtractedFieldCandidate],
    page_texts: list[str] | None,
    policy: dict[str, Any] | None = None,
) -> list[str]:
    """Grounds every candidate produced by a *model* method, in place.

    Only methods listed in the config's ``model_methods`` are grounded:
    OCR values are the page's own words (there is nothing to vouch for
    them with) and the mock never read a page. Returns advisory warnings
    for ungrounded values — the caller appends them to the upload's
    existing warnings, so the UI shows them on a 201 without any record,
    value or status changing (the 5.1 classifier pattern).
    """
    cfg = policy or config()
    model_methods = set(cfg["model_methods"])
    warnings: list[str] = []
    for candidate in candidates:
        if candidate.method not in model_methods:
            continue
        result = ground(value=candidate.value, page_texts=page_texts, policy=cfg)
        candidate.grounding = result["status"]
        if not result["grounded"]:
            warnings.append(
                f"model value for {candidate.field_name} could not be found on the "
                f"page ({result['reason']}) — recorded as "
                f"{result['status']} for a human to check; the stored value and "
                "every status are unchanged."
            )
    return warnings
