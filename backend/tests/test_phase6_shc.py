from __future__ import annotations

from datetime import date

from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.core.permissions import EXECUTIVE_COMMITTEE_MEMBER, SHC_MEMBER
from app.models import (
    AuditEvent,
    EvcVisit,
    Region,
    Role,
    User,
    UserRoleAssignment,
)

APPLICATION_ID = "app-main-0001"


def _completed_deficiency_report(client, as_user, db, clock) -> tuple[str, str]:
    officer = as_user("regional@demo.local")
    committees = client.get("/api/v1/evc/committees", headers=officer).json()
    committee = next(row for row in committees if row["region_code"] == "NR")
    experts = client.get(
        f"/api/v1/applications/{APPLICATION_ID}/evc/committees/{committee['id']}/experts",
        headers=officer,
    ).json()
    scheduled = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits",
        headers=officer,
        json={
            "scheduled_date": "2026-10-23",
            "visit_mode": "physical",
            "venue": "Synthetic site",
            "committee_id": committee["id"],
            "expert_user_ids": [experts[0]["id"]],
        },
    )
    assert scheduled.status_code == 201, scheduled.text
    visit_id = scheduled.json()["id"]
    evc_headers = as_user("evc@demo.local")
    uploaded = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report/document",
        headers=evc_headers,
        files={"file": ("evc-report.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    report = client.post(
        f"/api/v1/applications/{APPLICATION_ID}/evc/visits/{visit_id}/report",
        headers=evc_headers,
        json={
            "document_id": uploaded.json()["document"]["id"],
            "summary": "Synthetic committee report",
            "deficiency_present": True,
        },
    )
    assert report.status_code == 201, report.text
    visit = db.get(EvcVisit, visit_id)
    assert visit is not None
    visit.status = "completed"
    visit.completed_at = clock.now()
    db.commit()
    regional_user = db.scalar(select(User).where(User.email == "regional@demo.local"))
    region = db.scalar(select(Region).where(Region.code == "NR"))
    assert regional_user is not None and region is not None
    for role_name in (SHC_MEMBER, EXECUTIVE_COMMITTEE_MEMBER):
        role = db.scalar(select(Role).where(Role.name == role_name))
        assert role is not None
        db.add(
            UserRoleAssignment(
                user_id=regional_user.id,
                role_id=role.id,
                scope_type="region",
                scope_id=region.id,
            )
        )
    db.commit()
    return report.json()["id"], uploaded.json()["document"]["id"]


def test_shc_hearing_records_human_recommendation_for_executive_queue(
    client, as_user, db, clock
):
    report_id, _document_id = _completed_deficiency_report(client, as_user, db, clock)
    headers = as_user("regional@demo.local")
    scheduled = client.post(
        f"/api/v1/shc/queue/{report_id}/hearing",
        headers=headers,
        json={
            "scheduled_date": "2026-11-01",
            "visit_mode": "online",
            "meeting_url": "https://meet.example.test/shc-room",
        },
    )
    assert scheduled.status_code == 201, scheduled.text
    assert scheduled.json()["status"] == "scheduled"
    queue = client.get("/api/v1/shc/queue", headers=headers)
    assert queue.status_code == 200
    item = next(row for row in queue.json()["rows"] if row["report_id"] == report_id)
    assert item["hearing"]["scheduled_date"] == "2026-11-01"

    too_early = client.post(
        f"/api/v1/shc/queue/{report_id}/recommendation",
        headers=headers,
        json={
            "compliance_record": "Synthetic compliance record",
            "recommendation": "Place the matter before the Executive Committee",
        },
    )
    assert too_early.status_code == 409
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "shc.recommendation_rejected")
    ).first()

    clock.advance(days=10)
    recorded = client.post(
        f"/api/v1/shc/queue/{report_id}/recommendation",
        headers=headers,
        json={
            "compliance_record": "Human-recorded compliance observations",
            "recommendation": "Place the matter before the Executive Committee",
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["status"] == "completed"
    executive = client.get("/api/v1/executive-committee/queue", headers=headers)
    assert executive.status_code == 200
    item = next(row for row in executive.json()["rows"] if row["report_id"] == report_id)
    assert item["recommendation"] == "Place the matter before the Executive Committee"
    document = client.get(
        f"/api/v1/executive-committee/queue/{recorded.json()['id']}/document",
        headers=headers,
    )
    assert document.status_code == 200
    case = client.get(f"/api/v1/applications/{APPLICATION_ID}", headers=headers).json()
    assert case["application"]["current_state"] == "scrutiny"
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "shc.recommendation_recorded")
    ).first()


def test_shc_date_rejects_past_and_invalid_hearing_modes(client, as_user, db, clock):
    report_id, _document_id = _completed_deficiency_report(client, as_user, db, clock)
    headers = as_user("regional@demo.local")
    past = client.post(
        f"/api/v1/shc/queue/{report_id}/hearing",
        headers=headers,
        json={
            "scheduled_date": date(2026, 10, 21).isoformat(),
            "visit_mode": "physical",
            "venue": "Synthetic room",
        },
    )
    assert past.status_code == 422
    insecure = client.post(
        f"/api/v1/shc/queue/{report_id}/hearing",
        headers=headers,
        json={
            "scheduled_date": "2026-11-01",
            "visit_mode": "online",
            "meeting_url": "http://meet.example.test/room",
        },
    )
    assert insecure.status_code == 422
    hostless = client.post(
        f"/api/v1/shc/queue/{report_id}/hearing",
        headers=headers,
        json={
            "scheduled_date": "2026-11-01",
            "visit_mode": "online",
            "meeting_url": "https://",
        },
    )
    assert hostless.status_code == 422
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "shc.hearing_rejected")
    ).first()
