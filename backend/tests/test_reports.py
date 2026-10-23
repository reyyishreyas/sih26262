"""Reports: scope filtering, section shape, and reconciliation with the dashboard."""

from __future__ import annotations


def test_all_sections_load_for_a_supervisor(client, as_user):
    headers = as_user("supervisor@demo.local")
    body = client.get("/api/v1/reports", headers=headers).json()

    for section in (
        "pendency",
        "regions",
        "evc",
        "undertakings",
        "documents",
        "overdue",
        "workload",
    ):
        assert section in body, f"missing report section: {section}"

    assert body["pendency"]["total_cases"] >= 1
    assert body["pendency"]["by_state"]
    assert isinstance(body["regions"]["regions"], list)
    assert body["undertakings"]["total"] >= 0
    assert body["overdue"]["total_overdue"] == len(body["overdue"]["items"])


def test_individual_endpoints_match_the_bundle(client, as_user):
    headers = as_user("supervisor@demo.local")
    bundle = client.get("/api/v1/reports", headers=headers).json()

    single = client.get("/api/v1/reports/overdue", headers=headers).json()
    assert single["total_overdue"] == bundle["overdue"]["total_overdue"]

    docs = client.get("/api/v1/reports/documents", headers=headers).json()
    assert docs["expired"] + docs["expiring_30_days"] + docs["expiring_60_days"] <= (
        docs["documents_dated"] + docs["no_date_read"]
    )


def test_overdue_items_are_sorted_worst_first(client, as_user):
    headers = as_user("admin@demo.local")
    body = client.get("/api/v1/reports/overdue", headers=headers).json()
    days = [item["days_late"] for item in body["items"]]
    assert days == sorted(days, reverse=True)


def test_scope_is_enforced_for_every_section(client, as_user):
    """A college representative holds no monitoring permission at all."""
    headers = as_user("institution@demo.local")
    assert client.get("/api/v1/reports", headers=headers).status_code == 403
    for path in ("pendency", "regions", "evc", "overdue", "workload"):
        assert (
            client.get(f"/api/v1/reports/{path}", headers=headers).status_code == 403
        )


def test_a_scoped_officer_only_sees_their_own_region(client, as_user):
    headers = as_user("regional@demo.local")
    regions = client.get("/api/v1/reports/regions", headers=headers).json()["regions"]
    codes = {row["region_code"] for row in regions}
    # The seeded demo has two regions; the regional officer owns only one.
    assert codes == {"NR"}

    pendency = client.get("/api/v1/reports/pendency", headers=headers).json()
    assert pendency["total_cases"] >= 1

    # The drill-down rows agree with the headline count, and none of them
    # belong to another region.
    rows = client.get("/api/v1/officer/pendency", headers=headers).json()["rows"]
    assert len(rows) == pendency["total_cases"]
    assert {row["region"] for row in rows} <= {"NR"}


def test_document_report_flags_a_dated_document(client, as_user):
    headers = as_user("admin@demo.local")
    body = client.get("/api/v1/reports/documents", headers=headers).json()
    assert body["documents_dated"] >= 1
    dated = [row for row in body["rows"] if row["valid_to"] is not None]
    assert dated, "the seed writes valid_to on the lease deed"
    # Rows are ordered soonest-expiry first, undated last.
    days = [row["days_left"] for row in dated]
    assert days == sorted(days)
