"""End-to-end API behaviour through the HTTP surface."""

from __future__ import annotations

from pdf_factory import lease_deed_pdf


def test_login_returns_token_roles_and_scope(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "scrutiny@demo.local", "password": "DemoPassw0rd!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["roles"] == ["scrutiny_officer"]
    assert "case.read" in body["user"]["permissions"]
    assert body["user"]["scope"]["assigned_cases_only"] is True


def test_login_rejects_a_bad_password(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "scrutiny@demo.local", "password": "wrong"},
    )
    assert response.status_code == 401


def test_health_reports_the_injected_clock(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["clock"].startswith("2026-10-22T09:00:00")


def test_compliance_returns_typed_outcomes(client, as_user):
    response = client.post(
        "/api/v1/applications/app-main-0001/compliance/evaluate",
        headers=as_user("institution@demo.local"),
    )
    assert response.status_code == 200
    findings = {row["rule_key"]: row for row in response.json()["findings"]}

    assert findings["LEASE_VALID_COVERS_PERIOD"]["outcome"] == "PASS"
    assert findings["LEASE_ISSUING_AUTHORITY"]["outcome"] == "PASS"
    assert findings["REQUIRED_DOC_AFFIDAVIT"]["outcome"] == "FAIL"
    assert findings["LEASE_DATE_CONSISTENCY"]["outcome"] == "NEEDS_REVIEW"
    assert findings["INSTITUTION_IDENTITY_MATCH"]["outcome"] == "PASS"
    assert findings["EXISTING_INSTITUTION_FACULTY_RATIO"]["outcome"] == "NOT_APPLICABLE"

    # A blocking FAIL with a documented reason, not a silent pass.
    blocking = {row["rule_key"] for row in response.json()["blocking_unmet"]}
    assert "REQUIRED_DOC_AFFIDAVIT" in blocking


def test_compliance_get_returns_the_latest_batch(client, as_user):
    headers = as_user("institution@demo.local")
    first = client.get("/api/v1/applications/app-main-0001/compliance", headers=headers)
    assert first.status_code == 200
    batch_id = first.json()["batch_id"]
    second = client.get("/api/v1/applications/app-main-0001/compliance", headers=headers)
    assert second.json()["batch_id"] == batch_id
    checks = second.json()["advisory_checks"]
    assert [item["rule_id"] for item in checks] == [
        "RULE-E01",
        "RULE-E02",
        "RULE-E03",
    ]
    assert all(
        item["outcome"] == "REVIEW REQUIRED" and item["advisory_only"]
        for item in checks
    )


def test_rehearsal_through_the_api(client, as_user):
    headers = as_user("institution@demo.local")
    response = client.post(
        "/api/v1/applications/app-main-0001/rehearsals",
        headers=headers,
        json={
            "overrides": {
                "documents.affidavit.document_id": "hypothetical",
                "documents.ownership_record.lease_expiry": "2028-03-31",
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["production_modified"] is False
    assert body["metrics"]["load_factor"] is None
    assert body["summary"]["resolved_findings"] == 2

    run = client.get(f"/api/v1/rehearsals/{body['run_id']}", headers=headers)
    assert run.status_code == 200
    assert run.json()["run_id"] == body["run_id"]


def test_rehearsal_rejects_a_workflow_override(client, as_user):
    response = client.post(
        "/api/v1/applications/app-main-0001/rehearsals",
        headers=as_user("institution@demo.local"),
        json={"overrides": {"application.current_state": "approved"}},
    )
    # OverrideRejected is a ValueError; FastAPI surfaces it as a server-side error
    # only if unhandled, so the handler in main.py returns 422.
    assert response.status_code == 422
    assert "not evidence" in response.json()["detail"]


def test_rejected_transition_is_visible_in_the_audit_timeline(client, as_user):
    headers = as_user("scrutiny@demo.local")
    response = client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=headers,
        json={"action": "schedule_evc", "reason": ""},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert any("affidavit" in reason for reason in body["reasons"])

    timeline = client.get("/api/v1/applications/app-main-0001/audit", headers=headers)
    assert timeline.status_code == 200
    events = timeline.json()["events"]
    rejected = [event for event in events if event["outcome"] == "rejected"]
    assert rejected
    assert rejected[-1]["action"] == "workflow.schedule_evc"
    assert rejected[-1]["before"] == {"state": "scrutiny"}

    verify = client.get("/api/v1/audit/verify", headers=headers)
    assert verify.json()["ok"] is True


def test_accepted_transition_through_the_api(client, as_user):
    headers = as_user("scrutiny@demo.local")
    response = client.post(
        "/api/v1/applications/app-existing-0003/transitions",
        headers=headers,
        json={"action": "approve", "reason": "Scrutiny complete"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["to_state"] == "approved"

    case = client.get("/api/v1/applications/app-existing-0003", headers=headers).json()
    assert case["application"]["current_state"] == "approved"


def test_document_upload_reads_values_from_the_uploaded_file(client, as_user):
    headers = as_user("institution@demo.local")
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=headers,
        data={"doc_type": "lease_deed"},
        files={"file": ("lease.pdf", lease_deed_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["extraction"]["simulated"] is False
    assert body["extraction"]["fields_extracted"] == 5

    values = {
        field["field_name"]: field["value"] for field in body["document"]["fields"]
    }
    # Dates are normalised to ISO because the rule engine compares them as
    # plain strings against application.cycle_end.
    assert values["valid_to"] == "2028-03-31"
    assert values["valid_from"] == "2026-04-01"
    assert values["lessee_name"] == "Example Institute of Technology"
    assert body["document"]["fields"][0]["verification_status"] == "unverified"

    documents = client.get(
        "/api/v1/applications/app-draft-0004/documents", headers=headers
    ).json()
    assert len(documents) == 1


def test_an_unreadable_file_is_accepted_with_an_honest_warning(client, as_user):
    """A corrupt PDF must not 500: the file is stored and nothing is claimed."""
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={"file": ("broken.pdf", b"%PDF-1.4 fake demo bytes", "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["extraction"]["fields_extracted"] == 0
    assert body["document"]["fields"] == []
    assert any("could not be opened" in w for w in body["extraction"]["warnings"])


def test_document_upload_rejects_unsupported_types(client, as_user):
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_officer_monitoring_endpoints(client, as_user):
    headers = as_user("regional@demo.local")
    dashboard = client.get("/api/v1/officer/dashboard", headers=headers)
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["role"] == "regional_officer"
    assert body["cases_in_scope"] >= 1

    ageing = client.get("/api/v1/officer/ageing", headers=headers).json()
    assert ageing["total"] == body["cases_in_scope"]
    assert sum(ageing["bands"].values()) == ageing["total"]

    escalations = client.get("/api/v1/officer/escalations", headers=headers).json()
    assert "rows" in escalations


def test_admin_can_run_the_deadline_sweep_and_read_alerts(client, as_user):
    admin = as_user("admin@demo.local")
    sweep = client.post("/api/v1/internal/deadline-sweep", headers=admin)
    assert sweep.status_code == 200
    assert sweep.json()["created"] > 0

    again = client.post("/api/v1/internal/deadline-sweep", headers=admin)
    assert again.json()["created"] == 0

    alerts = client.get("/api/v1/alerts", headers=admin)
    assert alerts.status_code == 200
    body = alerts.json()
    assert body["simulated"] is True
    assert body["alerts"]
    assert any(alert["deliveries"] for alert in body["alerts"])


def test_institution_cannot_run_the_deadline_sweep(client, as_user):
    response = client.post(
        "/api/v1/internal/deadline-sweep", headers=as_user("institution@demo.local")
    )
    assert response.status_code == 403
