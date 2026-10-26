"""Fallback-to-EoA branch after "not approved" (Phase 1.8).

PRD FR-11 / §6 routing rule 3: "Fallback to EoA (2.7l, 2.14j, 2.15e):
after 'not approved' for new programme / level conversion / Women's-to-
Co-ed, issue EoA for the existing institution **if requirements are met**;
the engine opens this branch automatically."

So three categories qualify (Start new Programme/Level, Conversion
Diploma↔Degree, Women's Institution ↔ Co-ed), and a "not approved" outcome
makes the branch *eligible* to open.

Safety rules honoured here:
- **"if requirements are met" is unevaluable from the PRD** — it never
  enumerates the requirements. So when the trigger fires the answer is
  ``review_required`` (a human decides whether to actually issue the EoA),
  never an automatic "issue". Rule 1 (humans decide) + rule 4 (missing
  data is needs-review, never a guessed pass).
- The three clause numbers (2.7l / 2.14j / 2.15e) are recorded as the
  PRD gives them, **as a set** — the PRD does not say which clause covers
  which category, so no clause→category mapping is asserted (no invented
  citation, Master Prompt §2 rule 2).
- Advisory configuration (`table_2_3.fallback_eoa`), like 1.5/1.6/1.7.
"""

from __future__ import annotations

from app.services import routing

NEW_PROGRAMME = "t23-05"  # Start new Programme / Level
CONVERSION = "t23-03"  # Conversion Diploma↔Degree
WOMENS = "t23-16"  # Women's Institution ↔ Co-ed

QUALIFYING = (NEW_PROGRAMME, CONVERSION, WOMENS)


def test_the_fallback_rule_is_configured_and_advisory():
    rule = routing.fallback_eoa_rule()
    assert rule["status"] == "unverified"
    assert rule["advisory_only"] is True


def test_the_rule_points_at_the_frs_and_clauses_it_came_from():
    rule = routing.fallback_eoa_rule()
    assert "FR-11" in rule["source"] or "2.7l" in str(rule.get("clauses"))
    # The clauses are recorded as the PRD gives them, not remapped.
    assert set(rule["clauses"]) == {"2.7l", "2.14j", "2.15e"}


def test_the_three_prd_qualifying_categories_are_listed():
    assert set(routing.fallback_eoa_rule()["categories"]) == set(QUALIFYING)


def test_a_qualifying_category_with_a_not_approved_outcome_needs_review():
    """The branch becomes eligible, but 'requirements are met' is unevaluable
    from the PRD — so a human decides, never an automatic issue."""
    for category_id in QUALIFYING:
        assert (
            routing.fallback_eoa_status(category_id, "rejected")
            == "review_required"
        ), category_id


def test_a_non_qualifying_category_is_not_applicable():
    # Change of Site and Closure are not in the PRD's fallback list.
    assert routing.fallback_eoa_status("t23-14", "rejected") == "not_applicable"
    assert routing.fallback_eoa_status("t23-15", "rejected") == "not_applicable"


def test_a_qualifying_category_without_the_trigger_is_not_triggered():
    assert routing.fallback_eoa_status(NEW_PROGRAMME, "approved") == "not_triggered"


def test_an_undecided_or_unknown_outcome_is_uncertain_not_a_clean_no():
    """An outcome we don't recognise must not be read as 'no fallback'."""
    assert routing.fallback_eoa_status(NEW_PROGRAMME, None) == "review_required"
    assert routing.fallback_eoa_status(NEW_PROGRAMME, "something_else") == "review_required"


def test_fallback_eoa_applies_answers_which_categories_qualify():
    assert routing.fallback_eoa_applies(NEW_PROGRAMME) is True
    assert routing.fallback_eoa_applies(WOMENS) is True
    assert routing.fallback_eoa_applies("t23-14") is False


def test_an_unknown_category_fails_loudly():
    import pytest

    with pytest.raises(KeyError):
        routing.fallback_eoa_status("t23-99", "rejected")
    with pytest.raises(KeyError):
        routing.fallback_eoa_applies("t23-99")
