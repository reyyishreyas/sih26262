"""Phase 4.1: assignment by workload + conflict-of-interest (FR-12).

Covers the two advisory behaviours added by IMPL-0031:

* **Workload ordering** — ``assign_next_actors`` hands the case to the
  least-loaded eligible officer (``lowest_active_load``), so the officer with
  the fewest active assignments is picked first.
* **Conflict of interest** — an officer who declares a conflict on a case is
  hidden from that case (scope filter / ``can_access_application``) and kept
  out of the assignment pool; resolving or revoking the declaration restores
  both. A declaration never gates, moves or rejects a case (DEC-0003).

The COI behaviour is the "declared_only, hiding-only" placeholder from
``rules/assignment_policy.json`` and PRD Appendix E (no approved conflict
policy yet), so these tests pin the hiding, not a substantive conflict rule.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import CaseAssignment, User
from app.services.authorization_service import (
    can_access_application,
    effective_access,
)
from app.services.case_assignment_service import assign_next_actors
from app.services.seed import DEMO_PASSWORD, hash_password


def _create_scrutiny_officer(db, email: str, full_name: str) -> User:
    """A second active scrutiny officer, so the pool has a choice to make."""
    from app.core.permissions import SCRUTINY_OFFICER
    from app.models import Role, UserRoleAssignment

    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(DEMO_PASSWORD),
        is_active=True,
    )
    db.add(user)
    db.flush()
    role = db.scalars(select(Role).where(Role.name == SCRUTINY_OFFICER)).one()
    db.add(
        UserRoleAssignment(
            user_id=user.id, role_id=role.id, scope_type="assigned", scope_id=None
        )
    )
    db.flush()
    return user


def _load(db, application_id: str, user_id: str) -> int:
    return (
        db.query(CaseAssignment)
        .filter(
            CaseAssignment.application_id == application_id,
            CaseAssignment.user_id == user_id,
            CaseAssignment.revoked_at.is_(None),
        )
        .count()
    )


def _seeded(db, email: str) -> User:
    return db.scalars(select(User).where(User.email == email)).one()


# --- workload ordering -------------------------------------------------------


def test_workload_orders_to_least_loaded_officer(db, client):
    """The less-loaded officer gets the new case first."""
    from app.models import Application

    light = _create_scrutiny_officer(db, "officer-light@demo.local", "Light Officer")
    heavy = _create_scrutiny_officer(db, "officer-heavy@demo.local", "Heavy Officer")

    app = db.get(Application, "app-second-0002")
    app.current_state = "submitted"
    db.flush()

    # Give the heavy officer three real cases of their own; the light officer
    # none. Load is counted per-user across all cases, so this is a genuine
    # difference in active load.
    for _i in range(3):
        other = Application(
            institution_id=app.institution_id,
            category="new_technical",
            route_key="new_technical",
            cycle="2026-27",
            current_state="submitted",
            status="submitted",
        )
        db.add(other)
        db.flush()
        db.add(
            CaseAssignment(
                application_id=other.id, user_id=heavy.id, role_name="scrutiny_officer"
            )
        )
    db.flush()

    light_load_before = _load(db, app.id, light.id)
    assert _load(db, app.id, heavy.id) == 0  # heavy holds other cases, not this one
    assert light_load_before == 0

    created = assign_next_actors(db, app)
    created_users = {row.user_id for row in created}

    # The pool is genuinely populated, so the assertion below is evidence.
    assert created_users, "expected the eligible scrutiny pool to be populated"
    assert light.id in created_users
    assert heavy.id in created_users

    # The light officer (lower active load across all cases) comes first.
    # Workload ordering decides WHO is offered the case first; it does not
    # remove the heavier officer from an otherwise-eligible pool (soft cap).
    assert created[0].user_id == light.id, (
        "the least-loaded officer must be offered the case first"
    )
    db.flush()
    assert _load(db, app.id, light.id) == light_load_before + 1


def test_workload_does_not_override_jurisdiction(db, client):
    """Workload ordering never grants a case to an officer outside their scope."""
    from app.models import Application

    light = _create_scrutiny_officer(db, "officer-scope@demo.local", "Scoped Officer")
    app = db.get(Application, "app-second-0002")
    db.flush()

    # The scoped officer is not yet assigned; ordering alone must not put them
    # on a case their role does not act on. Force a state with no scrutiny
    # actor so candidacy is empty, and confirm nothing is created.
    app.current_state = "draft"
    db.flush()
    created = assign_next_actors(db, app)
    assert created == []
    assert _load(db, app.id, light.id) == 0


# --- conflict of interest: hide ---------------------------------------------


def test_coi_hides_case_from_declaring_officer(db, client):
    """An open declaration removes the case from the declarer's view."""
    officer = _seeded(db, "scrutiny@demo.local")
    application_id = "app-main-0001"
    # The API commits in its own session; the test session must not hold the
    # only write transaction open or SQLite reports "database is locked".
    db.commit()

    headers = as_user_factory(client, "scrutiny@demo.local")
    resp = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "financial_interest", "description": "equity in applicant"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["conflict_type"] == "financial_interest"
    assert body["application_id"] == application_id

    # Before: the assigned officer could see the case. After: they cannot.
    # expire() drops the identity map so this session re-reads the row the
    # API's own session just committed.
    from app.models import Application

    db.expire_all()
    app = db.get(Application, application_id)
    access = effective_access(db, officer)
    # Recompute: an open COI must flip the access to hidden.
    assert can_access_application(db, access, app) is False


