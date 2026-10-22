"""Application configuration.

Everything security-, storage- and clock-related is configuration so the demo can
run deterministically (fixed clock) without touching business logic.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SIH_", extra="ignore"
    )

    app_name: str = "SIH26262 — AICTE Approval & Compliance Platform"
    env: str = "dev"
    api_prefix: str = "/api/v1"

    # Production/operational database (PostgreSQL in deployment, SQLite for dev).
    database_url: str = "sqlite:///./sih26262.db"
    # Simulation storage. In deployment these point at the least-privilege roles
    # documented in docs/REHEARSAL_ENGINE.md (`sim_prod_ro` / `sim_results_rw`).
    simulation_readonly_url: str | None = None
    simulation_results_url: str | None = None
    # PostgreSQL only: keep simulation rows in their own schema so the results
    # role never has USAGE on the operational schema. Leave unset for SQLite.
    simulation_schema: str | None = None

    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    password_hash_iterations: int = 260_000

    # system | fixed | offset — the rehearsal/demo clock is injectable, never ambient.
    clock_mode: str = "system"
    clock_fixed_at: str | None = None
    clock_offset_days: float = 0.0
    display_timezone: str = "Asia/Kolkata"
    business_timezone: str = "Asia/Kolkata"

    storage_dir: str = "./storage"
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_upload_types: tuple[str, ...] = (
        "application/pdf",
        "image/png",
        "image/jpeg",
    )

    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    seed_on_startup: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
