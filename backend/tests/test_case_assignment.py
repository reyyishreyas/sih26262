"""A case must land in the queue of whoever has to act on it next.

What this pins: only the demo seed ever created assignment rows. A brand-new
application therefore reached no queue at all — the College could create it,
submit it and upload documents, and the Review Officer would see nothing,
because their scope is "assigned cases only". Submitting is the moment the
hand-off happens, so that is where it is tested.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import CaseAssignment


def _create_draft(client, headers, *, route_key: str = "new_technical") -> str:
    institution = client.get("/api/v1/institutions", headers=headers).json()[0]
    created = client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "institution_id": institution["id"],
            "category": route_key,
            "route_key": route_key,
            "cycle": "2027-28",
            "cycle_end": "2028-03-31",
        },
    )
    assert created.status_code == 201
    return created.json()["id"]


def _visible_cases(client, headers) -> set[str]:
    response = client.get("/api/v1/applications", headers=headers)
    assert response.status_code == 200
    return {row["id"] for row in response.json()}


def test_a_draft_is_not_yet_in_any_reviewer_queue(client, as_user):
    college = as_user("institution@demo.local")
    application_id = _create_draft(client, college)

    # The College sees its own draft; no officer has been handed it yet.
    assert application_id in _visible_cases(client, college)
    assert application_id not in _visible_cases(
        client, as_user("scrutiny@demo.local")
    )


def test_submitting_hands_the_case_to_the_reviewer_queue(client, as_user):
    college = as_user("institution@demo.local")
    reviewer = as_user("scrutiny@demo.local")
    application_id = _create_draft(client, college)

    submitted = client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "submit"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["accepted"] is True

    # The exact complaint this fixes: it must now be in the reviewer's list,
    # and openable, not merely listed somewhere global.
    assert application_id in _visible_cases(client, reviewer)
    opened = client.get(
        f"/api/v1/applications/{application_id}", headers=reviewer
    )
    assert opened.status_code == 200
    assert opened.json()["application"]["current_state"] == "submitted"


def test_documents_uploaded_after_submitting_are_readable_by_the_reviewer(
    client, as_user
):
    from pdf_factory import affidavit_pdf

    college = as_user("institution@demo.local")
    reviewer = as_user("scrutiny@demo.local")
    application_id = _create_draft(client, college)

    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "submit"},
    )
    uploaded = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=college,
        data={"doc_type": "affidavit"},
        files={"file": ("affidavit.pdf", affidavit_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201

    documents = client.get(
        f"/api/v1/applications/{application_id}/documents", headers=reviewer
    )
    assert documents.status_code == 200
    assert [row["file_name"] for row in documents.json()] == ["affidavit.pdf"]
    # What the officer reads is what the College actually uploaded.
    values = {
        field["field_name"]: field["value"]
        for field in documents.json()[0]["fields"]
    }
    assert values["document_id"] == "AFF-2026-0007"


def test_handing_over_twice_does_not_duplicate_assignments(client, as_user, db):
    college = as_user("institution@demo.local")
    application_id = _create_draft(client, college)

    # submit -> scrutiny -> return_for_clarification -> resubmit: the reviewer
    # is the next actor out of both `submitted` and `scrutiny`, so the same
    # officer must end up with exactly one row, not three.
    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "submit"},
    )
    officer = as_user("scrutiny@demo.local")
    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=officer,
        json={"action": "start_scrutiny"},
    )
    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=officer,
        json={"action": "return_for_clarification", "reason": "please clarify"},
    )
    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "resubmit"},
    )

    rows = db.scalars(
        select(CaseAssignment).where(
            CaseAssignment.application_id == application_id,
            CaseAssignment.revoked_at.is_(None),
        )
    ).all()
    by_user = [row.user_id for row in rows]
    assert len(by_user) == len(set(by_user)), "an officer was assigned twice"


def test_the_case_gets_a_primary_officer_for_reporting(client, as_user, db):
    from app.models import Application, User

    college = as_user("institution@demo.local")
    application_id = _create_draft(client, college)
    # A draft has no officer: it is with the College, and "unassigned" is the
    # honest answer for the workload report.
    assert db.get(Application, application_id).assigned_officer_id is None

    client.post(
        f"/api/v1/applications/{application_id}/transitions",
        headers=college,
        json={"action": "submit"},
    )
    officer_id = db.get(Application, application_id).assigned_officer_id
    assert officer_id is not None
    officer = db.get(User, officer_id)
    assert officer.email == "scrutiny@demo.local"