def test_coi_keeps_declarer_out_of_assignment_pool(db, client):
    """A declared conflict keeps the officer out of the assignment pool."""
    from app.models import Application

    # Two eligible scrutiny officers. If the only officer were the declarer,
    # skipping them would leave the pool empty and the test would prove
    # nothing; the second officer is what makes the exclusion observable.
    officer = _seeded(db, "scrutiny@demo.local")
    other = _create_scrutiny_officer(db, "officer-pool@demo.local", "Pool Officer")
    application_id = "app-second-0002"
    app = db.get(Application, application_id)
    app.current_state = "submitted"
    # The declarer must already hold the case: an unassigned officer cannot see
    # it, so they could never declare on it. The second officer is what makes
    # the exclusion observable rather than a silent empty pool.
    db.add(
        CaseAssignment(
            application_id=application_id, user_id=officer.id, role_name="scrutiny_officer"
        )
    )
    # Commit before the API call so its own session can take the write lock.
    db.commit()

    # A rejected declaration would make the exclusion below vacuous, so the
    # status is part of the test, not incidental.
    declared = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "personal_relationship"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )
    assert declared.status_code == 200, declared.text

    db.expire_all()
    app = db.get(Application, application_id)
    created = assign_next_actors(db, app)
    created_users = {row.user_id for row in created}

    # Control: the pool is not empty, so the officer's absence is meaningful.
    assert created_users, "expected the eligible scrutiny pool to be populated"
    assert other.id in created_users, "the conflict-free officer must still be offered the case"
    assert officer.id not in created_users, (
        "an officer with an open conflict must not be handed the case"
    )


def test_coi_hides_only_for_the_declarer(db, client):
    """A COI hides the case from the declarer, not from other officers."""
    from app.models import Application

    declarer = _seeded(db, "scrutiny@demo.local")
    other = _create_scrutiny_officer(db, "officer-other@demo.local", "Other Officer")
    application_id = "app-main-0001"
    # Both officers must hold the case, so the only difference between them is
    # the declarer's open conflict. Without this the other officer would fail
    # the base access check and the test would prove nothing about COI.
    db.add(
        CaseAssignment(
            application_id=application_id, user_id=other.id, role_name="scrutiny_officer"
        )
    )
    db.commit()

    client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "prior_affiliation"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )

    db.expire_all()
    app = db.get(Application, application_id)
    declarer_access = effective_access(db, declarer)
    other_access = effective_access(db, other)
    assert can_access_application(db, declarer_access, app) is False
    # A different officer is unaffected — hiding is per-declarer.
    assert can_access_application(db, other_access, app) is True


