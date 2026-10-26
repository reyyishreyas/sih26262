"""Table 2.3 routing: which stages a category runs, and in what order.

Answers come from configuration only — ``rules/workflow_routes.json``'s
``table_2_3`` section (the 21 APH rows and the four PRD §6 patterns). No
route, stage or condition is hard-coded here, and nothing in this module
may block, return or reject an application: the rows are **Unverified**
until a reviewer records the exact clause in ``docs/SOURCES.md``
(DEC-0003, PRD §0), so every answer this service gives is advisory input
to a workflow decision, never the decision itself.
"""

from __future__ import annotations

from typing import Any

from .policy import workflow_routes

_SECTION = "table_2_3"


def _section() -> dict[str, Any]:
    section = workflow_routes().get(_SECTION)
    if not section:
        raise KeyError(
            f"workflow_routes.json has no {_SECTION!r} section — the Table 2.3 "
            "routing table is missing from configuration"
        )
    return section


def is_advisory() -> bool:
    """True while the APH clauses behind these rows are unverified."""
    return bool(_section().get("advisory_only"))


def table_2_3_rows() -> list[dict[str, Any]]:
    """The 21 category rows, in PRD order."""
    return list(_section().get("rows", []))


def category(category_id: str) -> dict[str, Any]:
    """One Table 2.3 row by its stable id (``t23-01`` … ``t23-21``).

    Raises ``KeyError`` rather than answering with a default: an unknown
    category must reach a human as 'no route known', never as a guessed one.
    """
    for row in table_2_3_rows():
        if row.get("category_id") == category_id:
            return row
    raise KeyError(f"unknown Table 2.3 category: {category_id!r}")


def route_patterns() -> dict[str, Any]:
    """The four PRD §6 patterns (SD, SCR, SCR+EVC, SCR+EVC+AA)."""
    return dict(_section().get("route_patterns", {}))


def route_pattern(category_id: str) -> str:
    """The route pattern a category uses (``SD`` / ``SCR`` / …)."""
    return str(category(category_id)["route"])


def stages(route_pattern_name: str) -> list[dict[str, Any]]:
    """Ordered stages for a pattern; each entry is ``{stage, when}``.

    ``when`` is ``always``, ``if_deficiencies`` (the PRD §6 "AA" gate) or
    ``on_decision`` (the appeal window). Raises ``KeyError`` for an unknown
    pattern.
    """
    patterns = route_patterns()
    if route_pattern_name not in patterns:
        raise KeyError(f"unknown route pattern: {route_pattern_name!r}")
    return list(patterns[route_pattern_name].get("stages", []))


def stages_for_category(category_id: str) -> list[dict[str, Any]]:
    """Ordered stages for a category's pattern."""
    return stages(route_pattern(category_id))


def stage_order() -> list[str]:
    """Canonical flow order (PRD §7) used to interleave combined stages."""
    return list(_section().get("stage_order", []))


def stages_for_categories(category_ids: list[str]) -> list[dict[str, Any]]:
    """Ordered union of the stage lists of several categories (FR-08).

    A combined application runs every stage *any* of its categories needs,
    interleaved in the canonical flow order so SD's Nil Deficiency report
    and SCR's scrutiny sit where the PRD puts them. A stage named by more
    than one category appears once; if the categories disagree about its
    condition, the **most restrictive** one wins — a gate that one category
    requires (SHC behind its deficiency gate) must not be opened wider
    because another category happens to list the same stage. Unknown
    categories raise ``KeyError`` via :func:`stages_for_category`.
    """
    merged: dict[str, str] = {}
    for category_id in category_ids:
        for stage in stages_for_category(category_id):
            name, when = stage["stage"], stage["when"]
            if name not in merged or _WHEN_RANK[when] < _WHEN_RANK[merged[name]]:
                merged[name] = when

    order = stage_order()
    if set(merged) - set(order):
        raise KeyError(
            "stage_order is missing stages used by the route patterns: "
            f"{sorted(set(merged) - set(order))}"
        )
    return [
        {"stage": name, "when": merged[name]}
        for name in sorted(merged, key=order.index)
    ]


def sequencing_rules() -> list[dict[str, Any]]:
    """Rules for a category that must clear before another may start."""
    return list(_section().get("sequencing_rules", []))


def prerequisites_for(category_id: str) -> list[str]:
    """Categories that must clear before this one may start (PRD rule 4).

    Validates the category against the table first, so an unknown id fails
    loudly rather than silently answering "no prerequisites".
    """
    category(category_id)  # raises KeyError for an unknown id
    return [
        rule["requires"]
        for rule in sequencing_rules()
        if rule["category"] == category_id
    ]


