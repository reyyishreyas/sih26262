"""Table 2.3 routing data: the contract the routing engine will be built on (Phase 1.1).

`backend/rules/workflow_routes.json` carries a ``table_2_3`` section: the 21
APH Table 2.3 rows transcribed from the PRD's "routing test source of truth"
table (``md/1_PRD.md`` §6). This file pins the *shape and honesty* of that
data before any routing code exists:

* exactly 21 rows, in the PRD's order, each with a stable ``category_id``;
* every ``route`` is one of the four documented patterns (SD, SCR, SCR+EVC,
  SCR+EVC+AA) and every ``window`` is one of the two documented values;
* the EVC-not-applicable flag is set only where the PRD says "EVC n/a" —
  the Foreign Nationals / OCI / Gulf row;
* the section is marked **unverified and advisory-only**: PRD §0 and
  DEC-0003 require that anything transcribed from the APH stays disabled or
  advisory until a named reviewer records the exact clause in
  ``docs/SOURCES.md``. Nothing here may block, return or reject an
  application.

The per-row *routing behaviour* tests arrive with the routing service in
task 1.3 (``test_routing_table_2_3.py``); these tests exist so the data
cannot drift while that service is being built.
"""

from __future__ import annotations

import json

from app.services.policy import RULES_DIR

ROW_COUNT = 21
VALID_ROUTES = {"SD", "SCR", "SCR+EVC", "SCR+EVC+AA"}
VALID_WINDOWS = {"public_notice", "year_round"}

# The one row the PRD marks "SCR (EVC n/a)": seats for Foreign Nationals,
# OCI and children of Indian workers in the Gulf (Table 2.3 row 8).
EVC_N_A_CATEGORY = "Seats for Foreign Nationals, OCI, Children of Indian Workers in Gulf"


def _section() -> dict:
    with (RULES_DIR / "workflow_routes.json").open() as handle:
        data = json.load(handle)
    assert "table_2_3" in data, "workflow_routes.json has no table_2_3 section"
    return data["table_2_3"]


def _rows() -> list[dict]:
    return _section()["rows"]


def test_there_are_exactly_21_rows_in_prd_order():
    rows = _rows()
    assert len(rows) == ROW_COUNT
    assert [row["row"] for row in rows] == list(range(1, ROW_COUNT + 1))


def test_every_row_has_a_stable_unique_category_id():
    ids = [row["category_id"] for row in _rows()]
    assert len(set(ids)) == ROW_COUNT, "category ids must be unique"
    assert all(isinstance(value, str) and value for value in ids)


def test_routes_and_windows_use_only_the_documented_vocabulary():
    for row in _rows():
        assert row["route"] in VALID_ROUTES, row
        assert row["window"] in VALID_WINDOWS, row


def test_evc_not_applicable_is_set_only_for_the_fn_oci_gulf_row():
    flagged = [row for row in _rows() if row["evc_not_applicable"]]
    assert len(flagged) == 1, "only the PRD's '(EVC n/a)' row carries the flag"
    assert flagged[0]["category"] == EVC_N_A_CATEGORY
    # The PRD shows that row as "SCR (EVC n/a)" — scrutiny, no EVC.
    assert flagged[0]["route"] == "SCR"


def test_the_section_is_marked_unverified_and_advisory_only():
    """Unverified APH data must never be able to gate an application."""
    section = _section()
    assert section["status"] == "unverified"
    assert section["advisory_only"] is True
    assert "SOURCES.md" in (section.get("note") or ""), (
        "the note must point a reviewer at the source register"
    )
    assert all(row.get("source") for row in _rows()), (
        "every row must say where it came from"
    )
