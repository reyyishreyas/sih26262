"""One test per Table 2.3 row: routing accuracy against the PRD (Phase 1.3).

The PRD's acceptance criterion for FR-07 is "Routing accuracy vs Table 2.3:
100% (one test per row)". Each of the 21 rows is checked against the PRD
table transcribed **in this file** — route pattern, application window and
resulting stage order — so any drift between `workflow_routes.json` and the
PRD is caught row by row, not in aggregate.

The expected stage lists per pattern come from `test_routing` (single
source for the §6/§7 flow); the per-row expectations here are an
independent copy of the PRD's Table 2.3, deliberately written out rather
than read back from the configuration under test.

Still advisory (Unverified rows, DEC-0003): these tests prove the config
matches the PRD transcription, not that the PRD transcription matches the
official APH edition — that remains the human verification step in
`docs/SOURCES.md`.
"""

from __future__ import annotations

import pytest
from test_routing import EXPECTED_STAGES

from app.services import routing

# md/1_PRD.md §6 "Table 2.3 (21 rows)": row -> (category_id, route, window).
# Rows 1-13 open with the Public Notice; rows 14-21 are year round.
PRD_TABLE: dict[int, tuple[str, str, str]] = {
    1: ("t23-01", "SD", "public_notice"),
    2: ("t23-02", "SD", "public_notice"),
    3: ("t23-03", "SCR+EVC+AA", "public_notice"),
    4: ("t23-04", "SCR", "public_notice"),
    5: ("t23-05", "SCR+EVC+AA", "public_notice"),
    6: ("t23-06", "SCR+EVC+AA", "public_notice"),
    7: ("t23-07", "SCR+EVC+AA", "public_notice"),
    8: ("t23-08", "SCR", "public_notice"),
    9: ("t23-09", "SCR+EVC+AA", "public_notice"),
    10: ("t23-10", "SCR+EVC+AA", "public_notice"),
    11: ("t23-11", "SCR+EVC+AA", "public_notice"),
    12: ("t23-12", "SCR", "public_notice"),
    13: ("t23-13", "SCR+EVC+AA", "public_notice"),
    14: ("t23-14", "SCR+EVC+AA", "year_round"),
    15: ("t23-15", "SCR", "year_round"),
    16: ("t23-16", "SCR", "year_round"),
    17: ("t23-17", "SCR", "year_round"),
    18: ("t23-18", "SCR", "year_round"),
    19: ("t23-19", "SCR", "year_round"),
    20: ("t23-20", "SCR+EVC+AA", "year_round"),
    21: ("t23-21", "SCR+EVC+AA", "year_round"),
}


@pytest.mark.parametrize("row_number", sorted(PRD_TABLE))
def test_row_routes_and_stages_match_the_prd(row_number):
    category_id, route, window = PRD_TABLE[row_number]
    row = routing.category(category_id)

    assert row["row"] == row_number
    assert row["route"] == route, f"Table 2.3 row {row_number} route changed"
    assert row["window"] == window, f"Table 2.3 row {row_number} window changed"

    stages = routing.stages_for_category(category_id)
    assert [stage["stage"] for stage in stages] == EXPECTED_STAGES[route], (
        f"Table 2.3 row {row_number} ({route}) stage order changed"
    )


def test_the_fn_oci_gulf_row_runs_scrutiny_without_evc():
    """Row 8 is the one the PRD marks 'SCR (EVC n/a)'."""
    row = routing.category("t23-08")
    assert row["evc_not_applicable"] is True
    assert "evc" not in [stage["stage"] for stage in routing.stages_for_category("t23-08")]


def test_only_that_row_carries_the_evc_not_applicable_flag():
    flagged = [
        row["category_id"]
        for row in routing.table_2_3_rows()
        if row["evc_not_applicable"]
    ]
    assert flagged == ["t23-08"]


def test_every_prd_row_is_present_and_resolvable():
    """21 rows in, 21 resolvable categories out — none dropped or renamed."""
    assert len(routing.table_2_3_rows()) == 21
    for row_number, (category_id, _route, _window) in PRD_TABLE.items():
        assert routing.category(category_id)["row"] == row_number