def unmet_prerequisites(
    category_id: str, outcomes: dict[str, str | None]
) -> list[str]:
    """Which prerequisites have not cleared yet.

    ``outcomes`` maps category id → its recorded per-category outcome
    (None when undecided). A prerequisite counts as cleared only when its
    outcome equals the rule's ``clears_with`` value — undecided or any
    other outcome keeps the successor blocked.
    """
    unmet: list[str] = []
    prerequisites_for(category_id)  # unknown category fails loudly
    for rule in sequencing_rules():
        if rule["category"] != category_id:
            continue
        required, clears_with = rule["requires"], rule["clears_with"]
        if outcomes.get(required) != clears_with:
            unmet.append(required)
    return unmet


def additional_evc_actions() -> list[dict[str, Any]]:
    """Actions that pull a case into the EVC queue outside its route's
    standard stages (PRD §6 routing rules 1 and 5, FR-19).

    Two exist today: a "random" EVC add for a self-disclosure case
    (cl. 2.3.5) and a second EVC after movable property is shifted on a
    Change of Site (cl. 2.17e). Advisory like the rest of this module.
    """
    return list(_section().get("additional_evc_actions", []))


def evc_actions_for_category(category_id: str) -> list[dict[str, Any]]:
    """Which additional-EVC actions apply to a category.

    An action matches when its ``applies_to`` names this category's route
    pattern (``route_pattern``, e.g. every SD case may get a random EVC) or
    lists the category id explicitly (``category_ids``, e.g. the second EVC
    after a site shift). Validates the category first so an unknown id
    fails loudly rather than silently answering "no actions".

    Advisory only: this answers "may an authorised user ask for this
    visit?", never "schedule it". Which roles may act is an open question
    (PRD §19 #4), so each action's ``authorised_roles`` is an empty
    labelled placeholder until a human records the authority.
    """
    pattern = route_pattern(category_id)  # unknown category fails loudly
    return [
        action
        for action in additional_evc_actions()
        if _evc_action_applies(action, category_id, pattern)
    ]


def _evc_action_applies(
    action: dict[str, Any], category_id: str, route_pattern_name: str
) -> bool:
    applies_to = action.get("applies_to", {})
    if applies_to.get("route_pattern") == route_pattern_name:
        return True
    return category_id in applies_to.get("category_ids", [])


def aa_gate() -> dict[str, Any]:
    """The "AA" (as applicable) gate configuration (PRD FR-10, §6).

    Decides when the SHC/SAC stage is due on a SCR+EVC+AA route: only
    when the earlier outcome carries a deficiency or a negative scrutiny
    result. Advisory like the rest of this module.
    """
    gate = _section().get("aa_gate")
    if not gate:
        raise KeyError(
            f"workflow_routes.json has no {_SECTION!r}.aa_gate — the 'AA' "
            "gate definition is missing from configuration"
        )
    return dict(gate)


def aa_stage_is_due(
    scrutiny_result: str | None, deficiencies_remaining: int
) -> str:
    """Is the SHC/SAC ("AA") stage due for this case?

    Answers ``open``, ``closed`` or ``needs_review``.

    The gate opens when *either* condition holds (FR-10: "deficiency **or**
    negative outcome"): there is at least one open deficiency, or the
    recorded scrutiny result is a configured negative one. It stays closed
    only when the result is a configured clean one *and* no deficiency
    remains.

    **Missing or unrecognised data is never a guessed open or closed**
    (Master Prompt §2 rule 4): an ``None`` (undecided) or a result outside
    the configured vocabulary answers ``needs_review`` so a human decides,
    rather than the gate silently opening or shutting on absent evidence.

    Advisory only: this reports whether SHC looks due; it never opens the
    stage, transitions the case or blocks anything.
    """
    gate = aa_gate()  # missing config fails loudly
    vocabulary = gate["scrutiny_results"]

    if scrutiny_result is None or (
        scrutiny_result not in vocabulary["clean"]
        and scrutiny_result not in vocabulary["negative"]
    ):
        return str(gate["undecided_result"])  # "needs_review"

    if deficiencies_remaining > 0:
        return "open"
    if scrutiny_result in vocabulary["negative"]:
        return "open"
    return "closed"


# How much a condition gates the stage: lower keeps the stage more tightly
# closed. Used to merge conditions when categories disagree.
_WHEN_RANK = {"if_deficiencies": 0, "on_decision": 1, "always": 2}
