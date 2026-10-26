"""Sequencing: Women's conversion clears before the merger starts (Phase 1.5).

PRD routing rule 4 (cl. 2.13.1m): "Women's-to-Co-ed conversion first,
merger after it clears." A combined application that asks for both must
not advance its merger category until the conversion category has a
clearing outcome — recorded per category (FR-08, task 1.4).

The rule is configuration (`table_2_3.sequencing_rules`), not code, and
advisory like everything else from Table 2.3 (Unverified, DEC-0003). The
"clearing" outcome value is provisional: the decision vocabulary arrives
with Phase 6; "approved" is used because it is the workflow's existing
state name, and nothing here may gate a real case yet.
"""

from __future__ import annotations

import pytest

from app.services import routing

WOMENS = "t23-16"  # Women's Institution ↔ Co-ed (SCR)
MERGER = "t23-06"  # Merger of Institutions (SCR+EVC+AA)


def test_the_merger_requires_the_womens_conversion_to_clear():
    assert routing.prerequisites_for(MERGER) == [WOMENS]


def test_categories_without_a_rule_have_no_prerequisites():
    for category_id in ("t23-01", WOMENS, "t23-14", "t23-21"):
        assert routing.prerequisites_for(category_id) == []


def test_the_merger_is_blocked_until_the_conversion_has_a_clearing_outcome():
    blocked = routing.unmet_prerequisites(MERGER, {WOMENS: None})
    assert blocked == [WOMENS]

    cleared = routing.unmet_prerequisites(MERGER, {WOMENS: "approved"})
    assert cleared == []

    not_cleared = routing.unmet_prerequisites(MERGER, {WOMENS: "rejected"})
    assert not_cleared == [WOMENS], "a conversion that did not clear still blocks"


def test_an_item_missing_from_the_outcome_map_counts_as_not_cleared():
    assert routing.unmet_prerequisites(MERGER, {}) == [WOMENS]


def test_a_single_category_case_is_never_blocked_by_absent_items():
    assert routing.unmet_prerequisites("t23-15", {}) == []


def test_an_unknown_category_fails_loudly():
    with pytest.raises(KeyError):
        routing.prerequisites_for("t23-99")
    with pytest.raises(KeyError):
        routing.unmet_prerequisites("t23-99", {})


def test_the_rule_points_at_the_clause_it_came_from():
    """No invented clause: the rule cites the PRD row that carries it."""
    rule = routing.sequencing_rules()[0]
    assert rule["requires"] == WOMENS
    assert rule["category"] == MERGER
    assert "2.13.1m" in rule["source"]
