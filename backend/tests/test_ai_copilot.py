"""Tests for Evidence-Grounded AI Extraction and Deterministic AI Copilot Engine."""

from __future__ import annotations

from pdf_factory import text_pdf


def sample_lease_agreement_pdf(
    *,
    lessor: str = "DLF CyberCity Developers Ltd",
    lessee: str = "Example Institute of Technology",
    address: str = "Plot 42, Sector 18, Institutional Area, New Delhi 110001",
    expiry_date: str = "31 December 2023",  # Expired date to trigger Copilot rule 1
) -> bytes:
    return text_pdf(
        [
            [
                "COMMERCIAL LEASE AGREEMENT",
                f"Lessor: {lessor}",
                f"Lessee: {lessee}",
                f"Property address: {address}",
                f"Expiry date: {expiry_date}",
            ]
        ]
    )


def test_evidence_grounded_ai_extraction_and_copilot_deficiency(client, as_user):
    college = as_user("institution@demo.local")
    scrutiny = as_user("scrutiny@demo.local")

    # 1. Institution uploads a 'lease_agreement' PDF with an expired date and mismatched lessee
    pdf_bytes = sample_lease_agreement_pdf(
        lessor="DLF CyberCity Developers Ltd",
        lessee="Mismatched College of Engineering",  # Triggers Copilot rule 2 (lessee mismatch)
        address="Plot 42, Sector 18, Institutional Area, New Delhi",
        expiry_date="31 December 2023",  # Triggers Copilot rule 1 (expired date)
    )

    upload_res = client.post(
        "/api/v1/applications/app-main-0001/documents",
        headers=college,
        data={"doc_type": "lease_agreement"},
        files={"file": ("lease_agreement.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 201
    doc_data = upload_res.json()["document"]
    assert doc_data["doc_type"] == "lease_agreement"

    # 2. Check that the extracted fields contain: value, source_quote, and ai_reasoning
    fields = {f["field_name"]: f for f in doc_data["fields"]}
    assert "lessor_name" in fields
    assert "lessee_name" in fields
    assert "property_address" in fields
    assert "valid_to" in fields

    valid_to_field = fields["valid_to"]
    val_json = valid_to_field["value"]
    assert isinstance(val_json, dict)
    assert "value" in val_json
    assert "source_quote" in val_json
    assert "ai_reasoning" in val_json
    assert "31 December 2023" in val_json["source_quote"] or "Expiry date" in val_json["source_quote"]

    lessee_field = fields["lessee_name"]
    lessee_json = lessee_field["value"]
    assert isinstance(lessee_json, dict)
    assert "Mismatched College of Engineering" in lessee_json["value"]
    assert "source_quote" in lessee_json
    assert "ai_reasoning" in lessee_json

    # 3. Deterministic AI Copilot Engine: check that draft Deficiencies were automatically created
    defs_res = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=scrutiny)
    assert defs_res.status_code == 200
    all_defs = defs_res.json()

    # Find the AI Copilot drafted deficiencies
    copilot_defs = [d for d in all_defs if "AI Copilot Flag:" in d["explanation"]]
    assert len(copilot_defs) >= 2  # Both Expiry date and Lessee mismatch rules fired

    expiry_def = next((d for d in copilot_defs if d["field_name"] == "valid_to"), None)
    assert expiry_def is not None
    assert expiry_def["status"] == "draft"  # Drafted for officer review
    assert "quoted:" in expiry_def["explanation"] or "Expiry date" in expiry_def["explanation"]

    lessee_def = next((d for d in copilot_defs if d["field_name"] == "lessee_name"), None)
    assert lessee_def is not None
    assert lessee_def["status"] == "draft"
    assert "Mismatched College of Engineering" in lessee_def["explanation"]

    # 4. Critical requirement: AI did NOT auto-approve or auto-reject the application
    app_res = client.get("/api/v1/applications/app-main-0001", headers=scrutiny)
    app = app_res.json()["application"]
    assert app["current_state"] not in ("approved", "rejected")

    # 5. Officer reviews the drafted deficiencies and returns the application
    if app["current_state"] == "submitted":
        client.post(
            "/api/v1/applications/app-main-0001/transitions",
            headers=scrutiny,
            json={"action": "start_scrutiny", "reason": "Begin scrutiny"},
        )

    ret_res = client.post(
        "/api/v1/applications/app-main-0001/transitions",
        headers=scrutiny,
        json={
            "action": "return_for_clarification",
            "reason": "AI Copilot flagged expired lease and mismatched lessee entity.",
            "reason_code": "RC-DOC-MISSING",
        },
    )
    assert ret_res.status_code == 200
    assert ret_res.json()["accepted"] is True
    assert ret_res.json()["to_state"] == "returned"

    # 6. Verify that on return, the copilot deficiencies are promoted to 'open' and visible to institution
    inst_defs = client.get("/api/v1/applications/app-main-0001/deficiencies", headers=college).json()
    open_copilot = [d for d in inst_defs if "AI Copilot Flag:" in d["explanation"] and d["status"] == "open"]
    assert len(open_copilot) >= 2
