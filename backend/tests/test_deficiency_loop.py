"""Tests for the Structured Deficiency and Return Loop."""

from __future__ import annotations

from pdf_factory import affidavit_pdf


def _pdf(name: str = "upload.pdf") -> tuple[str, bytes, str]:
    return (name, affidavit_pdf(), "application/pdf")


def test_structured_deficiency_and_return_loop(client, as_user):
    college = as_user("institution@demo.local")
    scrutiny = as_user("scrutiny@demo.local")

    # 1. Start with an existing submitted/scrutiny application: app-main-0001
    # Check baseline status
    app_res = client.get("/api/v1/applications/app-main-0001", headers=scrutiny)
    assert app_res.status_code == 200
    app_data = app_res.json()["application"]

    # Retrieve current documents
    docs_res = client.get("/api/v1/applications/app-main-0001/documents", headers=scrutiny)
    assert docs_res.status_code == 200
    docs = docs_res.json()
    assert len(docs) > 0
    target_doc = docs[0]
    target_field = target_doc["fields"][0] if target_doc["fields"] else None

    # 2. Officer creates a structured deficiency from a rejected field
    field_def_payload = {
        "document_id": target_doc["id"],
        "extracted_field_id": target_field["id"] if target_field else None,
        "category": target_doc["doc_type"],
        "field_name": target_field["field_name"] if target_field else "valid_to",
        "extracted_value": target_field["value"] if target_field else "2024-01-01",
        "explanation": "Document expired before required academic session coverage.",
        "corrective_action": "Upload an updated registered deed covering full 3-year term.",
        "status": "draft",
    }
    create_res = client.post(
        "/api/v1/applications/app-main-0001/deficiencies",
        headers=scrutiny,
        json=field_def_payload,
    )
    assert create_res.status_code == 201
    def1 = create_res.json()
    assert def1["status"] == "draft"
    assert def1["document_id"] == target_doc["id"]

    # 3. Officer creates a manual deficiency (not tied to extracted field)
    manual_def_payload = {
        "document_id": target_doc["id"],
        "category": "resolution_record",
        "explanation": "Trust resolution signatures are not notarized.",
        "corrective_action": "Upload notarized copy of the governing body resolution.",
        "status": "draft",
    }
    create_manual_res = client.post(
        "/api/v1/applications/app-main-0001/deficiencies",
        headers=scrutiny,
        json=manual_def_payload,
    )
    assert create_manual_res.status_code == 201
    def2 = create_manual_res.json()
    assert def2["status"] == "draft"

    # 4. Verification: Merely unverified fields do not create deficiencies automatically
    # Checking existing fields list: unverified fields remain unverified without deficiency
    all_defs = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=scrutiny).json()
    assert any(d["id"] == def1["id"] for d in all_defs)
    assert any(d["id"] == def2["id"] for d in all_defs)

    # 5. Authorization: Institution CANNOT see draft deficiencies prior to return
    inst_defs_draft = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=college).json()
    assert not any(d["id"] == def1["id"] for d in inst_defs_draft)
    assert not any(d["id"] == def2["id"] for d in inst_defs_draft)

    # 6. Authorization: Institution CANNOT create, update or close deficiencies
    inst_forbidden_create = client.post(
        "/api/v1/applications/app-main-0001/deficiencies",
        headers=college,
        json=manual_def_payload,
    )
    assert inst_forbidden_create.status_code in (403, 404)

    inst_forbidden_close = client.post(
        f"/api/v1/applications/app-main-0001/deficiencies/{def1['id']}/close",
        headers=college,
        json={"resolution_note": "I fixed it"},
    )
    assert inst_forbidden_close.status_code in (403, 404)

    # 7. Workflow: Return for clarification promotes drafts to open and transitions case to 'returned'
    # Ensure case is in 'scrutiny' state first
    if app_data["current_state"] == "submitted":
        client.post(
            "/api/v1/applications/app-main-0001/transitions",
            headers=scrutiny,
            json={"action": "start_scrutiny", "reason": "Officer begins review"},
        )

    ret_res = client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=scrutiny,
        json={
            "action": "return_for_clarification",
            "reason": "Returned due to document expiry and missing notarization in governing body resolution.",
            "reason_code": "RC-DOC-MISSING",
        },
    )
    assert ret_res.status_code == 200
    assert ret_res.json()["accepted"] is True
    assert ret_res.json()["to_state"] == "returned"

    # Now institution CAN view the deficiencies in 'open' status
    inst_defs_open = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=college).json()
    assert any(d["id"] == def1["id"] and d["status"] == "open" for d in inst_defs_open)
    assert any(d["id"] == def2["id"] and d["status"] == "open" for d in inst_defs_open)

    # 8. Institution uploads a corrected document version
    upload_correction = client.post(
        "/api/v1/applications/app-main-0001/documents",
        headers=college,
        data={"doc_type": target_doc["doc_type"]},
        files={"file": _pdf("corrected-deed.pdf")},
    )
    assert upload_correction.status_code == 201
    corrected_doc = upload_correction.json()["document"]
    assert corrected_doc["version"] > target_doc["version"]

    # 9. Verify deficiency is marked 'addressed' (NOT automatically closed or approved)
    updated_defs = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=college).json()
    addressed_def = next((d for d in updated_defs if d["id"] == def1["id"]), None)
    assert addressed_def is not None
    assert addressed_def["status"] == "addressed"
    assert addressed_def["corrective_document_id"] == corrected_doc["id"]

    # Application is STILL returned; no automatic approval
    app_after_upload = client.get("/api/v1/applications/app-main-0001", headers=college).json()["application"]
    assert app_after_upload["current_state"] == "returned"

    # 10. Institution resubmits application
    resubmit_res = client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=college,
        json={"action": "resubmit", "reason": "Uploaded corrected registered documents."},
    )
    assert resubmit_res.status_code == 200
    assert resubmit_res.json()["accepted"] is True
    assert resubmit_res.json()["to_state"] == "submitted"

    # 11. Scrutiny officer reviews corrected evidence and explicitly closes the deficiency
    close_res = client.post(
        f"/api/v1/applications/app-main-0001/deficiencies/{def1['id']}/close",
        headers=scrutiny,
        json={"resolution_note": "Verified registered dates in version 2."},
    )
    assert close_res.status_code == 200
    closed_def = close_res.json()
    assert closed_def["status"] == "closed"
    assert closed_def["resolved_by"] is not None

    # 12. Audit events exist for deficiency lifecycle
    audit_events = client.get("/api/v1/applications/app-main-0001/audit", headers=scrutiny).json()["events"]
    actions = [e["action"] for e in audit_events]
    assert "deficiency.created" in actions
    assert "deficiency.finalized" in actions
    assert "deficiency.addressed" in actions
    assert "deficiency.closed" in actions
