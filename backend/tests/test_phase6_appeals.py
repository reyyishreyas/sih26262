from __future__ import annotations

from datetime import timedelta

from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.core.permissions import EXECUTIVE_COMMITTEE_MEMBER
from app.models import (
    Application,
    AuditEvent,
    Document,
    Region,
    Role,
    ScrutinyOverallResult,
    User,
    UserRoleAssignment,
    WorkflowTransition,
)

APPLICATION_ID = "app-existing-0003"


def _rejected_with_speaking_order(client, as_user, db, clock):
    application = db.get(Application, APPLICATION_ID)
    regional_user = db.scalar(select(User).where(User.email == "regional@demo.local"))
    executive_role = db.scalar(select(Role).where(Role.name == EXECUTIVE_COMMITTEE_MEMBER))
    north = db.scalar(select(Region).where(Region.code == "NR"))
    assert application is not None and regional_user is not None and executive_role is not None and north is not None
    db.add(UserRoleAssignment(
        user_id=regional_user.id, role_id=executive_role.id,
        scope_type="region", scope_id=north.id,
    ))
    db.add(ScrutinyOverallResult(
        application_id=application.id,
        result="nil_deficiency",
        remarks="Human scrutiny outcome for the appeal-flow fixture.",
        recorded_by=regional_user.id,
    ))
    db.commit()
    regional = as_user("regional@demo.local")
    uploaded = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/documents/executive-speaking-orders",
        headers=regional,
        files={"file": ("order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    order_id = uploaded.json()["document"]["id"]
    decision = client.post(
        f"/api/v1/executive-committee/applications/{APPLICATION_ID}/decision",
        headers=regional,
        json={
            "outcome": "rejected",
            "speaking_order_document_id": order_id,
            "reason": "The committee recorded a human rejection decision.",
        },
    )
    assert decision.status_code == 200 and decision.json()["accepted"]
    return order_id


def _upload_doc(client, headers, doc_type: str, filename: str) -> str:
    result = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/documents",
        headers=headers,
        data={"doc_type": doc_type},
        files={"file": (filename, affidavit_pdf(), "application/pdf")},
    )
    assert result.status_code == 201, result.text
    return result.json()["document"]["id"]


def _submit_appeal(client, as_user):
    institution = as_user("institution@demo.local")
    evidence_id = _upload_doc(client, institution, "appeal_supporting_evidence", "appeal-evidence.pdf")
    result = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/appeals",
        headers=institution,
        json={
            "grounds": "The institution disputes the deficiencies listed in the uploaded decision.",
            "supporting_document_ids": [evidence_id],
        },
    )
    assert result.status_code == 201, result.text
    return institution, result.json()


