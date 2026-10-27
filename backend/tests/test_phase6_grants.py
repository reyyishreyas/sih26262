from __future__ import annotations

from sqlalchemy import select

from app.models import Application, AuditEvent, GrantBatch

APP_ID = "app-existing-0003"


def test_grant_batch_requires_ratification_letter_and_publish(client, as_user, db, monkeypatch):
    from app.api import grants

    application = db.get(Application, APP_ID)
    application.current_state = "approved"
    application.cycle = "2026-27"
    db.commit()
    monkeypatch.setattr(grants, "_eligible", lambda _db, _application: True)
    rb = as_user("regulation-bureau@demo.local")
    council = as_user("council@demo.local")
    payload = {
        "cycle": "2026-27",
        "last_grant_date": "2027-06-30",
        "calendar_source": "https://aicte.gov.in/academic-calendar",
        "entries": [
            {
                "application_id": APP_ID,
                "approved_intake": [{"course_name": "B.Tech Synthetic", "approved_intake": 60}],
            }
        ],
    }
    created = client.post("/api/v1/grant/batches", headers=rb, json=payload)
    assert created.status_code == 201, created.text
    batch_id = created.json()["id"]
    blocked = client.post(f"/api/v1/grant/batches/{batch_id}/publish", headers=rb)
    assert blocked.status_code == 409

    ratified = client.post(
        f"/api/v1/grant/batches/{batch_id}/ratify",
        headers=council,
        json={"reason": "Council meeting minute reference: synthetic 42."},
    )
    assert ratified.status_code == 200, ratified.text
    file = ("eoa.pdf", b"%PDF-1.4\nsynthetic grant letter\n%%EOF", "application/pdf")
    uploaded = client.post(
        f"/api/v1/grant/batches/{batch_id}/applications/{APP_ID}/letter",
        headers=rb,
        files={"file": file},
    )
    assert uploaded.status_code == 201, uploaded.text
    published = client.post(f"/api/v1/grant/batches/{batch_id}/publish", headers=rb)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    grant = client.get(
        f"/api/v1/grant/applications/{APP_ID}", headers=as_user("institution@demo.local")
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["approved_intake"] == [
        {"course_name": "B.Tech Synthetic", "approved_intake": 60}
    ]
    assert grant.json()["letter_document_id"]
    assert db.scalar(select(GrantBatch.status).where(GrantBatch.id == batch_id)) == "published"
    actions = set(db.scalars(select(AuditEvent.action)).all())
    assert {
        "grant.batch_consolidated",
        "grant.batch_ratified",
        "grant.letter_uploaded",
        "grant.batch_published",
        "grant.published_record_viewed",
    } <= actions


def test_grant_batch_rejects_non_integer_intake_and_roles_are_narrow(
    client, as_user, db, monkeypatch
):
    from app.api import grants

    application = db.get(Application, APP_ID)
    application.current_state = "approved"
    application.cycle = "2026-27"
    db.commit()
    monkeypatch.setattr(grants, "_eligible", lambda _db, _application: True)
    response = client.post(
        "/api/v1/grant/batches",
        headers=as_user("regulation-bureau@demo.local"),
        json={
            "cycle": "2026-27",
            "last_grant_date": "2027-06-30",
            "calendar_source": "https://aicte.gov.in/calendar",
            "entries": [
                {
                    "application_id": APP_ID,
                    "approved_intake": [{"course_name": "Course", "approved_intake": 1.5}],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert db.scalar(
        select(AuditEvent.id).where(AuditEvent.action == "grant.intake_rejected")
    )
    assert (
        client.get("/api/v1/grant/eligible", headers=as_user("admin@demo.local")).status_code == 403
    )
