from __future__ import annotations

from pdf_factory import affidavit_pdf
from sqlalchemy import select
from test_phase6_shc import _completed_deficiency_report

from app.core.clock import iso
from app.core.permissions import EXECUTIVE_COMMITTEE_MEMBER, ROLE_PERMISSIONS
from app.models import (
    Application,
    AuditEvent,
    Document,
    Region,
    Role,
    ScrutinyOverallResult,
    ShcHearing,
    User,
    UserRoleAssignment,
    WorkflowTransition,
)

APPLICATION_ID = "app-main-0001"


def _ready_for_decision(client, as_user, db, clock) -> str:
    report_id, _report_document_id = _completed_deficiency_report(
        client, as_user, db, clock
    )
    regional = db.scalar(select(User).where(User.email == "regional@demo.local"))
    role = db.scalar(
        select(Role).where(Role.name == EXECUTIVE_COMMITTEE_MEMBER)
    )
    assert regional is not None and role is not None
    db.add(
        ShcHearing(
            report_id=report_id,
            scheduled_date=clock.now().date(),
            visit_mode="physical",
            venue="Synthetic venue",
            status="completed",
            scheduled_by=regional.id,
            compliance_record="Human-recorded compliance review",
            recommendation="Place before the Executive Committee",
            recorded_by=regional.id,
            recorded_at=clock.now(),
            created_at=clock.now(),
        )
    )
    application = db.get(Application, APPLICATION_ID)
    assert application is not None
    application.route_key = "evc_sac_shc"
    application.current_state = "sac_review"
    application.status = "sac_review"
    db.commit()
    return report_id


def test_executive_decision_links_speaking_order_and_starts_verified_appeal_clock(
    client, as_user, db, clock
):
    _ready_for_decision(client, as_user, db, clock)
    headers = as_user("regional@demo.local")
    queue = client.get("/api/v1/executive-committee/queue", headers=headers)
    assert queue.status_code == 200, queue.text
    item = next(row for row in queue.json()["rows"] if row["application_id"] == APPLICATION_ID)
    assert item["readiness"] == "shc_recommendation"
    assert item["decision_actions"] == ["approve", "reject"]

    uploaded = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/documents/executive-speaking-orders",
        headers=headers,
        files={"file": ("speaking-order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = db.get(Document, uploaded.json()["document"]["id"])
    assert document is not None and document.doc_type == "speaking_order"
    upload_time = document.uploaded_at
    clock.advance(days=1)

    response = client.post(
        f"/api/v1/executive-committee/applications/{APPLICATION_ID}/decision",
        headers=headers,
        json={
            "outcome": "rejected",
            "speaking_order_document_id": document.id,
            "reason": "Human decision recorded in the uploaded Speaking Order.",
            "expected_baseline_version": db.get(Application, APPLICATION_ID).baseline_version,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert response.json()["to_state"] == "rejected"
    transition = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == APPLICATION_ID,
            WorkflowTransition.action == "reject",
        )
    ).first()
    assert transition is not None
    assert transition.speaking_order_document_id == document.id

    appeal = client.get(
        f"/api/v1/applications/{APPLICATION_ID}/appeal-window", headers=headers
    )
    assert appeal.status_code == 200, appeal.text
    assert appeal.json()["decision_at"] == iso(transition.created_at)
    assert appeal.json()["decision_at"] != iso(upload_time)
    assert appeal.json()["advisory_only"] is False
    assert appeal.json()["placeholder"] is False
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "workflow.reject")
    ).first()


def test_executive_role_has_narrow_scope_and_nonexecutive_cannot_upload_order(
    client, as_user
):
    permissions = set(ROLE_PERMISSIONS[EXECUTIVE_COMMITTEE_MEMBER])
    assert "case.read" not in permissions
    assert "document.read" not in permissions
    assert "document.upload" not in permissions
    response = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/documents/executive-speaking-orders",
        headers=as_user("evc@demo.local"),
        files={"file": ("speaking-order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 403


def test_nil_deficiency_scrutiny_record_enters_executive_queue(client, as_user, db):
    regional = db.scalar(select(User).where(User.email == "regional@demo.local"))
    role = db.scalar(select(Role).where(Role.name == EXECUTIVE_COMMITTEE_MEMBER))
    north = db.scalar(select(Region).where(Region.code == "NR"))
    application = db.get(Application, APPLICATION_ID)
    assert regional is not None and role is not None and north is not None
    assert application is not None
    application.route_key = "existing_technical"
    db.add(
        UserRoleAssignment(
            user_id=regional.id,
            role_id=role.id,
            scope_type="region",
            scope_id=north.id,
        )
    )
    db.add(
        ScrutinyOverallResult(
            application_id=APPLICATION_ID,
            result="nil_deficiency",
            remarks="Human-recorded nil-deficiency result",
            recorded_by=regional.id,
        )
    )
    db.commit()
    queue = client.get(
        "/api/v1/executive-committee/queue",
        headers=as_user("regional@demo.local"),
    )
    assert queue.status_code == 200, queue.text
    row = next(
        item for item in queue.json()["rows"] if item["application_id"] == APPLICATION_ID
    )
    assert row["readiness"] == "nil_list"
    assert row["decision_actions"] == ["approve", "reject"]


def test_executive_decision_rejects_document_from_another_case(
    client, as_user, db, clock
):
    report_id = _ready_for_decision(client, as_user, db, clock)
    regional = db.scalar(select(User).where(User.email == "regional@demo.local"))
    institution = db.scalar(select(Application).where(Application.id == "app-second-0002"))
    assert regional is not None and institution is not None
    from app.services.seed import _add_document

    wrong_order = _add_document(
        db,
        application=institution,
        doc_type="speaking_order",
        file_name="wrong-case-order.pdf",
        fields=[],
        uploaded_at=clock.now(),
    )
    db.commit()
    response = client.post(
        f"/api/v1/executive-committee/applications/{APPLICATION_ID}/decision",
        headers=as_user("regional@demo.local"),
        json={
            "outcome": "rejected",
            "speaking_order_document_id": wrong_order.id,
            "reason": "Attempt using unrelated order.",
        },
    )
    assert response.status_code == 422
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "executive.decision_rejected")
    ).first()
    assert db.get(Application, APPLICATION_ID).current_state == "sac_review"
    assert report_id
