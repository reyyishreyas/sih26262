"""Phase 9.1 lease thin slice (FR-45): the stored lease end date drives
expiry alerts.

FR-45: *"Read lease end date, compute years, finding if equal or shorter;
store end date for expiry alerts."* The reading (extractor), the years
computation and the equal/shorter finding landed in Phase 2.4/2.5
(``readiness.lease_check``, IMPL-0019) and the storage is Phase 5.2's
``ExtractedField``; the sweep ladder already walks documented expiry dates
(``deadline_service.collect_items`` item 2). What no test had proven is
the composed behavior on a lease document: a *verified* lease ``valid_to``
must raise the configured advance reminders before expiry and the
overdue/escalated alerts after it — while an unverified date raises
nothing (already covered in ``test_alerts.py``) and a second sweep
creates nothing new.

All values are synthetic; the ladder is configured in
`rules/deadline_policy.json`, never code.
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy import select

from app.models import Alert, Document, User
from app.services import deadline_service
from tests.conftest import DEMO_NOW

APP = "app-main-0001"
OFFICER = "scrutiny@demo.local"
INSTITUTION = "institution@demo.local"
URL = "/api/v1/applications"


def _upload_lease(client, headers, *, valid_to: str) -> Document:
    """Upload a synthetic lease whose text layer carries the expiry."""
    from pdf_factory import lease_deed_pdf

    response = client.post(
        f"{URL}/{APP}/documents",
        headers=headers,
        data={"doc_type": "lease_deed"},
        files={"file": ("lease.pdf", lease_deed_pdf(valid_to=valid_to), "application/pdf")},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()["document"]
    assert document["fields"], "the lease text layer must yield fields"
    values = {f["field_name"]: f for f in document["fields"]}
    assert values["valid_to"]["value"] == valid_to
    return document


def _verify(client, headers, document: dict, field_name: str) -> None:
    values = {f["field_name"]: f for f in document["fields"]}
    response = client.post(
        f"{URL}/{APP}/documents/{document['id']}/fields/{values[field_name]['id']}/verify",
        headers=headers,
        json={"verification_status": "verified", "note": "checked on the lease text"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text


def _document_alerts(db, document_id: str) -> dict[str, Alert]:
    return {
        alert.level: alert
        for alert in db.scalars(
            select(Alert).where(Alert.entity_type == "document", Alert.entity_id == document_id)
        ).all()
    }


def test_advance_expiry_reminders_fire_on_a_verified_lease_date(client, as_user, db):
    # Lease valid_to 14 days past the demo clock: both configured advance
    # levels (reminder_60, reminder_30) are already inside their windows.
    valid_to = "2026-11-05"
    document = _upload_lease(client, as_user(INSTITUTION), valid_to=valid_to)
    _verify(client, as_user(OFFICER), document, "valid_to")

    result = deadline_service.sweep(db, DEMO_NOW)
    by_level = _document_alerts(db, document["id"])
    assert set(by_level) == {"reminder_60", "reminder_30"}
    assert by_level["reminder_30"].payload["valid_to"] == valid_to
    assert by_level["reminder_30"].payload["doc_type"] == "lease_deed"
    assert result.created >= 2

    # Idempotence is per-lease too: the second sweep creates nothing new.
    again = deadline_service.sweep(db, DEMO_NOW)
    assert not any(
        item["entity_id"] == document["id"] and item["created"] for item in again.alerts
    )


def test_overdue_alerts_fire_after_an_expired_verified_lease(client, as_user, db):
    document = _upload_lease(client, as_user(INSTITUTION), valid_to="2025-01-01")
    _verify(client, as_user(OFFICER), document, "valid_to")

    deadline_service.sweep(db, DEMO_NOW)
    by_level = _document_alerts(db, document["id"])
    # A far-past due date is inside *every* threshold window at once:
    # both advance reminders and both overdue levels are raised.
    assert set(by_level) == {"reminder_60", "reminder_30", "expired", "escalated"}

    # The escalated alert reaches the region's regional officer.
    regional = db.scalars(
        select(Alert).where(Alert.entity_id == document["id"], Alert.level == "escalated")
    ).one()
    officer = db.scalars(select(User).where(User.email == "regional@demo.local")).one()
    assert officer.id in regional.recipients

    # And a repeat sweep does not duplicate the overdue rows.
    deadline_service.sweep(db, DEMO_NOW)
    assert len(_document_alerts(db, document["id"])) == 4
