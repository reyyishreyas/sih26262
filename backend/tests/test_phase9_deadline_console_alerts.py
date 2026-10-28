"""Phase 9.5: an approved console deadline changes actual alert timing."""

from copy import deepcopy
from datetime import timedelta

from sqlalchemy import select

from app.models import Alert, Role, Undertaking, User, UserRoleAssignment
from app.services import deadline_service, policy_config_service
from tests.conftest import DEMO_NOW


def _add_second_admin(db):
    administrator = db.scalars(select(Role).where(Role.name == "administrator")).one()
    reviewer = User(
        email="deadline-reviewer@demo.local",
        full_name="Deadline Review Administrator",
        password_hash="test-only-hash",
    )
    db.add(reviewer)
    db.flush()
    db.add(UserRoleAssignment(
        user_id=reviewer.id,
        role_id=administrator.id,
        scope_type="global",
        scope_id=None,
    ))
    db.commit()
    return reviewer


def test_console_deadline_update_moves_reminder_in_the_sweep(client, as_user, db):
    due_at = DEMO_NOW + timedelta(days=10)
    undertaking = Undertaking(
        application_id="app-existing-0003",
        obligation_key="phase9_5_timing_demo",
        title="Synthetic deadline timing check",
        due_at=due_at,
        status="pending",
    )
    db.add(undertaking)
    db.commit()

    # Ten days before the due time, the baseline 7-day reminder is not due.
    deadline_service.sweep(db, now=DEMO_NOW)
    assert db.scalar(select(Alert.id).where(
        Alert.entity_id == undertaking.id,
        Alert.alert_type == "undertaking_due",
        Alert.level == "reminder_7",
    )) is None

    changed = deepcopy(policy_config_service.baseline("deadlines"))
    reminder = next(entry for entry in changed["undertaking"] if entry["level"] == "reminder_7")
    reminder["offset_days"] = -15
    draft = client.post(
        "/api/v1/admin/policies/deadlines/drafts",
        headers=as_user("admin@demo.local"),
        json={"content": changed, "summary": "Move synthetic reminder earlier for timing demo"},
    )
    assert draft.status_code == 201, draft.text
    _add_second_admin(db)
    approved = client.post(
        f"/api/v1/admin/policies/deadlines/{draft.json()['version']}/approve",
        headers=as_user("deadline-reviewer@demo.local"),
    )
    assert approved.status_code == 200, approved.text

    # Same clock instant and same deadline: the approved -15-day offset now fires.
    deadline_service.sweep(db, now=DEMO_NOW)
    fired = db.scalar(select(Alert.id).where(
        Alert.entity_id == undertaking.id,
        Alert.alert_type == "undertaking_due",
        Alert.level == "reminder_7",
    ))
    assert fired is not None
