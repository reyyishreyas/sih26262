"""Combined applications: union of stages, per-category outcome (Phase 1.4, FR-08).

PRD routing rule 2: "Combined applications: route = union of needed stages;
outcome recorded per category." An institution may apply for several
Table 2.3 categories on one case (e.g. Conversion Diploma↔Degree *and*
Women's Institution ↔ Co-ed); the case then runs every stage any of its
categories needs, in the canonical flow order, and each category gets its
own recorded outcome.

The stage order lives in configuration (`table_2_3.stage_order`), not in
code, so the admin console (Phase 9) can version it. Everything here stays
advisory, like the rest of Table 2.3 (Unverified, DEC-0003).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Application, ApplicationItem
from app.services import routing

# t23-01 = EoA based on Self-Disclosure (SD); t23-16 = Women's ↔ Co-ed (SCR).
SD_AND_SCR = ["t23-01", "t23-16"]
# t23-05 = Start new Programme (SCR+EVC+AA) + t23-15 = Closure (SCR).
AA_PLUS_SCR = ["t23-05", "t23-15"]


def _names(stages):
    return [stage["stage"] for stage in stages]


# ---------------------------------------------------------------------------
# Union of stages
# ---------------------------------------------------------------------------


def test_the_union_runs_every_stage_any_category_needs_in_flow_order():
    merged = routing.stages_for_categories(SD_AND_SCR)
    assert _names(merged) == [
        "readiness",
        "nil_deficiency_report",
        "scrutiny",
        "executive_decision",
        "appeal_window",
        "grant",
    ]


def test_a_single_category_union_is_just_that_categories_stages():
    assert _names(routing.stages_for_categories(["t23-05"])) == _names(
        routing.stages("SCR+EVC+AA")
    )


def test_duplicate_categories_do_not_duplicate_stages():
    merged = routing.stages_for_categories(["t23-15", "t23-15", "t23-15"])
    assert _names(merged) == _names(routing.stages("SCR"))


def test_conditional_stages_keep_their_condition_in_the_union():
    """SHC stays behind the deficiency gate even in a combined case."""
    shc = {
        stage["stage"]: stage["when"]
        for stage in routing.stages_for_categories(AA_PLUS_SCR)
    }["shc"]
    assert shc == "if_deficiencies"
    appeal = {
        stage["stage"]: stage["when"]
        for stage in routing.stages_for_categories(SD_AND_SCR)
    }["appeal_window"]
    assert appeal == "on_decision"


def test_an_unknown_category_in_a_combined_application_fails_loudly():
    with pytest.raises(KeyError):
        routing.stages_for_categories(["t23-15", "t23-99"])


# ---------------------------------------------------------------------------
# Per-category outcome on the model
# ---------------------------------------------------------------------------


def test_each_category_carries_its_own_outcome(db):
    application = db.get(Application, "app-main-0001")
    db.add(
        ApplicationItem(
            application_id=application.id,
            category_id="t23-05",
            route="SCR+EVC+AA",
            outcome="approved",
        )
    )
    db.add(
        ApplicationItem(
            application_id=application.id,
            category_id="t23-15",
            route="SCR",
        )
    )
    db.commit()

    items = {
        item.category_id: item
        for item in db.scalars(
            select(ApplicationItem).where(
                ApplicationItem.application_id == application.id
            )
        )
    }
    assert items["t23-05"].outcome == "approved"
    assert items["t23-15"].outcome is None, "outcomes are per category, not shared"
    assert all(item.route for item in items.values())


def test_the_same_category_cannot_be_added_to_one_application_twice(db):
    application = db.get(Application, "app-main-0001")
    db.add(ApplicationItem(application_id=application.id, category_id="t23-05", route="SCR+EVC+AA"))
    db.commit()
    db.add(ApplicationItem(application_id=application.id, category_id="t23-05", route="SCR+EVC+AA"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_an_application_removes_its_items(db):
    application = db.get(Application, "app-main-0001")
    db.add(ApplicationItem(application_id=application.id, category_id="t23-16", route="SCR"))
    db.commit()

    db.delete(application)
    db.commit()

    remaining = db.scalars(
        select(ApplicationItem).where(ApplicationItem.category_id == "t23-16")
    ).all()
    assert remaining == []
