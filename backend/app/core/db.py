"""Database engines and sessions.

Three access paths exist on purpose:

* ``SessionLocal``      — operational writes, authorised services only.
* ``open_readonly_session`` — the rehearsal baseline reader. The session is set
  read-only at the connection level, so a stray write raises instead of relying
  on developer discipline.
* ``SimResultsWriter``  — the only writer for simulation tables. It type-checks
  what it is given so a production model cannot be flushed to simulation storage.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _build_engine(url: str) -> Engine:
    engine = create_engine(url, future=True, connect_args=_connect_args(url))

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


_settings = get_settings()
engine: Engine = _build_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_results_url = _settings.simulation_results_url or _settings.database_url
sim_engine: Engine = _build_engine(_results_url)
SimSessionLocal = sessionmaker(
    bind=sim_engine, autoflush=False, expire_on_commit=False
)

_readonly_url = _settings.simulation_readonly_url or _settings.database_url
readonly_engine: Engine = _build_engine(_readonly_url)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def open_readonly_session() -> Iterator[Session]:
    """Session that cannot write, enforced by the database, not by convention."""
    db = Session(bind=readonly_engine, autoflush=False, expire_on_commit=False)
    try:
        if readonly_engine.dialect.name == "sqlite":
            db.execute(text("PRAGMA query_only = ON"))
        else:
            db.execute(text("SET TRANSACTION READ ONLY"))
        yield db
    finally:
        db.rollback()
        db.close()


@contextmanager
def open_sim_results_session() -> Iterator["SimResultsWriter"]:
    db = SimSessionLocal()
    try:
        yield SimResultsWriter(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class SimulationWriteViolation(RuntimeError):
    pass


class SimResultsWriter:
    """Writes only simulation records. Anything else is a programming error."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def add(self, obj: object) -> None:
        from ..models.rehearsal import SimMetric, SimRuleResult, SimRun
        from ..models.rehearsal import SimInputSnapshot

        allowed = (SimRun, SimInputSnapshot, SimRuleResult, SimMetric)
        if not isinstance(obj, allowed):
            raise SimulationWriteViolation(
                f"{type(obj).__name__} is not a simulation record; "
                "simulation storage cannot write production models"
            )
        self._session.add(obj)

    def flush(self) -> None:
        self._session.flush()

    def get_run(self, run_id: str):
        from ..models.rehearsal import SimRun

        return self._session.get(SimRun, run_id)


def create_all() -> None:
    """Dev/test convenience. Deployments use Alembic."""
    from .. import models  # noqa: F401  (register metadata)

    Base.metadata.create_all(bind=engine)
