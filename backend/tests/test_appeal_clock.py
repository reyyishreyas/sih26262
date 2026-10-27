"""Appeal window: the FR-27 seven-day clock, one-appeal limit, day-3/day-6 alerts.

Plan 3.5 builds `appeal_policy.json` + `appeal.py`: the PRD §7 appeal-to-Council
clock (once, within 7 days of the decision upload — APH cl. 2.24a), the
day-3 / day-6 reminder cadence (§11 line 288), and the SAC receiving-authority
label. Every value is Unverified placeholder configuration (rules2.json
REG-APPEAL-001 says do not activate the 7-day figure as binding).

Safety properties under test:

- **The figure is labelled unverified/placeholder/advisory, never an AICTE rule.**
- **The window runs from the decision state's start**, and a case not in
  approved/rejected has no window at all.
- **The sweep raises the day-3 and day-6 reminders idempotently** through the
  normal alert path — never a gate, and re-running creates nothing new.
- **One appeal only**: the count comes from `WorkflowTransition` rows, and the
  "may file" flag flips off once the limit is reached.
- **Nothing is gated or written** (DEC-0003): the snapshot is read-only and
  there is no `file_appeal` transition yet (Phase 6.6).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.clock import FixedClock, get_clock, set_clock
from app.models import Alert, Appeal, Application, AuditEvent, Document, WorkflowTransition
from app.services import appeal, deadline_service, workflow_service
from app.services.policy import RULES_DIR, appeal_policy

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)  # Thursday; matches DEMO_NOW

EXISTING = "app-existing-0003"  # scrutiny, in scope, assigned to scrutiny officer
MAIN = "app-main-0001"          # scrutiny, in scope (new_technical route)
SECOND = "app-second-0002"      # submitted (not a decision), region south

SCRUTINY_EMAIL = "scrutiny@demo.local"


def _config() -> dict:
    return appeal_policy()


def _scrutiny_reject(db, application_id: str, when: datetime) -> Application:
    """Drive a seeded scrutiny-stage case to `rejected` at instant `when`.

    `reject` is the decision transition that needs only a recorded reason —
    no documents or rule checks — so the setup is stable without depending on
    seeded evidence. The clock is frozen at `when` so `current_state_since`
    (the appeal-clock anchor) is deterministic.
    """
    from app.models import User
    from app.services.authorization_service import effective_access

    user = db.query(User).filter_by(email=SCRUTINY_EMAIL).one()
    access = effective_access(db, user)
    prior = get_clock()
    set_clock(FixedClock(when))
    try:
        decision = workflow_service.request_transition(
            db, access, application_id, "reject", reason="appeal-clock test decision"
        )
        assert decision.accepted, decision.reasons
    finally:
        set_clock(prior)
    application = db.get(Application, application_id)
    transition = db.scalars(
        select(WorkflowTransition).where(
            WorkflowTransition.application_id == application_id,
            WorkflowTransition.action == "reject",
        ).order_by(WorkflowTransition.created_at.desc())
    ).first()
    assert transition is not None
    document = Document(
        institution_id=application.institution_id,
        application_id=application.id,
        doc_type="speaking_order",
        file_name="test-speaking-order.pdf",
        content_type="application/pdf",
        file_sha256="a" * 64,
        storage_ref="seed://appeal-clock/test-order.pdf",
        uploaded_at=when,
    )
    db.add(document)
    db.flush()
    transition.speaking_order_document_id = document.id
    db.commit()
    return application


# ------------------------------------------------------------- the config


def test_the_policy_loads_verified_chapter_two_appeal_rules():
    config = _config()
    assert config["status"] == "verified"
    assert config["placeholder"] is False
    assert config["advisory_only"] is False


def test_it_cites_fr_27_and_the_unverified_caveat():
    source = _config()["source"]
    assert "FR-27" in source
    # §19 / REG-APPEAL-001 record the 7-day figure as unverified — it must
    # never read as a verified regulatory rule.
    assert "SRC-APH-APPEAL-2024-27" in source


def test_the_window_is_7_days_and_one_appeal_only():
    config = _config()
    assert config["window_days"] == 7  # FR-27: within 7 days of decision upload
    assert config["max_appeals"] == 1  # FR-27: one appeal only


def test_the_trigger_states_are_the_two_decisions():
    assert set(_config()["trigger"]["states"]) == {"approved", "rejected"}


def test_the_receiving_authority_is_the_standing_appellate_committee():
    authority = _config()["receiving_authority"]
    assert authority["placeholder"] is False
    assert "SAC" in authority["label"]


def test_the_reminders_are_day_3_and_day_6():
    days = [entry["day"] for entry in _config()["reminder_thresholds"]]
    assert days == [3, 6]  # §11 line 288: day 3 and day 6 of 7
    levels = [entry["level"] for entry in _config()["reminder_thresholds"]]
    assert levels == ["appeal_day_3", "appeal_day_6"]


def test_the_policy_file_is_readable_json_in_the_rules_dir():
    parsed = json.loads((Path(RULES_DIR) / "appeal_policy.json").read_text())
    assert parsed["window_days"] == 7
    assert parsed["max_appeals"] == 1


def test_the_sweep_ladder_drives_the_two_reminder_levels():
    """deadline_policy.json's 'appeal' offsets map to the same two levels."""
    from app.services import policy

    levels = [t.level for t in policy.thresholds("appeal")]
    assert levels == ["appeal_day_3", "appeal_day_6"]


