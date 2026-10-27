from __future__ import annotations

from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.models import Application, AuditEvent, ReopeningRequest, User, WorkflowTransition
from app.services.authorization_service import effective_access
from app.services.workflow_service import request_transition

APP_ID = "app-existing-0003"


def _upload(client, headers, doc_type, name):
    response = client.post(
        f"/api/v1/applications/{APP_ID}/documents",
        headers=headers,
        data={"doc_type": doc_type},
        files={"file": (name, affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


def test_reopening_requires_ca_review_and_verified_payment_before_state_reopens(
    client, as_user, db
):
    app = db.get(Application, APP_ID)
    app.current_state = "submitted"
    app.status = "submitted"
    db.commit()
    institution = as_user("institution@demo.local")
    ca = as_user("competent-authority@demo.local")
    resolution = _upload(client, institution, "reopening_resolution", "resolution.pdf")
    response = client.post(
        f"/api/v1/applications/{APP_ID}/reopening", headers=institution,
        json={"reason": "The institution identified an error in the submitted application.",
              "resolution_document_id": resolution},
    )
    assert response.status_code == 201, response.text
    request_id = response.json()["id"]
    assert db.get(Application, APP_ID).current_state == "submitted"
    downloaded = client.get(
        f"/api/v1/reopening/{request_id}/documents/{resolution}", headers=ca,
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["x-content-sha256"]

    notice = _upload(client, institution, "public_notice", "notice.pdf")
    review = client.post(
        f"/api/v1/reopening/{request_id}/review", headers=ca,
        json={"approved": True, "reason": "Filing date confirmed against the applicable notice.",
              "public_notice_document_id": notice},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "approved_pending_payment"

    payment = _upload(client, institution, "reopening_payment_evidence", "payment.pdf")
    submitted = client.post(
        f"/api/v1/reopening/{request_id}/payment", headers=institution,
        json={"evidence_document_id": payment},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "payment_submitted"

    verified = client.post(
        f"/api/v1/reopening/{request_id}/payment-review", headers=ca,
        json={"verified": True, "reason": "TER and applicable late-penalty payment evidence verified."},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "resumed"
    db.expire_all()
    assert db.get(Application, APP_ID).current_state == "returned"
    assert db.scalars(select(WorkflowTransition).where(
        WorkflowTransition.application_id == APP_ID,
        WorkflowTransition.action == "reopen_application",
    )).first()
    actions = set(db.scalars(select(AuditEvent.action)).all())
    assert {"reopening.requested", "reopening.reviewed", "reopening.payment_submitted",
            "reopening.resumed", "reopening.document_accessed"} <= actions
    assert db.get(ReopeningRequest, request_id).payment_verified_at is not None


def test_one_time_request_and_payment_gate_are_enforced(client, as_user, db):
    app = db.get(Application, APP_ID)
    app.current_state = "submitted"
    app.status = "submitted"
    db.commit()
    institution = as_user("institution@demo.local")
    resolution = _upload(client, institution, "reopening_resolution", "resolution.pdf")
    payload = {"reason": "The institution identified an error in the submitted application.",
               "resolution_document_id": resolution}
    first = client.post(f"/api/v1/applications/{APP_ID}/reopening", headers=institution, json=payload)
    second = client.post(f"/api/v1/applications/{APP_ID}/reopening", headers=institution, json=payload)
    assert first.status_code == 201
    assert second.status_code == 409
    assert db.get(Application, APP_ID).current_state == "submitted"


def test_reopen_transition_cannot_bypass_request_and_payment_review(client, as_user, db):
    app = db.get(Application, APP_ID)
    app.current_state = "submitted"
    app.status = "submitted"
    db.commit()
    result = client.post(
        f"/api/v1/applications/{APP_ID}/transitions",
        headers=as_user("competent-authority@demo.local"),
        json={"action": "reopen_application", "reason": "Attempted direct reopening bypass."},
    )
    assert result.status_code == 403
    ca_user = db.scalar(select(User).where(User.email == "competent-authority@demo.local"))
    assert ca_user is not None
    decision = request_transition(
        db, effective_access(db, ca_user), APP_ID, "reopen_application",
        "Attempted direct reopening bypass.",
    )
    assert decision.accepted is False
    assert "verification is required" in decision.reasons[0]
    db.expire_all()
    assert db.get(Application, APP_ID).current_state == "submitted"
