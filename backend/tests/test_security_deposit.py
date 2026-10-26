"""Security Deposit: the FR-33 penalty schedule and withdrawal marker.

Plan 3.6 builds `security_deposit_policy.json` + `security_deposit.py`: the
PRD §7 security-deposit penalty rules (proof + Affidavit 3, 15-day window,
10% penalty up to 31 May, 20% up to 31 July, withdrawn after — APH cl. 2.25f)
and the §11 day-1/10/14 reminder cadence. Every value is Unverified placeholder
configuration.

Safety properties under test:

- **The figures are labelled unverified/placeholder/advisory, never AICTE rules.**
- **The penalty band is computed from a date against the configured fixed
  dates**, never hard-coded — 31 May / 31 July drive 10% / 20%.
- **The withdrawal marker is advisory and never withdraws a case**: past
  31 July it sets `withdrawal_flagged` for display, but an actual withdrawal
  is a NEW REGULATORY STATE (rule 15), not a config change — nothing moves.
- **The snapshot is read-only** (DEC-0003): no version bump, no state change,
  no audit event.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from app.models import Application, AuditEvent, Undertaking
from app.services import security_deposit as sd
from app.services.policy import RULES_DIR, security_deposit_policy

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)  # Thursday; matches DEMO_NOW

EXISTING = "app-existing-0003"  # scrutiny, in scope, assigned to scrutiny officer
MAIN = "app-main-0001"          # scrutiny, in scope (new_technical route)
SECOND = "app-second-0002"      # submitted (not a decision), region south

SCRUTINY_EMAIL = "scrutiny@demo.local"


def _config() -> dict:
    return security_deposit_policy()


def _approve(db, application_id: str) -> Application:
    """Drive a seeded scrutiny-stage case to `approved` (the SD clock's anchor)."""
    from app.core.clock import FixedClock, get_clock, set_clock
    from app.models import User
    from app.services import workflow_service
    from app.services.authorization_service import effective_access

    user = db.query(User).filter_by(email=SCRUTINY_EMAIL).one()
    access = effective_access(db, user)
    prior = get_clock()
    set_clock(FixedClock(NOW))
    try:
        decision = workflow_service.request_transition(
            db, access, application_id, "approve", reason="security-deposit test decision"
        )
        assert decision.accepted, decision.reasons
    finally:
        set_clock(prior)
    return db.get(Application, application_id)


# ------------------------------------------------------------- the config


def test_the_policy_loads_unverified_placeholder_and_advisory():
    config = _config()
    assert config["status"] == "unverified"
    assert config["placeholder"] is True
    assert config["advisory_only"] is True


def test_it_cites_fr_33_and_the_unverified_caveat():
    source = _config()["source"]
    assert "FR-33" in source
    assert "APH cl. 2.25f" in source or "2.25f" in source


def test_the_proof_window_is_15_days():
    assert _config()["proof_window_days"] == 15  # FR-33: 15-day proof window


def test_the_penalty_schedule_is_10_then_20():
    schedule = _config()["penalty_schedule"]
    assert [e["penalty_percent"] for e in schedule] == [10, 20]
    assert [e["on_or_before"] for e in schedule] == ["05-31", "07-31"]


def test_the_withdrawal_flag_is_after_07_31():
    assert _config()["withdrawal_flag"]["after"] == "07-31"


def test_the_policy_file_is_readable_json_in_the_rules_dir():
    parsed = json.loads((Path(RULES_DIR) / "security_deposit_policy.json").read_text())
    assert parsed["proof_window_days"] == 15
    assert parsed["penalty_schedule"]


# ------------------------------------------------------ penalty date maths


def test_a_date_in_may_gets_the_10_percent_band():
    band = sd.penalty_for_date(date(2026, 5, 15))
    assert band.penalty_percent == 10
    assert band.withdrawal_flagged is False


def test_31_may_still_gets_10_percent():
    # "up to and including 31 May" — the boundary is inclusive.
    band = sd.penalty_for_date(date(2026, 5, 31))
    assert band.penalty_percent == 10


def test_a_date_in_june_gets_the_20_percent_band():
    band = sd.penalty_for_date(date(2026, 6, 15))
    assert band.penalty_percent == 20
    assert band.withdrawal_flagged is False


def test_31_july_still_gets_20_percent():
    band = sd.penalty_for_date(date(2026, 7, 31))
    assert band.penalty_percent == 20
    assert band.withdrawal_flagged is False


def test_a_date_after_31_july_flags_withdrawal_with_no_penalty():
    """'withdrawn after 31 July' — advisory marker, no penalty percent."""
    band = sd.penalty_for_date(date(2026, 8, 1))
    assert band.penalty_percent is None
    assert band.withdrawal_flagged is True


def test_the_dates_are_calendar_anchored_not_relative():
    """The schedule is fixed calendar dates, so it is the same every year."""
    assert sd.penalty_for_date(date(2027, 5, 10)).penalty_percent == 10
    assert sd.penalty_for_date(date(2027, 8, 2)).withdrawal_flagged is True


# -------------------------------------------------------- the SD snapshot


def test_an_unapproved_case_is_not_applicable(db):
    application = db.get(Application, SECOND)  # submitted — no deposit yet
    snapshot = sd.sd_snapshot(db, application, NOW)
    assert snapshot["status"] == "not_applicable"
    assert snapshot["penalty"] is None
    assert snapshot["withdrawal_flagged"] is False


def test_an_approved_case_reports_the_proof_deadline(db):
    application = _approve(db, EXISTING)
    assert application.current_state == "approved"
    snapshot = sd.sd_snapshot(db, application, NOW)
    assert snapshot["status"] == "open"
    # The 15-day window runs from the decision day (2026-10-22 → 2026-11-06).
    assert snapshot["proof_deadline"] == "2026-11-06"
    assert snapshot["proof_window_days"] == 15
    assert snapshot["placeholder"] is True
    assert snapshot["advisory_only"] is True


def test_the_snapshot_reports_the_penalty_band_for_today(db):
    """Today (2026-10-22) is past 31 July → the withdrawal marker is set."""
    application = _approve(db, EXISTING)
    snapshot = sd.sd_snapshot(db, application, NOW)
    assert snapshot["withdrawal_flagged"] is True
    assert snapshot["penalty"]["penalty_percent"] is None


def test_the_snapshot_is_advisory_and_writes_nothing(db):
    application = _approve(db, EXISTING)
    version_before = application.baseline_version
    state_before = application.current_state
    audit_before = db.scalar(select(AuditEvent.id).limit(1))

    sd.sd_snapshot(db, application, NOW)
    db.expire_all()

    assert db.get(Application, EXISTING).baseline_version == version_before
    assert db.get(Application, EXISTING).current_state == state_before
    assert db.scalar(select(AuditEvent.id).limit(1)) == audit_before


def test_the_snapshot_reflects_the_undertaking_status(db):
    """When the SD proof undertaking exists, its status rides the snapshot."""
    application = _approve(db, EXISTING)
    db.add(
        Undertaking(
            application_id=EXISTING,
            obligation_key=sd.OBLIGATION_KEY,
            title="Security Deposit proof + Affidavit 3",
            due_at=datetime(2026, 11, 6, 23, 59, 59, tzinfo=UTC),
            status="submitted",
        )
    )
    db.commit()
    snapshot = sd.sd_snapshot(db, application, NOW)
    assert snapshot["undertaking_status"] == "submitted"


# ----------------------------------------------------------- the API


def test_the_security_deposit_endpoint_is_served_to_signed_in_users(client, as_user):
    body = client.get(
        f"/api/v1/applications/{EXISTING}/security-deposit",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["placeholder"] is True
    assert payload["advisory_only"] is True
    assert payload["status"] == "not_applicable"  # seeded case is still in scrutiny


def test_the_security_deposit_endpoint_needs_a_token(client):
    assert (
        client.get(f"/api/v1/applications/{EXISTING}/security-deposit").status_code
        == 401
    )


def test_the_security_deposit_endpoint_respects_application_scope(client, as_user):
    """The college sees only its own case, never another institution's."""
    headers = as_user("institution@demo.local")
    allowed = client.get(
        f"/api/v1/applications/{MAIN}/security-deposit", headers=headers
    )
    assert allowed.status_code == 200
    denied = client.get(
        f"/api/v1/applications/{SECOND}/security-deposit", headers=headers
    )
    assert denied.status_code in (403, 404)


def test_the_endpoint_reports_an_open_window_for_an_approved_case(client, as_user, db):
    _approve(db, EXISTING)
    body = client.get(
        f"/api/v1/applications/{EXISTING}/security-deposit",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert body.status_code == 200
    payload = body.json()
    assert payload["status"] == "open"
    assert payload["proof_deadline"] == "2026-11-06"
    assert payload["withdrawal_flagged"] is True