def test_full_appeal_sac_hearing_and_council_final_decision(
    client, as_user, db, clock
):
    order_id = _rejected_with_speaking_order(client, as_user, db, clock)
    institution, appeal = _submit_appeal(client, as_user)
    assert appeal["status"] == "submitted"
    assert appeal["appeal_deadline"]
    assert len(appeal["evidence"]) == 1
    appeal_id = appeal["id"]

    rep_one = _upload_doc(client, institution, "appeal_representative_id", "rep-one-id.pdf")
    rep_two = _upload_doc(client, institution, "appeal_representative_id", "rep-two-id.pdf")
    representatives = client.post(
        f"/api/v1/appeals/{appeal_id}/representatives",
        headers=institution,
        json={"representatives": [
            {"name": "Demo Director", "institutional_role": "Director", "id_document_id": rep_one, "authorization_attested": True},
            {"name": "Demo Trustee", "institutional_role": "Trustee", "id_document_id": rep_two, "authorization_attested": True},
        ]},
    )
    assert representatives.status_code == 200, representatives.text

    hearing_at = clock.now() + timedelta(days=2)
    schedule = client.post(
        f"/api/v1/sac/appeals/{appeal_id}/schedule",
        headers=as_user("sac@demo.local"),
        json={"hearing_at": hearing_at.isoformat(), "venue": "Synthetic hearing room"},
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["status"] == "scheduled"
    assert client.get("/api/v1/council/appeals", headers=as_user("council@demo.local")).json()["rows"] == []

    clock.advance(days=2)
    hearing = client.post(
        f"/api/v1/sac/appeals/{appeal_id}/hearing-record",
        headers=as_user("sac@demo.local"),
        json={"recommendation": "Recommend that the Council grant the appeal."},
    )
    assert hearing.status_code == 200, hearing.text
    assert hearing.json()["status"] == "heard"
    assert len(hearing.json()["representatives"]) == 2
    council_queue = client.get("/api/v1/council/appeals", headers=as_user("council@demo.local"))
    assert council_queue.status_code == 200
    assert council_queue.json()["rows"][0]["id"] == appeal_id

    council_order = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/documents/council-decision-orders",
        headers=as_user("council@demo.local"),
        files={"file": ("council-order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert council_order.status_code == 201, council_order.text
    final = client.post(
        f"/api/v1/council/appeals/{appeal_id}/decision",
        headers=as_user("council@demo.local"),
        json={
            "outcome": "approved",
            "decision": "Council grants the appeal and approves the application.",
            "decision_document_id": council_order.json()["document"]["id"],
        },
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "decided"
    assert final.json()["council_outcome"] == "approved"
    assert db.get(Application, APPLICATION_ID).current_state == "approved"
    assert db.scalars(select(WorkflowTransition).where(
        WorkflowTransition.application_id == APPLICATION_ID,
        WorkflowTransition.action == "council_grant_approval",
    )).first()
    actions = set(db.scalars(select(AuditEvent.action)).all())
    assert {"appeal.submitted", "appeal.hearing_scheduled", "appeal.sac_recommendation_recorded", "appeal.council_decision_recorded"} <= actions
    assert db.get(Document, order_id).doc_type == "speaking_order"


def test_late_and_duplicate_appeals_are_refused_and_audited(client, as_user, db, clock):
    _rejected_with_speaking_order(client, as_user, db, clock)
    clock.advance(days=7, seconds=1)
    institution = as_user("institution@demo.local")
    evidence_id = _upload_doc(client, institution, "appeal_supporting_evidence", "late-evidence.pdf")
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/appeals",
        headers=institution,
        json={"grounds": "Late submission check for the verified period.", "supporting_document_ids": [evidence_id]},
    )
    assert response.status_code == 409
    assert db.scalars(select(AuditEvent).where(AuditEvent.action == "appeal.submission_rejected")).first()


def test_appeal_at_seven_day_deadline_is_accepted_but_a_second_filing_is_not(
    client, as_user, db, clock
):
    _rejected_with_speaking_order(client, as_user, db, clock)
    clock.advance(days=7)
    institution = as_user("institution@demo.local")
    evidence_id = _upload_doc(client, institution, "appeal_supporting_evidence", "deadline-evidence.pdf")
    payload = {
        "grounds": "The institution disputes the deficiencies listed in the decision.",
        "supporting_document_ids": [evidence_id],
    }
    first = client.post(f"/api/v1/applications/{APPLICATION_ID}/appeals", headers=institution, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "submitted"
    second = client.post(f"/api/v1/applications/{APPLICATION_ID}/appeals", headers=institution, json=payload)
    assert second.status_code == 409
    rejected_events = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "appeal.submission_rejected",
    )).all()
    assert any(event.after.get("reason") == "appeal_already_filed" for event in rejected_events)


def test_council_and_sac_roles_have_no_general_document_access():
    from app.core.permissions import COUNCIL_MEMBER, ROLE_PERMISSIONS, SAC_MEMBER

    assert "document.read" not in ROLE_PERMISSIONS[SAC_MEMBER]
    assert "document.read" not in ROLE_PERMISSIONS[COUNCIL_MEMBER]
    assert "document.upload" not in ROLE_PERMISSIONS[COUNCIL_MEMBER]
