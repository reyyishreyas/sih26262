"""Test harness.

The environment is configured *before* the app modules are imported, because the
engine, the clock and the settings cache are created at import time.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sih26262-tests-"))
os.environ.setdefault("SIH_DATABASE_URL", f"sqlite:///{TMP / 'test.db'}")
os.environ.setdefault("SIH_CLOCK_MODE", "fixed")
os.environ.setdefault("SIH_CLOCK_FIXED_AT", "2026-10-22T09:00:00+00:00")
os.environ.setdefault("SIH_STORAGE_DIR", str(TMP / "storage"))
os.environ.setdefault("SIH_NOTIFICATION_LOG", str(TMP / "notifications.log"))
os.environ.setdefault("SIH_JWT_SECRET", "test-secret")
os.environ.setdefault("SIH_PASSWORD_HASH_ITERATIONS", "1000")
os.environ.setdefault("SIH_ENV", "test")
# The API explorer is a second sign-in door; the suite proves it stays shut.
os.environ.setdefault("SIH_DOCS_ENABLED", "false")
# SQLite has no schemas; never inherit a PostgreSQL simulation schema here.
os.environ.pop("SIH_SIMULATION_SCHEMA", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.clock import FixedClock, set_clock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token, password_marker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.services.seed import seed  # noqa: E402

DEMO_NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)

# The front-end origin sign-in accepts — whatever the settings say it is.
UI_ORIGIN = get_settings().cors_origins[0]

USER_EMAILS = {
    "admin": "admin@demo.local",
    "scrutiny": "scrutiny@demo.local",
    "regional": "regional@demo.local",
    "evc": "evc@demo.local",
    "supervisor": "supervisor@demo.local",
    "institution": "institution@demo.local",
}


@pytest.fixture(autouse=True)
def clock():
    fixed = FixedClock(DEMO_NOW)
    set_clock(fixed)
    yield fixed
    set_clock(None)


@pytest.fixture(autouse=True)
def database(clock):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(database):
    # `POST /auth/login` only accepts the sign-in screen's origin, so the test
    # client stands in for the browser. Tests that need a client without that
    # origin (proving a plain HTTP client is refused) build their own.
    with TestClient(app, headers={"Origin": UI_ORIGIN}) as test_client:
        yield test_client


def _token(email: str) -> str:
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(email=email).one()
        return create_access_token(
            user.id, extra={"pwd": password_marker(user.password_hash)}
        )
    finally:
        session.close()


def auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(email)}"}


@pytest.fixture
def as_user():
    return auth


@pytest.fixture
def access_for(db):
    from app.services.authorization_service import effective_access

    def _access(email: str):
        user = db.query(User).filter_by(email=email).one()
        return effective_access(db, user)

    return _access
