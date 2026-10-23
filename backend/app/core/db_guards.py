"""Database-level guards for records that must not be rewritten.

The ORM guard in ``models.rules`` protects normal application writes. This module
adds the same invariant inside SQLite and PostgreSQL so a direct SQL update cannot
bypass the service layer. PostgreSQL deployments install the trigger from Alembic;
SQLite development/test databases install it when the table is created.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

_SQLITE_IMMUTABLE_FIELDS = (
    "rule_id",
    "version",
    "applicability",
    "condition",
    "missing_outcome",
    "unverified_outcome",
    "failure_outcome",
    "blocking",
    "severity",
    "effective_from",
    "effective_to",
    "content_hash",
    "notes",
)

_POSTGRES_IMMUTABLE_FIELDS = _SQLITE_IMMUTABLE_FIELDS


def _sqlite_changed_clause() -> str:
    return "\n      OR ".join(
        f"NEW.{field} IS NOT OLD.{field}" for field in _SQLITE_IMMUTABLE_FIELDS
    )


SQLITE_UPDATE_TRIGGER = f"""
CREATE TRIGGER IF NOT EXISTS rule_versions_immutable_update
BEFORE UPDATE ON rule_versions
WHEN OLD.status IN ('approved', 'retired')
BEGIN
  SELECT CASE
    WHEN OLD.status = 'retired' AND NEW.status <> 'retired'
      THEN RAISE(ABORT, 'retired rule versions cannot change status')
    WHEN OLD.status = 'approved' AND NEW.status NOT IN ('approved', 'retired')
      THEN RAISE(ABORT, 'approved rule versions may only be retired')
    WHEN {_sqlite_changed_clause()}
      THEN RAISE(ABORT, 'approved or retired rule versions are immutable; draft a new version')
  END;
END;
"""

SQLITE_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS rule_versions_immutable_delete
BEFORE DELETE ON rule_versions
WHEN OLD.status IN ('approved', 'retired')
BEGIN
  SELECT RAISE(ABORT, 'approved or retired rule versions cannot be deleted');
END;
"""


def _postgres_changed_clause() -> str:
    return "\n       OR ".join(
        f"NEW.{field}::text IS DISTINCT FROM OLD.{field}::text"
        for field in _POSTGRES_IMMUTABLE_FIELDS
    )


POSTGRES_FUNCTION = f"""
CREATE OR REPLACE FUNCTION enforce_rule_version_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('approved', 'retired') THEN
      RAISE EXCEPTION 'approved or retired rule versions cannot be deleted'
        USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
  END IF;

  IF OLD.status IN ('approved', 'retired') THEN
    IF OLD.status = 'retired' AND NEW.status <> 'retired' THEN
      RAISE EXCEPTION 'retired rule versions cannot change status'
        USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'approved' AND NEW.status NOT IN ('approved', 'retired') THEN
      RAISE EXCEPTION 'approved rule versions may only be retired'
        USING ERRCODE = '23514';
    END IF;
    IF {_postgres_changed_clause()}
    THEN
      RAISE EXCEPTION 'approved or retired rule versions are immutable; draft a new version'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
"""

POSTGRES_TRIGGER = """
DROP TRIGGER IF EXISTS rule_versions_immutability ON rule_versions;
CREATE TRIGGER rule_versions_immutability
BEFORE UPDATE OR DELETE ON rule_versions
FOR EACH ROW EXECUTE FUNCTION enforce_rule_version_immutability();
"""


def install_sqlite_rule_version_guard(connection: Connection) -> None:
    connection.exec_driver_sql(SQLITE_UPDATE_TRIGGER)
    connection.exec_driver_sql(SQLITE_DELETE_TRIGGER)


def install_postgres_rule_version_guard(connection: Connection) -> None:
    connection.exec_driver_sql(POSTGRES_FUNCTION)
    connection.exec_driver_sql(POSTGRES_TRIGGER)


def install_rule_version_guard(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        install_sqlite_rule_version_guard(connection)
    elif connection.dialect.name == "postgresql":
        install_postgres_rule_version_guard(connection)
