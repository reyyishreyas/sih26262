"""RBAC + scope: the server decides, not the dashboard."""

from __future__ import annotations

from sqlalchemy import select

from app.models import User, UserRoleAssignment


def test_institution_rep_sees_only_its_own_institution(client, as_user):
    response = client.get("/api/v1/applications", headers=as_user("institution@demo.local"))
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert ids == {"app-main-0001", "app-existing-0003", "app-draft-0004"}


def test_case_officer_sees_only_assigned_cases(client, as_user):
    response = client.get("/api/v1/applications", headers=as_user("scrutiny@demo.local"))
    ids = {row["id"] for row in response.json()}
    assert ids == {"app-main-0001", "app-existing-0003"}


def test_case_officer_cannot_open_an_unassigned_case(client, as_user):
    response = client.get(
        "/api/v1/applications/app-second-0002", headers=as_user("scrutiny@demo.local")
    )
    assert response.status_code == 404


def test_committee_member_sees_only_committee_cases(client, as_user):
    response = client.get("/api/v1/applications", headers=as_user("evc@demo.local"))
    ids = {row["id"] for row in response.json()}
    assert ids == {"app-main-0001"}


def test_region_query_parameter_cannot_widen_scope(client, as_user):
    response = client.get(
        "/api/v1/officer/pendency?region=SR", headers=as_user("regional@demo.local")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope_enforced"] is True
    assert body["count"] == 0
    assert all(row["region"] == "NR" for row in body["rows"])


def test_dashboard_totals_reconcile_with_drilldown(client, as_user):
    headers = as_user("regional@demo.local")
    dashboard = client.get("/api/v1/officer/dashboard", headers=headers).json()
    pendency = client.get("/api/v1/officer/pendency", headers=headers).json()
    assert dashboard["cases_in_scope"] == pendency["count"]

    scrutiny = as_user("scrutiny@demo.local")
    dashboard = client.get("/api/v1/officer/dashboard", headers=scrutiny).json()
    pendency = client.get("/api/v1/officer/pendency", headers=scrutiny).json()
    assert dashboard["cases_in_scope"] == pendency["count"]


def test_role_dashboards_expose_reconciling_scoped_application_drilldowns(client, as_user):
    for email in (
        "institution@demo.local",
        "scrutiny@demo.local",
        "regional@demo.local",
        "regulation-bureau@demo.local",
    ):
        response = client.get("/api/v1/officer/dashboard", headers=as_user(email))
        assert response.status_code == 200, (email, response.text)
        dashboard = response.json()
        drilldowns = dashboard["drilldowns"]
        in_scope = {row["application_id"] for row in drilldowns["cases_in_scope"]}
        assert len(in_scope) == dashboard["cases_in_scope"]
        for metric in (
            "overdue_obligations",
            "upcoming_deadlines_7d",
            "open_alerts",
            "escalated_alerts",
            "needs_review_cases",
            "my_assignments",
        ):
            assert len(drilldowns[metric]) == dashboard[metric], (email, metric)
            assert {row["application_id"] for row in drilldowns[metric]} <= in_scope
        for state, count in dashboard["cases_by_state"].items():
            rows = drilldowns["cases_by_state"][state]
            assert len(rows) == count
            assert {row["application_id"] for row in rows} <= in_scope

    institution = as_user("institution@demo.local")
    dashboard = client.get("/api/v1/officer/dashboard", headers=institution).json()
    assert dashboard["cases_in_scope"] == 3
    assert client.get("/api/v1/reports", headers=institution).status_code == 403

    bureau = as_user("regulation-bureau@demo.local")
    assert client.get("/api/v1/officer/dashboard", headers=bureau).status_code == 200
    assert client.get("/api/v1/reports", headers=bureau).status_code == 403

def test_revoking_a_role_takes_effect_on_the_next_request(client, as_user, db):
    headers = as_user("scrutiny@demo.local")
    assert client.get("/api/v1/applications", headers=headers).status_code == 200

    user = db.scalars(select(User).where(User.email == "scrutiny@demo.local")).one()
    assignment = db.scalars(
        select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)
    ).first()
    admin = as_user("admin@demo.local")
    response = client.post(
        f"/api/v1/admin/assignments/{assignment.id}/revoke", headers=admin
    )
    assert response.status_code == 200

    assert client.get("/api/v1/applications", headers=headers).status_code == 403


def test_non_admin_cannot_administer_access(client, as_user):
    headers = as_user("regional@demo.local")
    assert client.get("/api/v1/admin/roles", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403


def test_rehearsal_cannot_bypass_case_scope(client, as_user):
    response = client.post(
        "/api/v1/applications/app-second-0002/rehearsals",
        headers=as_user("institution@demo.local"),
        json={"overrides": {}},
    )
    assert response.status_code == 404


def test_missing_token_is_rejected(client):
    assert client.get("/api/v1/applications").status_code == 401
