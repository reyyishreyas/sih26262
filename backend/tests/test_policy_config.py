"""Policy draft history, four-eyes approval and live deadline config."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.models import AuditEvent, PolicyConfigVersion, Role, User, UserRoleAssignment
from app.services import policy_config_service
from app.services.policy import thresholds


def _second_admin(db):
    role = db.scalars(select(Role).where(Role.name == "administrator")).one()
    user = User(
        email="second-admin@demo.local",
        full_name="Second Demo Administrator",
        password_hash="test-only-hash",
    )
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(
        user_id=user.id, role_id=role.id, scope_type="global", scope_id=None
    ))
    db.commit()
    return user


def test_deadline_draft_requires_four_eyes_and_becomes_active(client, as_user, db):
    original = policy_config_service.baseline("deadlines")
    changed = deepcopy(original)
    changed["undertaking"][0]["offset_days"] = -29
    created = client.post("/api/v1/admin/policies/deadlines/drafts", headers=as_user("admin@demo.local"), json={
        "content": changed, "summary": "Move the first undertaking reminder one day later",
    })
    assert created.status_code == 201, created.text
    version = created.json()
    assert version["status"] == "draft"
    assert thresholds("undertaking", db=db)[0].offset_days == -30

    same_actor = client.post(
        f"/api/v1/admin/policies/deadlines/{version['version']}/approve",
        headers=as_user("admin@demo.local"),
    )
    assert same_actor.status_code == 409
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "policy.approval_rejected"))

    _second_admin(db)
    approved = client.post(
        f"/api/v1/admin/policies/deadlines/{version['version']}/approve",
        headers=as_user("second-admin@demo.local"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert thresholds("undertaking", db=db)[0].offset_days == -29

    replay = client.post(
        f"/api/v1/admin/policies/deadlines/{version['version']}/approve",
        headers=as_user("admin@demo.local"),
    )
    assert replay.status_code == 409


def test_invalid_draft_is_audited_and_never_saved(client, as_user, db):
    invalid = client.post("/api/v1/admin/policies/deadlines/drafts", headers=as_user("admin@demo.local"), json={
        "content": {"undertaking": [{"level": "x", "offset_days": 5000, "severity": "critical"}]},
        "summary": "Bad deadline test",
    })
    assert invalid.status_code == 422
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "policy.draft_rejected"))
    assert db.scalar(select(PolicyConfigVersion.id)) is None


def test_verified_fee_draft_requires_complete_source_metadata(client, as_user):
    content = deepcopy(policy_config_service.baseline("fees"))
    content.update(status="verified", placeholder=False)
    content["verification"] = {"reviewer": "Reviewer"}
    response = client.post("/api/v1/admin/policies/fees/drafts", headers=as_user("admin@demo.local"), json={
        "content": content, "summary": "Incomplete source verification must fail",
    })
    assert response.status_code == 422
    assert "named reviewer" in response.json()["detail"]


def test_approved_policy_snapshot_cannot_be_changed_or_deleted(db):
    user = db.query(User).filter_by(email="admin@demo.local").one()
    row = PolicyConfigVersion(
        policy_key="templates", version=1, status="approved", content={"templates": []},
        content_hash="hash", summary="approved test", created_by=user.id,
    )
    db.add(row)
    db.commit()
    row.content = {"templates": [{"key": "new"}]}
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
    persisted = db.get(PolicyConfigVersion, row.id)
    with pytest.raises(ValueError, match="cannot be deleted"):
        db.delete(persisted)
        db.flush()
    db.rollback()
