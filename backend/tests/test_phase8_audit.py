"""Phase 8 audit coverage: evidence access, events, export and verification."""

from __future__ import annotations

from pdf_factory import affidavit_pdf
from sqlalchemy import select, text

from app.models import AuditEvent, Document
from app.services import ocr_service

APP = "app-main-0001"


def _events(db, action: str) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.seq)
        ).all()
    )


def test_authorized_document_content_read_writes_a_sensitive_access_event(
    client, as_user, db
):
    document = db.scalar(select(Document).where(Document.application_id == APP))
    headers = as_user("scrutiny@demo.local")
    response = client.get(
        f"/api/v1/applications/{APP}/documents/{document.id}/content", headers=headers
    )
    assert response.status_code == 200

    db.expire_all()
    event = _events(db, "document.accessed")[-1]
    assert event.entity_id == document.id
    assert event.actor_role == "scrutiny_officer"
    assert event.after == {
        "application_id": APP,
        "version": document.version,
        "doc_type": document.doc_type,
        "sha256": document.file_sha256,
    }
    assert "content" not in event.after


def test_out_of_scope_document_read_does_not_write_an_access_event(
    client, as_user, db
):
    document = db.scalar(
        select(Document).where(Document.application_id == "app-second-0002")
    )
    before = len(_events(db, "document.accessed"))
    response = client.get(
        f"/api/v1/applications/app-second-0002/documents/{document.id}/content",
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == 404
    db.expire_all()
    assert len(_events(db, "document.accessed")) == before


def test_upload_records_extraction_start_completion_and_versioned_document(
    client, as_user, db
):
    response = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "affidavit"},
        files={"file": ("phase8-affidavit.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["document"]["id"]

    db.expire_all()
    started = _events(db, "document.extraction_started")[-1]
    completed = _events(db, "document.extraction_completed")[-1]
    uploaded = _events(db, "document.uploaded")[-1]
    assert started.entity_id == APP
    assert started.after["doc_type"] == "affidavit"
    assert completed.entity_id == APP
    assert completed.after["version"] == 1
    assert completed.after["sha256"] == response.json()["document"]["file_sha256"]
    assert uploaded.after["version"] == 1

    replaced = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "affidavit", "reason": "corrected copy"},
        files={"file": ("phase8-affidavit-v2.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert replaced.status_code == 201, replaced.text
    db.expire_all()
    replacement_event = _events(db, "document.replaced")[-1]
    assert replacement_event.after["version"] == 2
    assert replacement_event.before == {"version": 1}


def test_extraction_failure_is_recorded_without_storing_the_upload(
    client, as_user, db, monkeypatch
):
    class FailingExtractor:
        def extract(self, **_kwargs):
            raise RuntimeError("provider failure with no document data")

    monkeypatch.setattr(ocr_service, "get_ocr_extractor", lambda: FailingExtractor())
    response = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "affidavit"},
        files={"file": ("failed-affidavit.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert response.status_code == 500
    db.expire_all()
    assert _events(db, "document.extraction_started")[-1].entity_id == APP
    failed = _events(db, "document.extraction_failed")[-1]
    assert failed.entity_id == APP
    assert failed.reason == "document extraction failed"
    assert "provider failure" not in failed.reason


def test_explicit_chain_verification_is_audited_and_get_remains_read_only(
    client, as_user, db
):
    headers = as_user("scrutiny@demo.local")
    before = len(_events(db, "audit.verification"))
    read_only = client.get("/api/v1/audit/verify", headers=headers)
    assert read_only.status_code == 200
    assert len(_events(db, "audit.verification")) == before

    recorded = client.post("/api/v1/audit/verify", headers=headers)
    assert recorded.status_code == 200
    assert recorded.json()["ok"] is True
    assert recorded.json()["verification_event_seq"]
    db.expire_all()
    assert len(_events(db, "audit.verification")) == before + 1


def test_recorded_verification_reports_tampering_and_records_rejection(
    client, as_user, db
):
    target = db.scalar(select(AuditEvent).order_by(AuditEvent.seq))
    db.execute(
        text("UPDATE audit_events SET reason = :reason WHERE seq = :seq"),
        {"reason": "test-only alteration", "seq": target.seq},
    )
    db.commit()

    response = client.post(
        "/api/v1/audit/verify", headers=as_user("scrutiny@demo.local")
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    db.expire_all()
    event = _events(db, "audit.verification")[-1]
    assert event.outcome == "rejected"
    assert event.after["ok"] is False


def test_case_export_contains_chain_check_and_audits_the_export(client, as_user):
    response = client.get(
        f"/api/v1/applications/{APP}/audit/export",
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].endswith(f'{APP}-audit.json"')
    body = response.json()
    assert body["format"] == "sih26262.case-audit.v1"
    assert body["integrity"]["verified_before_export"] is True
    assert body["integrity"]["chain_verification"]["ok"] is True
    assert len(body["integrity"]["chain_head_hash"]) == 64
    assert any(event["action"] == "audit.exported" for event in body["events"])


def test_case_export_refuses_a_tampered_chain(client, as_user, db):
    target = db.scalar(select(AuditEvent).order_by(AuditEvent.seq))
    db.execute(
        text("UPDATE audit_events SET reason = :reason WHERE seq = :seq"),
        {"reason": "test-only alteration", "seq": target.seq},
    )
    db.commit()

    response = client.get(
        f"/api/v1/applications/{APP}/audit/export",
        headers=as_user("scrutiny@demo.local"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "audit chain verification failed"


def test_compliance_evaluation_is_recorded_as_a_finding_batch(client, as_user, db):
    response = client.post(
        f"/api/v1/applications/{APP}/compliance/evaluate",
        headers=as_user("institution@demo.local"),
    )
    assert response.status_code == 200
    db.expire_all()
    event = _events(db, "finding.batch_evaluated")[-1]
    assert event.entity_id == APP
    assert event.after["batch_id"] == response.json()["batch_id"]
    assert event.after["rule_set_version"]


def test_submission_audits_new_case_assignment(client, as_user, db):
    institution = as_user("institution@demo.local")
    institution_row = client.get("/api/v1/institutions", headers=institution).json()[0]
    created = client.post(
        "/api/v1/applications",
        headers=institution,
        json={
            "institution_id": institution_row["id"],
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2027-28",
            "cycle_end": "2028-03-31",
        },
    )
    assert created.status_code == 201
    application_id = created.json()["id"]
    submitted = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=institution,
        json={"action": "submit"},
    )
    assert submitted.status_code == 200 and submitted.json()["accepted"] is True

    db.expire_all()
    event = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.action == "assignment.created",
            AuditEvent.entity_id == application_id,
        )
        .order_by(AuditEvent.seq.desc())
    )
    assert event is not None
    assert event.after["assignments"]
