"""Production-hardening behaviour: headers, health, throttling, upload safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.adapters.malware import (
    MalwareDetected,
    MalwareScannerError,
    ScanResult,
)
from app.core.config import Settings
from app.models import (
    Alert,
    AlertDelivery,
    AuditEvent,
    Document,
    LoginAttempt,
    RuleVersion,
    User,
)
from app.services import login_throttle, malware_service
from app.services.retention_service import apply_retention, plan_retention


def test_security_headers_and_request_id(client):
    response = client.get("/health/live", headers={"X-Request-ID": "trace-12345678"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-12345678"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_invalid_request_id_is_replaced(client):
    response = client.get("/health/live", headers={"X-Request-ID": "bad id"})
    assert response.headers["X-Request-ID"] != "bad id"
    assert len(response.headers["X-Request-ID"]) == 32


def test_liveness_and_readiness_endpoints(client):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["components"]["operational"].startswith("ok:")


def test_validation_errors_are_structured(client):
    response = client.post("/api/v1/auth/login", json={"email": "a@b.c"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["request_id"]
    assert body["detail"]


def test_login_is_throttled_after_repeated_failures(client):
    for attempt in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "scrutiny@demo.local", "password": "wrong-password"},
        )
        assert response.status_code == 401, attempt

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "scrutiny@demo.local", "password": "DemoPassw0rd!"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["code"] == "http_error"


def test_successful_login_clears_recent_failures(client):
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "scrutiny@demo.local", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "scrutiny@demo.local", "password": "DemoPassw0rd!"},
        ).status_code
        == 200
    )
    for _ in range(4):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "scrutiny@demo.local", "password": "wrong"},
            ).status_code
            == 401
        )
    # Four failures after the reset is still below the limit of five.
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "scrutiny@demo.local", "password": "DemoPassw0rd!"},
        ).status_code
        == 200
    )


def test_successful_login_does_not_clear_address_failures(db):
    """One valid account must not reset the address-wide spraying counter."""
    settings = Settings(
        login_max_attempts=5,
        login_max_attempts_per_ip=2,
        login_window_seconds=900,
        login_lockout_seconds=900,
        _env_file=None,
    )
    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    client_ip = "203.0.113.7"
    for email in ("a@demo.local", "b@demo.local"):
        login_throttle.record(
            db,
            email=email,
            client_ip=client_ip,
            now=now,
            successful=False,
            settings=settings,
        )
    login_throttle.record(
        db,
        email="c@demo.local",
        client_ip=client_ip,
        now=now,
        successful=True,
        settings=settings,
    )
    db.flush()
    decision = login_throttle.evaluate(
        db,
        email="d@demo.local",
        client_ip=client_ip,
        now=now,
        settings=settings,
    )
    assert decision.allowed is False
    assert decision.reason == "too_many_ip_attempts"


def test_lockout_window_uses_wall_clock_not_the_frozen_demo_clock(client, db):
    """Throttling must never run on the rehearsal clock.

    The demo clock is a fixed instant. Stamping attempts with it put every
    failure permanently inside the counting window and pinned
    ``unlock_at - now`` at the full lockout, so five wrong passwords locked an
    account for ever while still promising "try again in 15 minutes" — the
    sign-in screen then looked broken with no way out.
    """
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "scrutiny@demo.local", "password": "wrong"},
        ).status_code
        == 401
    )

    stamps = [
        row.attempted_at.replace(tzinfo=UTC)
        if row.attempted_at.tzinfo is None
        else row.attempted_at
        for row in db.query(LoginAttempt).all()
    ]
    assert stamps, "the failed sign-in was not recorded"
    age_seconds = (datetime.now(UTC) - max(stamps)).total_seconds()
    # The frozen demo clock sits days in the past relative to real time.
    assert 0 <= age_seconds < 60, f"attempt stamped {age_seconds:.0f}s from now"

    # And the block has to say how long the wait really is.
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": "scrutiny@demo.local", "password": "wrong"},
        )
    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "scrutiny@demo.local", "password": "DemoPassw0rd!"},
    )
    assert blocked.status_code == 429
    assert "Try again in" in blocked.json()["detail"]


def test_login_attempts_and_audit_are_persisted(client, db):
    client.post(
        "/api/v1/auth/login",
        json={"email": "scrutiny@demo.local", "password": "wrong"},
    )
    assert db.query(LoginAttempt).count() == 2
    actions = [
        event.action
        for event in db.query(AuditEvent).order_by(AuditEvent.seq).all()
        if event.action == "auth.login"
    ]
    assert actions


def test_upload_rejects_content_type_mismatch(client, as_user):
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={"file": ("lease.pdf", b"not really a pdf", "application/pdf")},
    )
    assert response.status_code == 415
    assert "signature" in response.json()["detail"]


def test_upload_sanitises_path_traversal_filenames(client, as_user, db):
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={
            "file": (
                "../../outside.pdf",
                b"%PDF-1.4 demo bytes",
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201
    document = db.get(Document, response.json()["document"]["id"])
    assert document is not None
    assert document.file_name == "outside.pdf"
    assert ".." not in document.storage_ref
    assert document.content_type == "application/pdf"


def test_password_change_invalidates_existing_tokens(client, as_user):
    headers = as_user("institution@demo.local")
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "DemoPassw0rd!",
            "new_password": "NewDemoPassw0rd!",
        },
    )
    assert response.status_code == 200

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "institution@demo.local", "password": "NewDemoPassw0rd!"},
    )
    assert login.status_code == 200
    issued = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=issued).status_code == 200

    # The fixed clock gives both changes the same timestamp; the marker must still
    # change so the token issued by the first change cannot survive the second.
    second = client.post(
        "/api/v1/auth/change-password",
        headers=issued,
        json={
            "current_password": "NewDemoPassw0rd!",
            "new_password": "AnotherDemoPassw0rd!",
        },
    )
    assert second.status_code == 200
    assert client.get("/api/v1/auth/me", headers=issued).status_code == 401


def test_password_change_enforces_policy(client, as_user):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=as_user("institution@demo.local"),
        json={"current_password": "DemoPassw0rd!", "new_password": "short"},
    )
    assert response.status_code == 422


def test_list_endpoints_are_bounded_and_report_totals(client, as_user):
    headers = as_user("admin@demo.local")
    response = client.get("/api/v1/applications?limit=1", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert int(response.headers["X-Total-Count"]) >= 4

    institutions = client.get("/api/v1/institutions?limit=1", headers=headers)
    assert len(institutions.json()) == 1
    assert int(institutions.headers["X-Total-Count"]) >= 1


def test_production_configuration_rejects_unsafe_defaults():
    with pytest.raises(ValidationError) as excinfo:
        Settings(env="production", _env_file=None)
    message = str(excinfo.value)
    assert "unsafe production configuration" in message
    assert "SIH_JWT_SECRET" in message


def test_valid_production_configuration_is_accepted():
    settings = Settings(
        env="production",
        jwt_secret="a" * 64,
        database_url="postgresql+psycopg://app_rw:pass@db:5432/sih26262",
        simulation_readonly_url=(
            "postgresql+psycopg://sim_prod_ro:pass@db:5432/sih26262"
        ),
        simulation_results_url=(
            "postgresql+psycopg://sim_results_rw:pass@db:5432/sih26262"
        ),
        simulation_schema="sim",
        cors_origins=("https://aicte.example.gov.in",),
        allowed_hosts=("api.aicte.example.gov.in",),
        password_hash_iterations=260_000,
        hsts_seconds=31_536_000,
        clock_mode="system",
        metrics_token="m" * 32,
        malware_scan_enabled=True,
        _env_file=None,
    )
    assert settings.is_production


def test_production_configuration_requires_isolated_simulation_roles():
    base = {
        "env": "production",
        "jwt_secret": "a" * 64,
        "database_url": "postgresql+psycopg://app_rw:pass@db:5432/sih26262",
        "cors_origins": ("https://aicte.example.gov.in",),
        "allowed_hosts": ("api.aicte.example.gov.in",),
        "password_hash_iterations": 260_000,
        "hsts_seconds": 31_536_000,
        "clock_mode": "system",
        "_env_file": None,
    }
    with pytest.raises(ValidationError) as missing:
        Settings(**base)
    message = str(missing.value)
    assert "SIH_SIMULATION_READONLY_URL" in message
    assert "SIH_SIMULATION_RESULTS_URL" in message
    assert "SIH_SIMULATION_SCHEMA" in message

    with pytest.raises(ValidationError) as shared:
        Settings(
            **base,
            simulation_readonly_url=(
                "postgresql+psycopg://app_rw:pass@db:5432/sih26262"
            ),
            simulation_results_url=(
                "postgresql+psycopg://sim_results_rw:pass@db:5432/sih26262"
            ),
            simulation_schema="sim",
        )
    assert "different database role" in str(shared.value)


def test_password_change_audit_is_chained(client, as_user, db):
    headers = as_user("institution@demo.local")
    client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "DemoPassw0rd!",
            "new_password": "NewDemoPassw0rd!",
        },
    )
    assert db.query(AuditEvent).filter_by(action="auth.password_changed").count() == 1
    assert db.query(User).filter_by(email="institution@demo.local").one().password_changed_at
    assert (
        db.query(User)
        .filter_by(email="institution@demo.local")
        .one()
        .password_changed_at.replace(tzinfo=UTC)
        == datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    )


def test_metrics_endpoint_exposes_request_metrics(client):
    assert client.get("/health/live").status_code == 200
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "sih_http_requests_total" in response.text
    assert "sih_app_info" in response.text


def test_metrics_endpoint_requires_token_when_configured(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    token = "metrics-token-" + "x" * 32
    settings = Settings(metrics_token=token, _env_file=None)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    app_with_token = create_app()
    with TestClient(app_with_token) as test_client:
        assert test_client.get("/metrics").status_code == 403
        assert (
            test_client.get(
                "/metrics", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )


def test_database_trigger_blocks_direct_rule_updates(db):
    version = db.query(RuleVersion).first()
    assert version is not None
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE rule_versions SET condition = :condition WHERE id = :id"
            ),
            {'condition': '{"op": "always"}', "id": version.id},
        )
        db.commit()
    db.rollback()


def test_database_trigger_allows_retirement_and_blocks_changes_after_it(db):
    version = db.query(RuleVersion).first()
    assert version is not None
    db.execute(
        text("UPDATE rule_versions SET status = 'retired' WHERE id = :id"),
        {"id": version.id},
    )
    db.commit()
    db.expire_all()
    assert db.get(RuleVersion, version.id).status == "retired"

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE rule_versions SET condition = :condition WHERE id = :id"
            ),
            {'condition': '{"op": "never"}', "id": version.id},
        )
        db.commit()
    db.rollback()


def test_database_trigger_blocks_deleting_approved_versions(db):
    version = db.query(RuleVersion).first()
    assert version is not None
    with pytest.raises(IntegrityError):
        db.execute(
            text("DELETE FROM rule_versions WHERE id = :id"), {"id": version.id}
        )
        db.commit()
    db.rollback()


class _FakeMalwareScanner:
    name = "fake"

    def scan(self, content: bytes) -> ScanResult:
        if b"EICAR-TEST" in content:
            raise MalwareDetected("EICAR-Test-File", self.name)
        return ScanResult(clean=True, engine=self.name)


@pytest.fixture
def fake_malware_scanner():
    malware_service.set_malware_scanner(_FakeMalwareScanner())
    try:
        yield
    finally:
        malware_service.reset_malware_scanner()


def test_clean_upload_reports_the_scanner(client, as_user, fake_malware_scanner):
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={"file": ("lease.pdf", b"%PDF-1.4 clean demo", "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["malware_scan"] == {
        "engine": "fake",
        "clean": True,
        "note": "File passed the configured malware scanner.",
    }


def test_malware_detection_rejects_upload_and_audits_it(
    client, as_user, db, fake_malware_scanner
):
    response = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=as_user("institution@demo.local"),
        data={"doc_type": "lease_deed"},
        files={
            "file": ("lease.pdf", b"%PDF-1.4 EICAR-TEST", "application/pdf")
        },
    )
    assert response.status_code == 422
    assert "malware" in response.json()["detail"]
    assert db.query(Document).filter_by(application_id="app-draft-0004").count() == 0
    rejected = (
        db.query(AuditEvent)
        .filter_by(action="document.upload_rejected")
        .order_by(AuditEvent.seq.desc())
        .first()
    )
    assert rejected is not None
    assert rejected.outcome == "rejected"


class _UnavailableScanner:
    name = "unavailable"

    def scan(self, content: bytes) -> ScanResult:
        raise MalwareScannerError("daemon down")


def test_scanner_failure_rejects_upload_without_storing(
    client, as_user, db
):
    malware_service.set_malware_scanner(_UnavailableScanner())
    try:
        response = client.post(
            "/api/v1/applications/app-draft-0004/documents",
            headers=as_user("institution@demo.local"),
            data={"doc_type": "lease_deed"},
            files={"file": ("lease.pdf", b"%PDF-1.4 clean demo", "application/pdf")},
        )
    finally:
        malware_service.reset_malware_scanner()
    assert response.status_code == 503
    assert db.query(Document).filter_by(application_id="app-draft-0004").count() == 0


def test_retention_plan_and_apply_remove_only_eligible_rows(db):
    settings = Settings(
        retention_login_attempt_days=30,
        retention_alert_delivery_days=180,
        _env_file=None,
    )
    now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    old_attempt = LoginAttempt(
        key_hash="old",
        attempted_at=now - timedelta(days=31),
        successful=False,
    )
    fresh_attempt = LoginAttempt(
        key_hash="fresh",
        attempted_at=now - timedelta(days=1),
        successful=False,
    )
    alert = Alert(
        entity_type="application",
        entity_id="app-main-0001",
        alert_type="test",
        level="info",
        cycle_key="test",
        dedupe_key="retention-test-dedupe",
        due_at=now,
        fired_at=now,
        status="open",
        recipients=[],
        payload={},
    )
    db.add_all([old_attempt, fresh_attempt, alert])
    db.flush()
    old_delivery = AlertDelivery(
        alert_id=alert.id,
        channel="in_app",
        attempt=1,
        status="delivered",
        attempted_at=now - timedelta(days=181),
    )
    fresh_delivery = AlertDelivery(
        alert_id=alert.id,
        channel="in_app",
        attempt=2,
        status="delivered",
        attempted_at=now - timedelta(days=1),
    )
    db.add_all([old_delivery, fresh_delivery])
    db.commit()

    plan = plan_retention(db, now=now, settings=settings)
    assert plan.login_attempts_eligible == 1
    assert plan.alert_deliveries_eligible == 1

    result = apply_retention(db, now=now, settings=settings)
    assert result["login_attempts_deleted"] == 1
    assert result["alert_deliveries_deleted"] == 1
    assert db.query(LoginAttempt).filter_by(key_hash="old").count() == 0
    assert db.query(LoginAttempt).filter_by(key_hash="fresh").count() == 1
    assert db.query(AlertDelivery).filter_by(id=old_delivery.id).count() == 0
    assert db.query(AlertDelivery).filter_by(id=fresh_delivery.id).count() == 1