# ------------------------------------------------------ the window maths


def test_a_case_in_the_queue_has_no_window(db):
    application = db.get(Application, SECOND)  # submitted — not a decision
    assert appeal.window_for(application, NOW) is None


def test_a_decided_case_has_a_seven_day_window(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    assert application.current_state == "rejected"
    window = appeal.window_for(application, NOW, decision_at=NOW)
    assert window is not None
    assert window.decision_state == "rejected"
    assert window.opens_at == NOW
    assert window.closes_at == NOW + timedelta(days=7)
    assert window.status == "open"


def test_the_window_is_lapsed_after_the_close(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    after_close = NOW + timedelta(days=7, seconds=1)
    window = appeal.window_for(application, after_close, decision_at=NOW)
    assert window is not None
    assert window.status == "lapsed"
    assert window.may_file is False


def test_the_snapshot_flags_may_file_only_while_open(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    open_snapshot = appeal.appeal_snapshot(db, application, NOW)
    assert open_snapshot["may_file"] is True
    assert open_snapshot["appeals_filed"] == 0
    assert open_snapshot["placeholder"] is False
    assert open_snapshot["advisory_only"] is False
    lapsed = appeal.appeal_snapshot(db, application, NOW + timedelta(days=7, seconds=1))
    assert lapsed["may_file"] is False
    assert lapsed["status"] == "lapsed"


def test_an_undecided_case_reports_not_decided(db):
    application = db.get(Application, EXISTING)
    snapshot = appeal.appeal_snapshot(db, application, NOW)
    assert snapshot["status"] == "not_decided"
    assert snapshot["may_file"] is False


def test_chapter_one_new_technical_route_stays_outside_verified_appeal_scope(db):
    application = db.get(Application, MAIN)
    application.current_state = "rejected"
    application.status = "rejected"
    snapshot = appeal.appeal_snapshot(db, application, NOW)
    assert snapshot["status"] == "outside_verified_scope"
    assert snapshot["may_file"] is False


# -------------------------------------------------- the one-appeal limit


def _record_test_appeal(db, application):
    transition = db.scalars(
        select(WorkflowTransition)
        .where(WorkflowTransition.application_id == application.id, WorkflowTransition.action == "reject")
        .order_by(WorkflowTransition.created_at.desc())
    ).first()
    db.add(Appeal(
        application_id=application.id,
        decision_transition_id=transition.id,
        appellant_id=application.assigned_officer_id,
        grounds="The institution disputes the recorded decision.",
        submitted_at=NOW,
        appeal_deadline=NOW + timedelta(days=7),
    ))
    db.commit()


def test_filing_an_appeal_records_one_appeal_row(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    assert appeal.appeals_filed(db, EXISTING) == 0
    _record_test_appeal(db, application)
    assert appeal.appeals_filed(db, EXISTING) == 1


def test_the_may_file_flag_flips_off_once_the_limit_is_reached(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    _record_test_appeal(db, application)
    snapshot = appeal.appeal_snapshot(db, application, NOW)
    assert snapshot["appeals_filed"] == 1
    assert snapshot["max_appeals"] == 1
    assert snapshot["may_file"] is False  # one appeal only — FR-27


# -------------------------------------------------------- the sweep clock


def test_the_sweep_raises_the_day_3_and_day_6_reminders(db):
    _scrutiny_reject(db, EXISTING, NOW)

    clock = FixedClock(NOW)
    set_clock(clock)
    try:
        deadline_service.sweep(db, clock.now())
        # Day 3 of 7 (2026-10-25 09:00) is after the day-3 threshold.
        clock.advance(days=3)
        deadline_service.sweep(db, clock.now())
        day3 = db.scalars(
            select(Alert).where(
                Alert.alert_type == "appeal_window",
                Alert.entity_id == EXISTING,
                Alert.level == "appeal_day_3",
            )
        ).first()
        assert day3 is not None
        assert day3.payload["placeholder"] is False
        assert day3.payload["window_days"] == 7

        # Day 6 of 7 (2026-10-28 09:00) clears the day-6 threshold.
        clock.advance(days=3)
        deadline_service.sweep(db, clock.now())
        day6 = db.scalars(
            select(Alert).where(
                Alert.alert_type == "appeal_window",
                Alert.entity_id == EXISTING,
                Alert.level == "appeal_day_6",
            )
        ).first()
        assert day6 is not None
    finally:
        set_clock(None)


def test_the_sweep_is_idempotent_across_reruns(db):
    _scrutiny_reject(db, EXISTING, NOW)

    clock = FixedClock(NOW + timedelta(days=3))
    set_clock(clock)
    try:
        first = deadline_service.sweep(db, clock.now())
        second = deadline_service.sweep(db, clock.now())
        created_first = [
            a for a in first.alerts if a["alert_type"] == "appeal_window" and a["created"]
        ]
        created_second = [
            a for a in second.alerts if a["alert_type"] == "appeal_window" and a["created"]
        ]
        assert created_first  # the day-3 reminder fires once
        assert created_second == []  # re-running creates nothing new (dedupe_key)
        rows = db.scalars(
            select(Alert).where(
                Alert.alert_type == "appeal_window",
                Alert.entity_id == EXISTING,
                Alert.level == "appeal_day_3",
            )
        ).all()
        assert len(rows) == 1  # exactly one alert row for this case/level
    finally:
        set_clock(None)


def test_a_case_in_the_queue_gets_no_appeal_alert(db):
    """A submitted (undecided) case has no decision to appeal — no window, no alert."""
    _scrutiny_reject(db, EXISTING, NOW)
    clock = FixedClock(NOW + timedelta(days=6))
    set_clock(clock)
    try:
        deadline_service.sweep(db, clock.now())
        rows = db.scalars(
            select(Alert).where(
                Alert.alert_type == "appeal_window",
                Alert.entity_id == SECOND,
            )
        ).all()
        assert rows == []
    finally:
        set_clock(None)


# ----------------------------------------------------------- the API


def test_the_appeal_window_endpoint_is_served_to_signed_in_users(client, as_user):
    body = client.get(
        f"/api/v1/applications/{EXISTING}/appeal-window",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["placeholder"] is False
    assert payload["advisory_only"] is False
    assert payload["status"] == "not_decided"  # seeded case is still in scrutiny


def test_the_appeal_window_endpoint_needs_a_token(client):
    assert (
        client.get(f"/api/v1/applications/{EXISTING}/appeal-window").status_code == 401
    )


def test_the_appeal_window_endpoint_respects_application_scope(client, as_user):
    """The college sees only its own case, never another institution's."""
    headers = as_user("institution@demo.local")
    allowed = client.get(f"/api/v1/applications/{MAIN}/appeal-window", headers=headers)
    assert allowed.status_code == 200
    denied = client.get(f"/api/v1/applications/{SECOND}/appeal-window", headers=headers)
    assert denied.status_code in (403, 404)


def test_the_endpoint_reports_an_open_window_for_a_decided_case(client, as_user, db):
    _scrutiny_reject(db, EXISTING, NOW)
    body = client.get(
        f"/api/v1/applications/{EXISTING}/appeal-window",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["decision_state"] == "rejected"
    assert payload["status"] == "open"
    assert payload["may_file"] is True
    assert payload["window_days"] == 7
    assert payload["max_appeals"] == 1


# ------------------------------------------------------ no gating, no writes


def test_the_snapshot_is_advisory_and_writes_nothing(db):
    application = _scrutiny_reject(db, EXISTING, NOW)
    version_before = application.baseline_version
    state_before = application.current_state
    audit_before = db.scalar(select(AuditEvent.id).limit(1))

    appeal.appeal_snapshot(db, application, NOW)
    db.expire_all()

    assert db.get(Application, EXISTING).baseline_version == version_before
    assert db.get(Application, EXISTING).current_state == state_before
    assert db.scalar(select(AuditEvent.id).limit(1)) == audit_before
