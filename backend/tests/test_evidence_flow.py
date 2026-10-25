"""Evidence, institutions and undertaking flows through the HTTP surface."""

from __future__ import annotations

from pdf_factory import affidavit_pdf


def _pdf(name: str = "upload.pdf") -> tuple[str, bytes, str]:
    return (name, affidavit_pdf(), "application/pdf")


def test_institution_scope_is_enforced_on_the_institution_endpoint(client, as_user):
    own = client.get("/api/v1/institutions", headers=as_user("institution@demo.local"))
    assert own.status_code == 200
    assert len(own.json()) == 1
    assert own.json()[0]["aicte_id"] == "1-12345678"

    everything = client.get("/api/v1/institutions", headers=as_user("admin@demo.local"))
    assert everything.status_code == 200
    assert len(everything.json()) == 2


def test_route_catalogue_is_available_to_authenticated_users(client, as_user):
    response = client.get("/api/v1/workflow/routes", headers=as_user("admin@demo.local"))
    assert response.status_code == 200
    keys = {route["key"] for route in response.json()}
    # The four approval paths named in the problem statement.
    assert keys == {
        "new_technical",
        "existing_technical",
        "evc_only",
        "evc_sac_shc",
    }


def test_institution_can_create_a_draft_and_upload_evidence(client, as_user):
    headers = as_user("institution@demo.local")
    institution = client.get("/api/v1/institutions", headers=headers).json()[0]

    created = client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "institution_id": institution["id"],
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2027-28",
            "cycle_end": "2028-03-31",
        },
    )
    assert created.status_code == 201
    application_id = created.json()["id"]
    assert created.json()["current_state"] == "draft"

    upload = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        data={"doc_type": "affidavit"},
        files={"file": _pdf("affidavit.pdf")},
    )
    assert upload.status_code == 201
    body = upload.json()
    # The file really is read: the affidavit PDF above states an institution
    # name, an AICTE id, a document id and a swearing date, and all four come
    # back out of the file rather than out of a canned table.
    assert body["extraction"]["simulated"] is False
    assert body["extraction"]["fields_extracted"] == 4
    read_back = {
        field["field_name"]: field["value"] for field in body["document"]["fields"]
    }
    assert read_back == {
        "institution_name": "Example Institute of Technology",
        "aicte_id": "1-12345678",
        "document_id": "AFF-2026-0007",
        "notary_date": "2026-04-12",
    }
    # Values read by a machine are not evidence until a human confirms them.
    assert body["document"]["fields"][0]["verification_status"] == "unverified"
    assert {field["method"] for field in body["document"]["fields"]} == {"pdf_text"}

    documents = client.get(
        f"/api/v1/applications/{application_id}/documents", headers=headers
    )
    assert documents.status_code == 200
    assert len(documents.json()) == 1