def test_coi_never_gates_a_case_transition(db, client):
    """A declaration is advisory: the case still moves; it is not refused."""
    from app.models import Application

    application_id = "app-main-0001"
    db.commit()
    client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "other", "description": "declared"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )
    db.expire_all()
    app = db.get(Application, application_id)
    # The state itself is unchanged by a declaration — COI is not a gate.
    assert app.current_state == "scrutiny"


# --- conflict of interest: resolve / restore --------------------------------


def test_coi_resolve_restores_visibility(db, client):
    """Resolving a declaration restores the case to the declarer's view."""
    officer = _seeded(db, "scrutiny@demo.local")
    application_id = "app-main-0001"
    admin_headers = as_user_factory(client, "admin@demo.local")
    db.commit()

    declare_resp = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "financial_interest"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )
    declaration_id = declare_resp.json()["id"]

    review_resp = client.post(
        f"/api/v1/conflicts-of-interest/{declaration_id}/review",
        json={"status": "resolved", "resolution_note": "no equity in applicant"},
        headers=admin_headers,
    )
    assert review_resp.status_code == 200, review_resp.text
    assert review_resp.json()["status"] == "resolved"
    assert review_resp.json()["reviewer_id"] is not None

    from app.models import Application

    db.expire_all()
    app = db.get(Application, application_id)
    access = effective_access(db, officer)
    assert can_access_application(db, access, app) is True


def test_coi_revoked_also_restores(db, client):
    """Revoking a declaration also restores visibility (a mistaken hold is recoverable)."""
    officer = _seeded(db, "scrutiny@demo.local")
    application_id = "app-main-0001"
    admin_headers = as_user_factory(client, "admin@demo.local")
    db.commit()

    declaration_id = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "other"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    ).json()["id"]

    resp = client.post(
        f"/api/v1/conflicts-of-interest/{declaration_id}/review",
        json={"status": "revoked"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    from app.models import Application

    db.expire_all()
    app = db.get(Application, application_id)
    access = effective_access(db, officer)
    assert can_access_application(db, access, app) is True


def test_coi_redeclare_is_idempotent(db, client):
    """Re-declaring while one is open returns the existing declaration."""
    application_id = "app-main-0001"
    headers = as_user_factory(client, "scrutiny@demo.local")
    db.commit()
    first = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "financial_interest"},
        headers=headers,
    ).json()
    second = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "other", "description": "a second try"},
        headers=headers,
    ).json()
    assert first["id"] == second["id"], (
        "a retry must not create a second open declaration"
    )


def test_coi_unknown_type_is_rejected(db, client):
    """An unlisted conflict type is a 422, not a silent acceptance."""
    db.commit()
    resp = client.post(
        "/api/v1/applications/app-main-0001/conflicts-of-interest",
        json={"conflict_type": "made_up_type"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )
    assert resp.status_code == 422


def test_coi_review_unknown_status_is_rejected(db, client):
    """A reviewer cannot set a status other than resolved/revoked."""
    application_id = "app-main-0001"
    db.commit()
    declaration_id = client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "other"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    ).json()["id"]
    resp = client.post(
        f"/api/v1/conflicts-of-interest/{declaration_id}/review",
        json={"status": "open"},
        headers=as_user_factory(client, "admin@demo.local"),
    )
    assert resp.status_code == 422


def test_coi_lists_declarations_on_case(db, client):
    """The case view lists its declarations (reviewer + officer)."""
    application_id = "app-main-0001"
    db.commit()
    client.post(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        json={"conflict_type": "financial_interest"},
        headers=as_user_factory(client, "scrutiny@demo.local"),
    )
    rows = client.get(
        f"/api/v1/applications/{application_id}/conflicts-of-interest",
        headers=as_user_factory(client, "admin@demo.local"),
    ).json()
    assert any(r["application_id"] == application_id for r in rows)


# A tiny shim so the COI tests that need per-user auth headers can build them
# without importing the conftest fixture into this module's signature churn.
def as_user_factory(client, email: str) -> dict[str, str]:
    from tests.conftest import _token

    return {"Authorization": f"Bearer {_token(email)}"}
