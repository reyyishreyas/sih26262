"""Phase 4.4: the deficiency report and the compliance window (FR-15).

PRD FR-15: "Deficiency report, compliance window, compliance upload to
Re-Scrutiny" (APH s2.3.3b/2.4 as the PRD cites it). The row loop itself
(draft -> open -> addressed -> closed, resubmit -> Re-Scrutiny) already
exists and is covered by ``test_deficiency_loop``; this suite covers the
two composed views on top of it:

- the **report**: one read that joins the issued deficiencies with the
  issue instant, the reply window and what has come back;
- the **window**: a labelled-placeholder deadline that raises the PRD s11
  reminder cadence ("On issue, 7d, 2d, due date", line 281) through the
  sweep, and never blocks anything (DEC-0003).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.clock import FixedClock, get_clock, set_clock
from app.models import (
    Alert,
    Application,
    AuditEvent,
    Deficiency,
    User,
    WorkflowTransition,
)
from app.services import compliance, deadline_service, workflow_service
from app.services.policy import RULES_DIR, compliance_policy, thresholds

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)  # Thursday; matches DEMO_NOW

MAIN = "app-main-0001"  # new_technical, scrutiny, institution-owned;
                       # the only seeded route with BOTH the return and
                       # resubmit legs (existing_technical has neither —
                       # noted in IMPL-0035 as a route-config observation)
SECOND = "app-second-0002"      # other institution's case (scope 404)
SCRUTINY_EMAIL = "scrutiny@demo.local"
INSTITUTION_EMAIL = "institution@demo.local"

WINDOW_DAYS = 10  # the labelled placeholder in compliance_policy.json


# --------------------------------------------------------------- helpers


def _user_id(db, email: str = SCRUTINY_EMAIL) -> str:
    """`created_by`/`actor_id` are real FKs — no placeholder ids here."""
    return db.scalar(select(User.id).where(User.email == email))


def _add_drafts(db, application_id: str, count: int = 2) -> None:
    actor = _user_id(db)
    for i in range(count):
        db.add(
            Deficiency(
                application_id=application_id,
                category="document_deficiency",
                field_name=f"field_{i}",
                explanation=f"Draft line {i} needs review",
                corrective_action=f"Fix line {i}",
                status="draft",
                created_by=actor,
            )
        )
    db.commit()


def _transition(
    db,
    access,
    action: str,
    when: datetime,
    reason: str | None = None,
    reason_code: str | None = None,
):
    """Drive one workflow transition at instant `when` (frozen clock)."""
    prior = get_clock()
    set_clock(FixedClock(when))
    try:
        outcome = workflow_service.request_transition(
            db, access, MAIN, action, reason=reason or "", reason_code=reason_code
        )
        assert outcome.accepted, outcome.reasons
        return outcome
    finally:
        set_clock(prior)


def _issue(db, access_for, when: datetime = NOW) -> Application:
    """Draft two deficiencies and return the case: the report is issued."""
    _add_drafts(db, MAIN, 2)
    _transition(
        db, access_for(SCRUTINY_EMAIL), "return_for_clarification", when,
        reason="deficiency report test return",
        reason_code="RC-CLARIFICATION",  # FR-28: a code is mandatory on return
    )
    return db.get(Application, MAIN)


def _view(db, application, now: datetime = NOW, include_drafts: bool = True) -> dict:
    return compliance.report_view(
        db, application, now, include_drafts=include_drafts
    )


# ------------------------------------------------------------- the config


def test_the_policy_loads_unverified_placeholder_and_advisory():
    config = compliance_policy()
    assert config["status"] == "unverified"
    assert config["placeholder"] is True
    assert config["advisory_only"] is True


def test_the_source_cites_fr_15_and_the_open_window_question():
    source = compliance_policy()["source"]
    assert "FR-15" in source
    # The window LENGTH is not stated anywhere — PRD §19 Q1 keeps reply-time
    # targets open, so the config must say so rather than read as a rule.
    assert "s19" in source or "Q1" in source
    assert "window" in source.lower()


def test_the_window_days_is_a_labelled_placeholder():
    config = compliance_policy()
    assert config["window_days"] == WINDOW_DAYS
    assert "PLACEHOLDER" in config["window_days_note"]
    assert "s19" in config["window_days_note"]


def test_the_reminder_ladder_is_the_prd_deficiency_cadence():
    """PRD §11 line 281: "Deficiency issued | ... | On issue, 7d, 2d, due
    date | Regional on miss" — the cadence is from the PRD, expressed as
    offsets from the window close date."""
    ladder = {t.level: t for t in thresholds("compliance")}
    assert set(ladder) == {"compliance_7d", "compliance_2d", "compliance_due"}
    assert ladder["compliance_7d"].offset_days == -7
    assert ladder["compliance_7d"].severity == "info"
    assert ladder["compliance_2d"].offset_days == -2
    assert ladder["compliance_2d"].severity == "warning"
    assert ladder["compliance_due"].offset_days == 0
    assert ladder["compliance_due"].severity == "critical"


def test_the_config_file_is_readable_json_in_the_rules_dir():
    with open(RULES_DIR / "compliance_policy.json", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["window_days"] == WINDOW_DAYS


def test_the_window_matches_the_configured_value():
    assert compliance.window_days() == WINDOW_DAYS
    assert compliance.config()["advisory_only"] is True


# ------------------------------------------------- the report, before issue


def test_a_case_without_any_deficiency_reports_none(db):
    application = db.get(Application, MAIN)
    view = _view(db, application)
    assert view["status"] == "none"
    assert view["window_status"] == "not_started"
    assert view["issued_at"] is None
    assert view["deficiencies"] == []


def test_a_draft_report_is_labelled_draft_for_the_officer(db):
    _add_drafts(db, MAIN, 2)
    application = db.get(Application, MAIN)
    view = _view(db, application)
    assert view["status"] == "draft"
    assert view["counts"]["draft"] == 2
    assert len(view["deficiencies"]) == 2
    assert view["note"] and "officer" in view["note"].lower()
    # Drafts are not part of any issued reply: the window never starts.
    assert view["issued_at"] is None
    assert view["window_status"] == "not_started"


def test_the_institution_is_always_answered_not_issued_and_never_sees_drafts(db):
    application = db.get(Application, MAIN)

    # Nothing raised at all: the institution must get the same answer as a
    # case with hidden drafts, or the status value alone would leak that an
    # officer is working on something.
    with_nothing = _view(db, application, include_drafts=False)
    _add_drafts(db, MAIN, 2)
    with_drafts = _view(db, application, include_drafts=False)

    assert with_nothing["status"] == "not_issued"
    assert with_drafts["status"] == with_nothing["status"]
    assert with_drafts["deficiencies"] == []
    assert with_drafts["counts"] == {
        "draft": 0,
        "open": 0,
        "addressed": 0,
        "closed": 0,
    }
    assert with_drafts["window_status"] == "not_started"


# -------------------------------------------------- the report, once issued


def test_returning_the_case_issues_the_report(db, access_for):
    _issue(db, access_for)
    application = db.get(Application, MAIN)
    view = _view(db, application)

    assert view["status"] == "issued"
    assert datetime.fromisoformat(view["issued_at"]) == NOW
    # The return transition promotes draft rows to open (existing loop).
    assert view["counts"] == {"draft": 0, "open": 2, "addressed": 0, "closed": 0}
    assert [row["status"] for row in view["deficiencies"]] == ["open", "open"]


def test_the_window_closes_at_the_end_of_the_configured_day(db, access_for):
    _issue(db, access_for)
    application = db.get(Application, MAIN)
    view = _view(db, application)

    issued = datetime.fromisoformat(view["issued_at"])
    closes = datetime.fromisoformat(view["closes_at"])
    # End of the (issue day + window_days - 1), the same end-of-day
    # convention as the appeal and undertaking clocks — end of day in the
    # configured business timezone, stored (and shown) in UTC.
    assert closes.date() - issued.date() == timedelta(days=WINDOW_DAYS - 1)
    from zoneinfo import ZoneInfo

    from app.core.config import get_settings

    local_close = closes.astimezone(
        ZoneInfo(get_settings().business_timezone)
    )
    assert (local_close.hour, local_close.minute) == (23, 59)
    assert view["window_status"] == "open"
    assert view["days_remaining"] > 0
    assert view["overdue"] is False
    assert view["placeholder"] is True
    assert view["advisory_only"] is True


def test_the_window_goes_overdue_and_says_it_never_blocks(db, access_for):
    _issue(db, access_for)
    application = db.get(Application, MAIN)
    after = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)  # past the close
    view = _view(db, application, now=after)

    assert view["window_status"] == "overdue"
    assert view["overdue"] is True
    assert view["days_remaining"] == 0
    assert view["note"] and "never blocks" in view["note"]
    assert view["note"] and "7d, 2d, due date" in view["note"]


def test_the_institution_sees_the_issued_report(db, access_for):
    _issue(db, access_for)
    application = db.get(Application, MAIN)
    view = _view(db, application, include_drafts=False)

    assert view["status"] == "issued"
    assert len(view["deficiencies"]) == 2
    assert view["counts"]["open"] == 2
    assert view["window_status"] == "open"


def test_the_report_is_computed_on_read_and_stores_nothing(db, access_for):
    application = _issue(db, access_for)

    def snapshot() -> tuple:
        def count(model) -> int:
            return db.scalar(
                select(func.count()).select_from(model)
            )

        return (
            count(Deficiency),
            count(WorkflowTransition),
            count(AuditEvent),
            application.baseline_version,
            application.current_state,
        )

    before = snapshot()
    _view(db, application)
    _view(db, application, include_drafts=False)
    _view(db, application, now=datetime(2026, 11, 5, tzinfo=UTC))
    assert snapshot() == before


# ---------------------------------------------------- the Re-Scrutiny leg


def test_resubmitting_records_the_reply_and_the_rescrutiny_leg(db, access_for):
    _issue(db, access_for)
    _transition(
        db, access_for(INSTITUTION_EMAIL), "resubmit", NOW + timedelta(days=1)
    )
    application = db.get(Application, MAIN)
    view = _view(db, application, now=NOW + timedelta(days=1, hours=1))

    assert view["window_status"] == "received"
    assert datetime.fromisoformat(view["resubmitted_at"]) == NOW + timedelta(days=1)
    assert view["overdue"] is False
    # The reply is in, but no deficiency row has been closed yet: the case
    # is awaiting Re-Scrutiny (the officer's verification of the uploads).
    assert view["awaiting_re_scrutiny"] is True
    # Reminders stop the moment the reply is in ("alerts stop when task
    # closes") — the sweep has nothing left to raise for this report.
    assert compliance.compliance_window_item(
        db, application, NOW + timedelta(days=2)
    ) is None


def test_an_expired_window_never_blocks_the_resubmission(db, access_for):
    """DEC-0003 + the report's own wording: a deadline is a signal, not a
    lock. The institution that answers late is still let in."""
    _issue(db, access_for)
    late = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)  # two days past the close
    application = db.get(Application, MAIN)

    assert _view(db, application, now=late)["window_status"] == "overdue"

    outcome = _transition(db, access_for(INSTITUTION_EMAIL), "resubmit", late)
    assert outcome.accepted, outcome.reasons

    view = _view(db, application, now=late)
    assert view["window_status"] == "received"
    assert view["awaiting_re_scrutiny"] is True


# -------------------------------------------------------- the sweep ladder


def test_no_window_item_without_an_issued_report(db):
    application = db.get(Application, MAIN)
    assert compliance.compliance_window_item(db, application, NOW) is None

    _add_drafts(db, MAIN, 1)  # drafts alone are not an issued report
    assert compliance.compliance_window_item(db, application, NOW) is None


def test_the_window_item_rides_the_issue_cycle_key(db, access_for):
    _issue(db, access_for)
    application = db.get(Application, MAIN)
    item = compliance.compliance_window_item(db, application, NOW)

    assert item is not None
    assert item.alert_type == "compliance_window"
    assert item.application_id == MAIN
    # Keyed by the ISSUE instant, so a re-return starts a fresh reminder
    # cycle instead of reusing the old dedupe key.
    assert item.cycle_key == f"compliance:{NOW.date().isoformat()}"
    assert item.payload["window_days"] == WINDOW_DAYS
    assert item.payload["placeholder"] is True
    closes = datetime.fromisoformat(
        _view(db, application)["closes_at"]
    )
    assert item.due_at == closes


def test_a_re_return_starts_a_fresh_reminder_cycle(db, access_for):
    _issue(db, access_for)
    _transition(
        db, access_for(INSTITUTION_EMAIL), "resubmit", NOW + timedelta(days=1)
    )
    # Re-returned after Re-Scrutiny: the case must first re-enter scrutiny
    # (start_scrutiny), then a second issue instant starts a new cycle.
    second_issue = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
    _transition(
        db, access_for(SCRUTINY_EMAIL), "start_scrutiny",
        second_issue - timedelta(hours=1),
    )
    _transition(
        db, access_for(SCRUTINY_EMAIL), "return_for_clarification", second_issue,
        reason="second return after re-scrutiny",
        reason_code="RC-CLARIFICATION",
    )
    application = db.get(Application, MAIN)

    item = compliance.compliance_window_item(db, application, second_issue)
    assert item is not None
    assert item.cycle_key == f"compliance:{second_issue.date().isoformat()}"
    assert item.cycle_key != f"compliance:{NOW.date().isoformat()}"


def test_the_sweep_raises_the_7d_2d_and_due_reminders(db, access_for):
    _issue(db, access_for)
    clock = FixedClock(NOW)
    set_clock(clock)
    try:
        def levels() -> list[str]:
            return [
                row.level
                for row in db.scalars(
                    select(Alert).where(Alert.alert_type == "compliance_window")
                ).all()
            ]

        deadline_service.sweep(db, clock.now())
        assert levels() == []  # 7 days out: still quiet

        # Day 3 (2026-10-25): past the "7d before close" threshold.
        clock.advance(days=3)
        deadline_service.sweep(db, clock.now())
        assert levels() == ["compliance_7d"]
        alert = db.scalars(
            select(Alert).where(Alert.level == "compliance_7d")
        ).first()
        assert alert.payload["window_days"] == WINDOW_DAYS
        assert alert.payload["placeholder"] is True

        # Idempotent: a second sweep at the same instant creates nothing.
        def alert_count() -> int:
            return db.scalar(
                select(func.count())
                .select_from(Alert)
                .where(Alert.alert_type == "compliance_window")
            )

        count = alert_count()
        deadline_service.sweep(db, clock.now())
        assert alert_count() == count

        # 2026-10-29 19:00: past the "2d before close" threshold.
        clock.advance(days=4, hours=10)
        deadline_service.sweep(db, clock.now())
        assert set(levels()) == {"compliance_7d", "compliance_2d"}

        # 2026-10-31 19:00: the due date itself ("Regional on miss").
        clock.advance(days=2)
        deadline_service.sweep(db, clock.now())
        due = db.scalars(
            select(Alert).where(Alert.level == "compliance_due")
        ).first()
        assert due is not None
        assert due.payload["severity"] == "critical"
        assert set(levels()) == {
            "compliance_7d",
            "compliance_2d",
            "compliance_due",
        }
    finally:
        set_clock(None)


# ---------------------------------------------------------------- the API


def test_the_report_requires_a_token(client):
    response = client.get(f"/api/v1/applications/{MAIN}/deficiency-report")
    assert response.status_code == 401


def test_the_officer_reads_the_draft_report_over_the_api(client, as_user, db):
    _add_drafts(db, MAIN, 2)
    response = client.get(
        f"/api/v1/applications/{MAIN}/deficiency-report",
        headers=as_user(SCRUTINY_EMAIL),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["counts"]["draft"] == 2
    assert body["window_status"] == "not_started"


def test_the_institution_never_sees_a_draft_over_the_api(client, as_user, db):
    _add_drafts(db, MAIN, 2)
    response = client.get(
        f"/api/v1/applications/{MAIN}/deficiency-report",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_issued"
    assert body["deficiencies"] == []
    assert body["counts"]["draft"] == 0


def test_the_issued_report_reaches_the_institution_over_the_api(
    client, as_user, db, access_for
):
    _issue(db, access_for)
    response = client.get(
        f"/api/v1/applications/{MAIN}/deficiency-report",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "issued"
    assert body["window_status"] == "open"
    assert len(body["deficiencies"]) == 2
    assert body["placeholder"] is True


def test_the_report_is_scope_filtered(client, as_user):
    """An other-institution case looks absent, never leaked as a report."""
    response = client.get(
        f"/api/v1/applications/{SECOND}/deficiency-report",
        headers=as_user(INSTITUTION_EMAIL),
    )
    assert response.status_code == 404
