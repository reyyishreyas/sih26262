"""Audit integrity: hash chain verification and live tamper detection."""

from __future__ import annotations

from sqlalchemy import select, text

from app.models import AuditEvent
from app.services.audit_service import verify_chain


def test_seeded_chain_verifies(db):
    verification = verify_chain(db)
    assert verification.ok is True
    assert verification.checked >= 3


def test_tampering_with_a_stored_event_is_detected(db):
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).all()
    target = events[1]

    db.execute(
        text("UPDATE audit_events SET reason = :reason WHERE seq = :seq"),
        {"reason": "rewritten after the fact", "seq": target.seq},
    )
    db.commit()
    db.expire_all()

    verification = verify_chain(db)
    assert verification.ok is False
    assert verification.first_broken_seq == target.seq
    assert "hash" in verification.reason


def test_deleting_an_event_breaks_the_chain(db):
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).all()
    target = events[-2]

    db.execute(text("DELETE FROM audit_events WHERE seq = :seq"), {"seq": target.seq})
    db.commit()
    db.expire_all()

    verification = verify_chain(db)
    assert verification.ok is False
    assert verification.reason


def test_rejected_transition_is_recorded_with_before_state(db, access_for):
    from app.models import Application
    from app.services import workflow_service

    access = access_for("scrutiny@demo.local")
    application = db.get(Application, "app-main-0001")

    decision = workflow_service.request_transition(
        db, access, application.id, "schedule_evc"
    )
    assert decision.accepted is False

    event = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == application.id, AuditEvent.outcome == "rejected")
        .order_by(AuditEvent.seq.desc())
    ).first()
    assert event is not None
    assert event.before == {"state": "scrutiny"}
    assert event.after == {}
    assert verify_chain(db).ok is True


def test_accepted_event_carries_actor_and_transition(db, access_for):
    from app.models import Application
    from app.services import workflow_service

    access = access_for("scrutiny@demo.local")
    decision = workflow_service.request_transition(
        db, access, "app-existing-0003", "approve", reason="Verified"
    )
    assert decision.accepted is True

    event = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == "app-existing-0003")
        .order_by(AuditEvent.seq.desc())
    ).first()
    assert event.outcome == "accepted"
    assert event.actor_id == access.user_id
    assert event.actor_role == "scrutiny_officer"
    assert event.after["state"] == "approved"
    assert db.get(Application, "app-existing-0003").current_state == "approved"
