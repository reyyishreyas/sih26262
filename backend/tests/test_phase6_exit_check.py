from __future__ import annotations

from datetime import timedelta

from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.core.permissions import EXECUTIVE_COMMITTEE_MEMBER, SHC_MEMBER
from app.models import Application, Region, Role, User, UserRoleAssignment


def _upload(client, headers, application_id: str, doc_type: str, filename: str) -> str:
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=headers,
        data={"doc_type": doc_type},
        files={"file": (filename, affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


def test_phase6_single_case_journey_through_grant_and_advisory_deposit(
    client, as_user, db, clock
):
    """Exercise Phase 6's joins with public APIs; keep placeholder deposit rules advisory."""
    institution_headers = as_user("institution@demo.local")
    institution = client.get("/api/v1/institutions", headers=institution_headers).json()[0]
    created = client.post(
        "/api/v1/applications",
        headers=institution_headers,
        json={
            "institution_id": institution["id"],
            "category": "evc_sac_shc",
            "route_key": "evc_sac_shc",
            "cycle": "2026-27",
            "cycle_end": "2027-03-31",
        },
    )
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]
    _upload(
        client, institution_headers, application_id, "affidavit", "synthetic-affidavit.pdf"
    )

    submitted = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=institution_headers,
        json={"action": "submit", "reason": ""},
    )
    assert submitted.status_code == 200 and submitted.json()["accepted"]
    scrutiny = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=as_user("scrutiny@demo.local"),
        json={"action": "start_scrutiny", "reason": ""},
    )
    assert scrutiny.status_code == 200 and scrutiny.json()["accepted"]

    regional_headers = as_user("regional@demo.local")
    committees = client.get("/api/v1/evc/committees", headers=regional_headers)
    assert committees.status_code == 200, committees.text
    committee = committees.json()[0]
    experts = client.get(
        f"/api/v1/applications/{application_id}/evc/committees/{committee['id']}/experts",
        headers=regional_headers,
    )
    assert experts.status_code == 200 and experts.json()
    scheduled = client.post(
        f"/api/v1/applications/{application_id}/evc/visits",
        headers=regional_headers,
        json={
            "scheduled_date": (clock.now().date() + timedelta(days=2)).isoformat(),
            "visit_mode": "physical",
            "venue": "Synthetic campus",
            "committee_id": committee["id"],
            "expert_user_ids": [experts.json()[0]["id"]],
        },
    )
    assert scheduled.status_code == 201, scheduled.text
    visit_id = scheduled.json()["id"]
    evc_headers = as_user("evc@demo.local")
    report_document = client.post(
        f"/api/v1/applications/{application_id}/evc/visits/{visit_id}/report/document",
        headers=evc_headers,
        files={"file": ("synthetic-evc-report.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert report_document.status_code == 201, report_document.text
    report = client.post(
        f"/api/v1/applications/{application_id}/evc/visits/{visit_id}/report",
        headers=evc_headers,
        json={
            "document_id": report_document.json()["document"]["id"],
            "summary": "Synthetic EVC observations recorded by the assigned expert.",
            "deficiency_present": True,
        },
    )
    assert report.status_code == 201, report.text

    complete = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=evc_headers,
        json={"action": "complete_evc", "reason": ""},
    )
    assert complete.status_code == 200 and complete.json()["accepted"]
    forwarded = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=regional_headers,
        json={"action": "forward_to_sac", "reason": ""},
    )
    assert forwarded.status_code == 200 and forwarded.json()["accepted"]

    regional = db.scalar(select(User).where(User.email == "regional@demo.local"))
    north = db.scalar(select(Region).where(Region.code == "NR"))
    assert regional is not None and north is not None
    for role_name in (SHC_MEMBER, EXECUTIVE_COMMITTEE_MEMBER):
        role = db.scalar(select(Role).where(Role.name == role_name))
        assert role is not None
        db.add(
            UserRoleAssignment(
                user_id=regional.id,
                role_id=role.id,
                scope_type="region",
                scope_id=north.id,
            )
        )
    db.commit()

    report_id = report.json()["id"]
    hearing = client.post(
        f"/api/v1/shc/queue/{report_id}/hearing",
        headers=regional_headers,
        json={
            "scheduled_date": (clock.now().date() + timedelta(days=2)).isoformat(),
            "visit_mode": "physical",
            "venue": "Synthetic SHC room",
        },
    )
    assert hearing.status_code == 201, hearing.text
    clock.advance(days=2)
    recommendation = client.post(
        f"/api/v1/shc/queue/{report_id}/recommendation",
        headers=regional_headers,
        json={
            "compliance_record": "Human-recorded synthetic compliance observations.",
            "recommendation": "Place the application before the Executive Committee.",
        },
    )
    assert recommendation.status_code == 200, recommendation.text

    speaking_order = client.post(
        f"/api/v1/applications/{application_id}/documents/executive-speaking-orders",
        headers=regional_headers,
        files={"file": ("synthetic-speaking-order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert speaking_order.status_code == 201, speaking_order.text
    decision = client.post(
        f"/api/v1/executive-committee/applications/{application_id}/decision",
        headers=regional_headers,
        json={
            "outcome": "rejected",
            "speaking_order_document_id": speaking_order.json()["document"]["id"],
            "reason": "Synthetic human decision used to exercise the appeal route.",
        },
    )
    assert decision.status_code == 200 and decision.json()["accepted"]

    appeal_evidence = _upload(
        client,
        institution_headers,
        application_id,
        "appeal_supporting_evidence",
        "synthetic-appeal-evidence.pdf",
    )
    appeal_response = client.post(
        f"/api/v1/applications/{application_id}/appeals",
        headers=institution_headers,
        json={
            "grounds": "Synthetic appeal grounds for the integrated route test.",
            "supporting_document_ids": [appeal_evidence],
        },
    )
    assert appeal_response.status_code == 201, appeal_response.text
    appeal_id = appeal_response.json()["id"]
    representative_ids = [
        _upload(
            client,
            institution_headers,
            application_id,
            "appeal_representative_id",
            f"synthetic-representative-{index}.pdf",
        )
        for index in (1, 2)
    ]
    representatives = client.post(
        f"/api/v1/appeals/{appeal_id}/representatives",
        headers=institution_headers,
        json={
            "representatives": [
                {
                    "name": f"Synthetic Representative {index}",
                    "institutional_role": role,
                    "id_document_id": document_id,
                    "authorization_attested": True,
                }
                for index, (role, document_id) in enumerate(
                    zip(("Director", "Trustee"), representative_ids, strict=True), start=1
                )
            ]
        },
    )
    assert representatives.status_code == 200, representatives.text
    hearing_at = clock.now() + timedelta(days=2)
    sac_schedule = client.post(
        f"/api/v1/sac/appeals/{appeal_id}/schedule",
        headers=as_user("sac@demo.local"),
        json={"hearing_at": hearing_at.isoformat(), "venue": "Synthetic SAC room"},
    )
    assert sac_schedule.status_code == 200, sac_schedule.text
    clock.advance(days=2)
    sac_record = client.post(
        f"/api/v1/sac/appeals/{appeal_id}/hearing-record",
        headers=as_user("sac@demo.local"),
        json={"recommendation": "Recommend that the Council allow this synthetic appeal."},
    )
    assert sac_record.status_code == 200, sac_record.text
    council_order = client.post(
        f"/api/v1/applications/{application_id}/documents/council-decision-orders",
        headers=as_user("council@demo.local"),
        files={"file": ("synthetic-council-order.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert council_order.status_code == 201, council_order.text
    final_decision = client.post(
        f"/api/v1/council/appeals/{appeal_id}/decision",
        headers=as_user("council@demo.local"),
        json={
            "outcome": "approved",
            "decision": "Council allows the synthetic appeal.",
            "decision_document_id": council_order.json()["document"]["id"],
        },
    )
    assert final_decision.status_code == 200, final_decision.text
    assert db.get(Application, application_id).current_state == "approved"

    batch = client.post(
        "/api/v1/grant/batches",
        headers=as_user("regulation-bureau@demo.local"),
        json={
            "cycle": "2026-27",
            "last_grant_date": "2027-06-30",
            "calendar_source": "https://aicte.gov.in/academic-calendar",
            "entries": [
                {
                    "application_id": application_id,
                    "approved_intake": [
                        {"course_name": "Synthetic B.Tech", "approved_intake": 60}
                    ],
                }
            ],
        },
    )
    assert batch.status_code == 201, batch.text
    batch_id = batch.json()["id"]
    ratification = client.post(
        f"/api/v1/grant/batches/{batch_id}/ratify",
        headers=as_user("council@demo.local"),
        json={"reason": "Synthetic Council ratification record."},
    )
    assert ratification.status_code == 200, ratification.text
    grant_letter = client.post(
        f"/api/v1/grant/batches/{batch_id}/applications/{application_id}/letter",
        headers=as_user("regulation-bureau@demo.local"),
        files={"file": ("synthetic-eoa.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert grant_letter.status_code == 201, grant_letter.text
    published = client.post(
        f"/api/v1/grant/batches/{batch_id}/publish",
        headers=as_user("regulation-bureau@demo.local"),
    )
    assert published.status_code == 200, published.text

    institution_grant = client.get(
        f"/api/v1/grant/applications/{application_id}", headers=institution_headers
    )
    assert institution_grant.status_code == 200, institution_grant.text
    assert institution_grant.json()["letter_document_id"]
    deposit = client.get(
        f"/api/v1/applications/{application_id}/security-deposit",
        headers=institution_headers,
    )
    assert deposit.status_code == 200, deposit.text
    assert deposit.json()["status"] == "awaiting_intimation"
    assert deposit.json()["advisory_only"] is True
    assert deposit.json()["placeholder"] is True
    assert deposit.json()["proof_deadline"] is None
    assert deposit.json()["withdrawal_flagged"] is False
    assert db.get(Application, application_id).current_state == "approved"
