from __future__ import annotations

from datetime import date

from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.core.permissions import COMPETENT_AUTHORITY, SHC_MEMBER
from app.models import (
    AuditEvent,
    EvcReport,
    EvcVisit,
    FraudReferral,
    Region,
    Role,
    User,
    UserRoleAssignment,
)

APPLICATION_ID = "app-main-0001"


def _schedule(client, as_user) -> tuple[str, str]:
    headers = as_user("scrutiny@demo.local")
    committees = client.get("/api/v1/evc/committees", headers=headers).json()
    committee_id = committees[0]["id"]
    experts = client.get(
        f"/api/v1/applications/{APPLICATION_ID}/evc/committees/{committee_id}/experts",
        headers=headers,
    )
    assert experts.status_code == 200, experts.text
    expert_id = experts.json()[0]["id"]
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits",
        headers=headers,
        json={
            "scheduled_date": date(2026, 11, 12).isoformat(),
            "visit_mode": "physical",
            "venue": "Synthetic campus",
            "committee_id": committee_id,
            "expert_user_ids": [expert_id],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"], expert_id


def _upload_report(client, as_user, visit_id: str) -> str:
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report/document",
        headers=as_user("evc@demo.local"),
        files={"file": ("evc-report.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


def test_assigned_expert_can_submit_report_and_flag_nonpenal_referral(
    client, as_user, db
):
    visit_id, _expert_id = _schedule(client, as_user)
    document_id = _upload_report(client, as_user, visit_id)
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report",
        headers=as_user("evc@demo.local"),
        json={
            "document_id": document_id,
            "summary": "Synthetic site observations recorded by the committee.",
            "deficiency_present": True,
            "fraud_flag": True,
            "fraud_referral_reason": "Document authenticity requires competent review.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    report = db.get(EvcReport, body["id"])
    referral = db.get(FraudReferral, body["fraud_referral_id"])
    assert report is not None and report.deficiency_present and report.fraud_flag
    assert referral is not None and referral.status == "pending"

    history = client.get(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report",
        headers=as_user("institution@demo.local"),
    )
    assert history.status_code == 200
    assert history.json()["deficiency_present"] is True
    application = client.get(
        f"/api/v1/applications/{APPLICATION_ID}",
        headers=as_user("scrutiny@demo.local"),
    ).json()["application"]
    assert application["current_state"] == "scrutiny"

    regional = db.scalar(select(User).where(User.email == "regional@demo.local"))
    authority = db.scalar(
        select(Role).where(Role.name == COMPETENT_AUTHORITY)
    )
    assert regional is not None and authority is not None
    north = db.scalar(select(Region).where(Region.code == "NR"))
    assert north is not None
    db.add(
        UserRoleAssignment(
            user_id=regional.id,
            role_id=authority.id,
            scope_type="region",
            scope_id=north.id,
        )
    )
    shc_role = db.scalar(select(Role).where(Role.name == SHC_MEMBER))
    assert shc_role is not None
    db.add(
        UserRoleAssignment(
            user_id=regional.id,
            role_id=shc_role.id,
            scope_type="region",
            scope_id=north.id,
        )
    )
    db.commit()
    referrals = client.get("/api/v1/evc/fraud-referrals", headers=as_user("regional@demo.local"))
    assert referrals.status_code == 200, referrals.text
    assert referrals.json()[0]["id"] == referral.id
    assert referrals.json()[0]["penal_action_taken"] is False
    fraud_document = client.get(
        f"/api/v1/evc/fraud-referrals/{referral.id}/document",
        headers=as_user("regional@demo.local"),
    )
    assert fraud_document.status_code == 200
    visit = db.get(EvcVisit, visit_id)
    assert visit is not None
    visit.status = "completed"
    visit.completed_at = db.execute(select(EvcReport.created_at)).scalar_one()
    db.commit()
    shc_queue = client.get("/api/v1/shc/queue", headers=as_user("regional@demo.local"))
    assert shc_queue.status_code == 200, shc_queue.text
    assert shc_queue.json()["count"] == 1
    assert shc_queue.json()["rows"][0]["report_id"] == report.id
    shc_document = client.get(
        f"/api/v1/shc/queue/{report.id}/document",
        headers=as_user("regional@demo.local"),
    )
    assert shc_document.status_code == 200
    assert db.scalars(
        select(AuditEvent).where(
            AuditEvent.action.in_(("evc.report_submitted", "fraud.referral_created"))
        )
    ).all()


def test_unassigned_evc_member_cannot_upload_a_report(client, as_user):
    response = client.post(
        "/api/v1/applications/app-second-0002/evc/visits/missing/report/document",
        headers=as_user("evc@demo.local"),
        files={"file": ("evc-report.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 404


def test_fraud_flag_requires_reason_and_does_not_create_report(client, as_user, db):
    visit_id, _expert_id = _schedule(client, as_user)
    document_id = _upload_report(client, as_user, visit_id)
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report",
        headers=as_user("evc@demo.local"),
        json={
            "document_id": document_id,
            "deficiency_present": False,
            "fraud_flag": True,
        },
    )
    assert response.status_code == 422
    assert db.scalars(select(EvcReport)).first() is None
    assert db.scalars(select(FraudReferral)).first() is None
    rejected = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "evc.report_submission_rejected",
            AuditEvent.outcome == "rejected",
        )
    ).first()
    assert rejected is not None
