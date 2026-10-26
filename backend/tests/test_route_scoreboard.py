"""Route scoreboard: the 21 Table 2.3 rows, their stages, and coverage
(Phase 1.9 — the Phase 1 exit check).

The scoreboard is a read-only catalogue an officer (or a judge) can open to
see all 21 APH Table 2.3 categories, the route pattern each runs, its
window, whether EVC applies, and the ordered stages that route uses — plus
a coverage count (encoded/expected) so a missing row is visible rather than
silent.

It is advisory like everything else from Table 2.3 (Unverified, DEC-0003):
it displays configuration, it makes no routing decision, and it gates
nothing. The endpoint is authentication-gated but carries no per-case
permission because it exposes no case data — only the public route
catalogue.
"""

from __future__ import annotations

from app.services import routing


def test_the_scoreboard_reports_all_21_rows():
    board = routing.scoreboard()
    assert board["total_rows"] == 21
    assert len(board["rows"]) == 21


def test_coverage_is_twenty_one_of_twenty_one():
    """The Phase 1 exit check: the scoreboard shows 21/21."""
    assert routing.scoreboard()["coverage"] == "21/21"


def test_the_board_is_marked_advisory_and_unverified():
    board = routing.scoreboard()
    assert board["advisory_only"] is True
    assert board["status"] == "unverified"


def test_every_row_carries_its_identity_route_window_and_stage_list():
    rows = {row["category_id"]: row for row in routing.scoreboard()["rows"]}
    site = rows["t23-14"]  # Change of Site / Location
    assert site["category"] == "Change of Site / Location"
    assert site["route"] == "SCR+EVC+AA"
    assert site["window"] == "year_round"
    assert site["evc_not_applicable"] is False
    # The stages come from the row's route pattern, in order.
    assert [s["stage"] for s in routing.stages_for_category("t23-14")] == site["stages"]
    assert "evc" in site["stages"]
    assert "shc" in site["stages"]


def test_the_evc_not_applicable_flag_survives_for_the_fn_oci_gulf_row():
    rows = {row["category_id"]: row for row in routing.scoreboard()["rows"]}
    assert rows["t23-08"]["evc_not_applicable"] is True


def test_every_row_points_at_its_prd_source_row():
    for row in routing.scoreboard()["rows"]:
        assert "Table 2.3 row" in row["source"], row["category_id"]


def test_the_endpoint_returns_the_board_to_an_authenticated_user(client, as_user):
    response = client.get(
        "/api/v1/workflow/table-2-3-scoreboard",
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"] == "21/21"
    assert len(body["rows"]) == 21
    assert body["advisory_only"] is True


def test_the_endpoint_requires_authentication(client):
    """Deny by default: no token, no catalogue."""
    response = client.get("/api/v1/workflow/table-2-3-scoreboard")
    assert response.status_code == 401
