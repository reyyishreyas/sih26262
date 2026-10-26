"""Additional-EVC actions: random EVC for SD, second EVC after site shift
(Phase 1.6).

PRD §6 routing rules 1 and 5 (FR-19):
  1. Random EVC (cl. 2.3.5) — an authorised user can pull an SD application
     into the EVC queue.
  5. Change of Site (cl. 2.17e) — a second EVC may be needed after movable
     property is shifted.

Both are configuration (`table_2_3.additional_evc_actions`), not code, and
advisory like everything else from Table 2.3 (Unverified, DEC-0003). They
are deliberately *not* wired to any workflow transition: PRD open question
#4 ("Which roles may add a random EVC?") is unanswered, so the
`authorised_roles` list is an empty, clearly-labelled placeholder rather
than a guessed authority. Nothing here may gate, block or transition a
case — this is a lookup an officer-facing screen can read, exactly as the
1.5 sequencing rules are.
"""

from __future__ import annotations

import pytest

from app.services import routing

SD_CATEGORIES = ("t23-01", "t23-02")  # the two EoA-on-self-disclosure rows
SITE = "t23-14"  # Change of Site / Location (SCR+EVC+AA)


def _action(action_id: str) -> dict:
    for entry in routing.additional_evc_actions():
        if entry["action_id"] == action_id:
            return entry
    raise AssertionError(f"missing additional-EVC action: {action_id}")


def test_the_two_prd_additional_evc_actions_exist():
    ids = {entry["action_id"] for entry in routing.additional_evc_actions()}
    assert ids == {"random_evc", "second_evc_after_site_shift"}


def test_random_evc_applies_to_both_sd_categories():
    for category_id in SD_CATEGORIES:
        applied = [a["action_id"] for a in routing.evc_actions_for_category(category_id)]
        assert applied == ["random_evc"], category_id


def test_the_second_evc_applies_to_change_of_site():
    applied = [
        a["action_id"] for a in routing.evc_actions_for_category(SITE)
    ]
    assert applied == ["second_evc_after_site_shift"]


def test_a_category_with_no_action_returns_empty_not_a_guess():
    # Women's conversion (SCR) has neither action; it must not inherit one.
    assert routing.evc_actions_for_category("t23-16") == []
    assert routing.evc_actions_for_category("t23-21") == []


def test_an_unknown_category_fails_loudly():
    with pytest.raises(KeyError):
        routing.evc_actions_for_category("t23-99")


def test_both_actions_are_advisory_and_unverified():
    """Nothing from Table 2.3 may gate a case yet (DEC-0003)."""
    for entry in routing.additional_evc_actions():
        assert entry["status"] == "unverified", entry["action_id"]
        assert entry["advisory_only"] is True, entry["action_id"]


def test_each_action_points_at_the_clause_it_came_from():
    """No invented clause: each action cites the PRD row that carries it."""
    assert "2.3.5" in _action("random_evc")["source"]
    assert "2.17e" in _action("second_evc_after_site_shift")["source"]


def test_the_second_evc_trigger_is_the_property_shift():
    """2.17e says a second EVC *may* follow the shift — an officer judgement."""
    trigger = _action("second_evc_after_site_shift")["trigger"].lower()
    assert "movable property" in trigger or "shift" in trigger


def test_no_role_is_silently_authorised_the_question_is_still_open():
    """PRD open question #4 (who may add a random EVC) is unanswered, so the
    authority must be an empty labelled placeholder — never a guessed role."""
    for entry in routing.additional_evc_actions():
        assert entry["authorised_roles"] == [], entry["action_id"]
        assert entry["authorised_roles_status"] == "unverified_placeholder"
