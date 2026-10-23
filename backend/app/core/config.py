"""Application configuration.

Everything security-, storage- and clock-related is configuration so the demo can
run deterministically (fixed clock) without touching business logic. Production
settings are validated at startup: an unsafe deployment fails fast instead of
quietly running with development defaults.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

_PRODUCTION_ENVS = {"prod", "production"}
_INSECURE_SECRETS = {
    "",
    "dev-only-change-me",
    "docker-dev-only-change-me",
    "ci-only-secret",
    "test-secret",
    "change-me",
    "changeme",
    "secret",
}
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SIH_", extra="ignore"
    )

    app_name: str = "SIH26262 — AICTE Approval & Compliance Platform"
    app_version: str = "1.0.0"
    env: str = "dev"
    api_prefix: str = "/api/v1"
    debug: bool = False
    docs_enabled: bool = True

    # Production/operational database (PostgreSQL in deployment, SQLite for dev).
    database_url: str = "sqlite:///./sih26262.db"
    # Simulation storage. In deployment these point at the least-privilege roles
    # documented in docs/REHEARSAL_ENGINE.md (`sim_prod_ro` / `sim_results_rw`).
    simulation_readonly_url: str | None = None
    simulation_results_url: str | None = None
    # PostgreSQL only: keep simulation rows in their own schema so the results
    # role never has USAGE on the operational schema. Leave unset for SQLite.
    simulation_schema: str | None = None

    # Connection pool. Ignored for SQLite, which uses its own single-writer model.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    db_connect_timeout_seconds: int = 5
    db_statement_timeout_ms: int = 30_000

    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "sih26262"
    jwt_audience: str = "sih26262-api"
    jwt_leeway_seconds: int = 30
    access_token_minutes: int = 480
    password_hash_iterations: int = 260_000

    # Failed sign-in throttling. State is persisted in the operational database so
    # it works across API replicas and restarts.
    login_max_attempts: int = 5
    login_max_attempts_per_ip: int = 25
    login_window_seconds: int = 900
    login_lockout_seconds: int = 900

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
    cors_allow_credentials: bool = False
    allowed_hosts: tuple[str, ...] = ("*",)
    # Set when TLS terminates in front of the API. Browsers ignore HSTS on plain
    # HTTP, so it is safe to leave enabled and only emitted in production.
    hsts_seconds: int = 31_536_000
    trust_proxy_headers: bool = False

    log_level: str = "INFO"
    log_json: bool = True
    seed_on_startup: bool = False

    # Prometheus scrape endpoint. The token is optional in development and
    # mandatory in production when the endpoint is enabled.
    metrics_enabled: bool = True
    metrics_token: str | None = None

    # Optional upload malware scanning. Production validation requires this to be
    # enabled; development and tests can leave it off.
    malware_scan_enabled: bool = False
    malware_scanner: str = "clamav"
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 5.0

    # Bounded retention for transient operational rows. Audit events are retained
    # indefinitely because deleting a middle event would break the hash chain.
    retention_login_attempt_days: int = 30
    retention_alert_delivery_days: int = 180

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in _PRODUCTION_ENVS

    @model_validator(mode="after")
    def _validate_security_settings(self) -> Settings:
        if self.jwt_algorithm not in _ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"jwt_algorithm must be one of {sorted(_ALLOWED_JWT_ALGORITHMS)}"
            )
        if not 5 <= self.access_token_minutes <= 1440:
            raise ValueError("access_token_minutes must be between 5 and 1440")
        if self.password_hash_iterations < 1_000:
            raise ValueError("password_hash_iterations must be at least 1000")
        if self.max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")
        if self.login_max_attempts < 1 or self.login_max_attempts_per_ip < 1:
            raise ValueError("login attempt limits must be positive")
        if self.login_window_seconds < 1 or self.login_lockout_seconds < 1:
            raise ValueError("login window and lockout must be positive")
        if not 1 <= self.clamav_port <= 65_535:
            raise ValueError("clamav_port must be a valid TCP port")
        if self.clamav_timeout_seconds <= 0:
            raise ValueError("clamav_timeout_seconds must be positive")
        if self.retention_login_attempt_days < 1:
            raise ValueError("retention_login_attempt_days must be positive")
        if self.retention_alert_delivery_days < 1:
            raise ValueError("retention_alert_delivery_days must be positive")
        if self.metrics_token is not None and len(self.metrics_token) < 16:
            raise ValueError("metrics_token must be at least 16 characters when set")

        if not self.is_production:
            return self

        problems: list[str] = []
        if (
            len(self.jwt_secret) < 32
            or self.jwt_secret in _INSECURE_SECRETS
            or self.jwt_secret.startswith("dev-")
        ):
            problems.append(
                "SIH_JWT_SECRET must be a random secret of at least 32 characters"
            )
        if not self.database_url.startswith("postgresql"):
            problems.append("SIH_DATABASE_URL must point at PostgreSQL in production")
        if not self.simulation_readonly_url:
            problems.append(
                "SIH_SIMULATION_READONLY_URL must be set in production"
            )
        if not self.simulation_results_url:
            problems.append("SIH_SIMULATION_RESULTS_URL must be set in production")
        if not self.simulation_schema:
            problems.append("SIH_SIMULATION_SCHEMA must be set in production")
        elif (
            self.simulation_schema == "public"
            or not re.fullmatch(r"[a-z_][a-z0-9_]*", self.simulation_schema)
        ):
            problems.append(
                "SIH_SIMULATION_SCHEMA must be a dedicated lowercase schema, "
                "not public"
            )
        if (
            self.database_url.startswith("postgresql")
            and self.simulation_readonly_url
            and self.simulation_results_url
        ):
            if (
                not self.simulation_readonly_url.startswith("postgresql")
                or not self.simulation_results_url.startswith("postgresql")
            ):
                problems.append(
                    "simulation URLs must use PostgreSQL in production"
                )
            else:
                try:
                    operational = make_url(self.database_url)
                    readonly = make_url(self.simulation_readonly_url)
                    results = make_url(self.simulation_results_url)
                except Exception:
                    problems.append("database URLs could not be parsed")
                else:
                    if readonly.username == operational.username:
                        problems.append(
                            "the rehearsal baseline must use a different database "
                            "role from the API"
                        )
                    if results.username == operational.username:
                        problems.append(
                            "the rehearsal writer must use a different database "
                            "role from the API"
                        )
                    if readonly.username == results.username:
                        problems.append(
                            "the rehearsal baseline and writer must use different "
                            "database roles"
                        )
        if self.password_hash_iterations < 100_000:
            problems.append("SIH_PASSWORD_HASH_ITERATIONS must be >= 100000")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("SIH_CORS_ORIGINS must list explicit front-end origins")
        if self.cors_allow_credentials and "*" in self.cors_origins:
            problems.append(
                "credentialed CORS cannot use a wildcard origin"
            )
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            problems.append("SIH_ALLOWED_HOSTS must list explicit hostnames")
        if self.seed_on_startup:
            problems.append("SIH_SEED_ON_STARTUP must be false in production")
        if self.clock_mode != "system":
            problems.append("the injectable clock must not be fixed in production")
        if self.debug:
            problems.append("SIH_DEBUG must be false in production")
        if self.hsts_seconds < 31_536_000:
            problems.append("SIH_HSTS_SECONDS must be at least one year")
        if self.metrics_enabled and not self.metrics_token:
            problems.append(
                "SIH_METRICS_TOKEN must be set when SIH_METRICS_ENABLED=true "
                "in production"
            )
        if not self.malware_scan_enabled:
            problems.append(
                "SIH_MALWARE_SCAN_ENABLED must be true in production"
            )
        if self.malware_scanner != "clamav":
            problems.append(
                "SIH_MALWARE_SCANNER must be 'clamav' in production"
            )
        if problems:
            raise ValueError(
                "unsafe production configuration: " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