def test_verifying_a_field_changes_verification_and_baseline(client, as_user):
    # app-second-0002 is in another region and has no scrutiny assignment, so use
    # the global administrator for this evidence check.
    headers = as_user("admin@demo.local")
    documents = client.get(
        "/api/v1/applications/app-second-0002/documents", headers=headers
    ).json()
    unverified = documents[0]["fields"][0]
    assert unverified["verification_status"] == "unverified"

    before = client.get(
        "/api/v1/applications/app-second-0002", headers=headers
    ).json()["application"]["baseline_version"]

    response = client.post(
        f"/api/v1/applications/app-second-0002/documents/"
        f"{documents[0]['id']}/fields/{unverified['id']}/verify",
        headers=headers,
        json={"verification_status": "verified", "note": "checked against original"},
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"

    evidence = client.get(
        "/api/v1/applications/app-second-0002/evidence", headers=headers
    ).json()
    path = f"documents.lease_deed.{unverified['field_name']}"
    assert evidence["verified"][path] is True

    after = client.get(
        "/api/v1/applications/app-second-0002", headers=headers
    ).json()["application"]["baseline_version"]
    assert after == before + 1


def test_uploaded_evidence_invalidates_a_stored_compliance_batch(client, as_user):
    headers = as_user("institution@demo.local")
    first = client.get(
        "/api/v1/applications/app-main-0001/compliance", headers=headers
    ).json()
    assert first["findings"]

    upload = client.post(
        "/api/v1/applications/app-main-0001/documents",
        headers=headers,
        data={"doc_type": "affidavit"},
        files={"file": _pdf("affidavit.pdf")},
    )
    assert upload.status_code == 201

    second = client.get(
        "/api/v1/applications/app-main-0001/compliance", headers=headers
    ).json()
    assert second["batch_id"] != first["batch_id"]
    findings = {row["rule_key"]: row for row in second["findings"]}
    assert findings["REQUIRED_DOC_AFFIDAVIT"]["outcome"] == "PASS"
    assert findings["REQUIRED_DOC_AFFIDAVIT"]["title"]
    assert findings["REQUIRED_DOC_AFFIDAVIT"]["severity"] in {"major", "minor"}


def test_institution_submits_and_officer_verifies_an_undertaking(client, as_user):
    institution = as_user("institution@demo.local")
    scrutiny = as_user("scrutiny@demo.local")
    items = client.get(
        "/api/v1/applications/app-main-0001/undertakings", headers=institution
    ).json()
    pending = next(item for item in items if item["status"] == "pending")

    submitted = client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/submit",
        headers=institution,
        json={"evidence_note": "Receipt acknowledged; registered deed to follow."},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    verified = client.post(
        f"/api/v1/applications/app-main-0001/undertakings/{pending['id']}/verify",
        headers=scrutiny,
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"


def test_an_officer_cannot_upload_evidence_without_the_permission(client, as_user):
    response = client.post(
        "/api/v1/applications/app-main-0001/documents",
        headers=as_user("scrutiny@demo.local"),
        data={"doc_type": "affidavit"},
        files={"file": _pdf()},
    )
    assert response.status_code == 403


def test_institution_upload_visible_to_authorized_checker_roles(client, as_user):
    """Uploaded documents from Institution role are visible and readable to authorized checkers/authorities."""
    college = as_user("institution@demo.local")
    scrutiny = as_user("scrutiny@demo.local")
    supervisor = as_user("supervisor@demo.local")
    regional = as_user("regional@demo.local")

    # 1. Institution uploads a supporting document
    upload = client.post(
        "/api/v1/applications/app-main-0001/documents",
        headers=college,
        data={"doc_type": "affidavit"},
        files={"file": _pdf("reg-test-affidavit.pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["document"]["id"]

    # 2. Scrutiny officer can retrieve and view the uploaded document
    docs_scrutiny = client.get(
        "/api/v1/applications/app-main-0001/documents", headers=scrutiny
    )
    assert docs_scrutiny.status_code == 200
    doc_names = [d["file_name"] for d in docs_scrutiny.json()]
    assert "reg-test-affidavit.pdf" in doc_names

    # 3. Supervisory officer (Authority role) can retrieve and view the documents
    docs_supervisor = client.get(
        "/api/v1/applications/app-main-0001/documents", headers=supervisor
    )
    assert docs_supervisor.status_code == 200
    assert any(d["id"] == doc_id for d in docs_supervisor.json())

    # 4. Regional officer (Authority role) can retrieve and view the documents
    docs_regional = client.get(
        "/api/v1/applications/app-main-0001/documents", headers=regional
    )
    assert docs_regional.status_code == 200
    assert any(d["id"] == doc_id for d in docs_regional.json())

    # 5. Content download succeeds for authorized officers
    content_scrutiny = client.get(
        f"/api/v1/applications/app-main-0001/documents/{doc_id}/content",
        headers=scrutiny,
    )
    assert content_scrutiny.status_code == 200

    content_supervisor = client.get(
        f"/api/v1/applications/app-main-0001/documents/{doc_id}/content",
        headers=supervisor,
    )
    assert content_supervisor.status_code == 200

    # 6. Unauthorized / out-of-scope cannot access
    unassigned = client.get(
        "/api/v1/applications/app-second-0002/documents", headers=scrutiny
    )
    assert unassigned.status_code == 404

    unauthenticated = client.get("/api/v1/applications/app-main-0001/documents")
    assert unauthenticated.status_code == 401

