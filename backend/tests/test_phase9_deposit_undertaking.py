"""Phase 9.2 deposit undertaking, linked notice, evidence and reminders."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import select

from app.core.clock import to_utc
from app.models import Alert, Application, Undertaking
from app.services import deadline_service, demo_clock
from app.services import security_deposit as sd
from app.services.authorization_service import effective_access
from tests.conftest import DEMO_NOW

CASE = "app-existing-0003"
URL = f"/api/v1/applications/{CASE}"
OFFICER = "scrutiny@demo.local"
INSTITUTION = "institution@demo.local"
ADMIN = "admin@demo.local"


def _approve(db):
    from app.models import User
    from app.services import workflow_service

    access = effective_access(db, db.query(User).filter_by(email=OFFICER).one())
    result = workflow_service.request_transition(
        db, access, CASE, "approve", reason="synthetic approval for Phase 9.2 test"
    )
    assert result.accepted, result.reasons


def _upload(client, as_user, filename="synthetic-notice.pdf"):
    result = client.post(
        f"{URL}/documents", headers=as_user(INSTITUTION),
        data={"doc_type": "aicte_notice"},
        files={"file": (filename, b"%PDF-1.4 synthetic evidence", "application/pdf")},
    )
    assert result.status_code == status.HTTP_201_CREATED, result.text
    return result.json()["document"]


def _record(client, as_user, document, notice_date="2026-10-22"):
    return client.post(
        f"{URL}/undertakings", headers=as_user(OFFICER),
        json={"title": "Security Deposit proof and Affidavit 3",
              "obligation_key": "security_deposit_proof",
              "source_received_on": notice_date,
              "source_document_id": document["id"]},
    )


def _item(db):
    return db.scalars(select(Undertaking).where(
        Undertaking.application_id == CASE,
        Undertaking.obligation_key == sd.OBLIGATION_KEY,
    )).first()


def test_approval_alone_does_not_start_the_deposit_clock(db):
    _approve(db)
    assert _item(db) is None
    assert sd.sd_snapshot(db, db.get(Application, CASE), DEMO_NOW)["status"] == "awaiting_intimation"


def test_officer_records_notice_and_window_uses_its_date(client, as_user, db):
    _approve(db)
    notice = _upload(client, as_user)
    response = _record(client, as_user, notice)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    item = _item(db)
    assert item.source_received_on == date(2026, 10, 22)
    assert item.source_document_id == notice["id"]
    expected_deadline = datetime.combine(
        date(2026, 11, 6), time(23, 59, 59), tzinfo=ZoneInfo("Asia/Kolkata")
    ).astimezone(UTC)
    assert to_utc(item.due_at) == expected_deadline
    snapshot = sd.sd_snapshot(db, db.get(Application, CASE), DEMO_NOW)
    assert snapshot["status"] == "open"
    assert snapshot["intimation_date"] == "2026-10-22"


def test_notice_requires_approved_case_date_and_same_case_document(client, as_user, db):
    notice = _upload(client, as_user)
    unapproved = _record(client, as_user, notice)
    assert unapproved.status_code == status.HTTP_409_CONFLICT
    _approve(db)
    missing = client.post(f"{URL}/undertakings", headers=as_user(OFFICER), json={
        "title": "Security Deposit proof", "obligation_key": sd.OBLIGATION_KEY,
    })
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    future = _record(client, as_user, notice, "2026-10-23")
    assert future.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_notice_reminders_dedupe_after_explicit_recording(client, as_user, db):
    _approve(db)
    notice = _upload(client, as_user)
    assert _record(client, as_user, notice).status_code == status.HTTP_201_CREATED
    demo_clock.advance(db, _access(db, ADMIN), 16.0)
    result = deadline_service.sweep(db)
    alerts = [row for row in result.alerts if row["alert_type"] == "security_deposit_due"]
    assert {row["level"] for row in alerts} == {"sd_day_1", "sd_day_10", "sd_day_14"}
    deadline_service.sweep(db)
    assert len(db.scalars(select(Alert).where(Alert.alert_type == "security_deposit_due")).all()) == 3


def _access(db, email):
    from app.models import User

    return effective_access(db, db.query(User).filter_by(email=email).one())


def test_submitted_proof_documents_are_linked_and_officer_verified(client, as_user, db):
    _approve(db)
    notice = _upload(client, as_user)
    assert _record(client, as_user, notice).status_code == status.HTTP_201_CREATED
    proof = _upload(client, as_user, "synthetic-bank-proof.pdf")
    affidavit = _upload(client, as_user, "synthetic-affidavit-3.pdf")
    item = _item(db)
    submit = client.post(f"{URL}/undertakings/{item.id}/submit", headers=as_user(INSTITUTION), json={
        "evidence_note": "Synthetic proof and affidavit uploaded.",
        "evidence_document_ids": [proof["id"], affidavit["id"]],
    })
    assert submit.status_code == status.HTTP_200_OK, submit.text
    assert set(submit.json()["evidence_document_ids"]) == {proof["id"], affidavit["id"]}
    verify = client.post(f"{URL}/undertakings/{item.id}/verify", headers=as_user(OFFICER))
    assert verify.status_code == status.HTTP_200_OK, verify.text
    assert verify.json()["status"] == "verified"
    db.expire_all()
    assert sd.sd_snapshot(db, db.get(Application, CASE), DEMO_NOW)["undertaking_status"] == "verified"
