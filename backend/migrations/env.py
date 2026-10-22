"""Alembic environment.

The URL always comes from the application settings (``SIH_DATABASE_URL``), never
from ``alembic.ini``, so migrations and the app can never drift apart.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402,F401  (register metadata)
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostgreSQL deployments keep simulation records in a dedicated schema (see
# docs/REHEARSAL_ENGINE.md). Autogenerate must reflect that schema, otherwise it
# treats every `sim.*` table in the metadata as missing and `alembic check` fails
# even though the migration applied cleanly.
SIM_SCHEMA = os.environ.get("SIH_SIMULATION_SCHEMA") or get_settings().simulation_schema
INCLUDE_SCHEMAS = bool(SIM_SCHEMA)


def include_name(name: str | None, type_: str, _parent_names: dict) -> bool:
    """Limit schema reflection to the operational schema and ``sim``.

    Without this, ``include_schemas=True`` makes Alembic reflect PostgreSQL
    catalog schemas (``pg_catalog``, ``information_schema``) and compare them with
    the application metadata.
    """
    if type_ == "schema":
        return name in (None, SIM_SCHEMA)
    return True


def get_url() -> str:
    return os.environ.get("SIH_DATABASE_URL", get_settings().database_url)


def _configure_kwargs(connection=None) -> dict:
    kwargs: dict = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "render_as_batch": True,
        "include_schemas": INCLUDE_SCHEMAS,
        "include_name": include_name,
    }
    if connection is not None:
        kwargs["connection"] = connection
    return kwargs


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        literal_binds=True,
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(**_configure_kwargs(connection))
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
