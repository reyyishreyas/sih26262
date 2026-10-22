"""Password hashing and JWT handling.

PBKDF2-SHA256 from the standard library: no native build step, no bcrypt-version
surprises, and a format we control. Tokens are short-lived bearer tokens with an
issuer/audience and are invalidated when the account password changes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from .config import get_settings

_ALGORITHM = "pbkdf2_sha256"
_MIN_ITERATIONS = 1_000
_MAX_ITERATIONS = 1_000_000
_PASSWORD_MIN_LENGTH = 12
_PASSWORD_MAX_LENGTH = 128


def hash_password(password: str) -> str:
    iterations = get_settings().password_hash_iterations
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        iteration_count = int(iterations)
        if algorithm != _ALGORITHM:
            return False
        # A corrupted row must not be able to pin a CPU with a huge iteration
        # count (or accept a trivially weak one).
        if not _MIN_ITERATIONS <= iteration_count <= _MAX_ITERATIONS:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iteration_count)
    return hmac.compare_digest(digest, expected)


def validate_password_strength(password: str) -> None:
    """Raise ``ValueError`` with a user-safe reason when the policy is not met."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"password must be at least {_PASSWORD_MIN_LENGTH} characters"
        )
    if len(password) > _PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"password must be at most {_PASSWORD_MAX_LENGTH} characters"
        )
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("password must contain at least one letter")
    if not re.search(r"\d", password):
        raise ValueError("password must contain at least one digit")


def password_marker(password_hash: str) -> str:
    """Return a token marker bound to the current password hash.

    The stored hash changes on every password change (new salt), so a marker
    derived from it revokes old tokens even when two changes happen in the same
    clock tick. It does not expose the hash: only a truncated digest is embedded in
    the signed token.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:32]


def create_access_token(subject: str, extra: dict | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
                "require_iss": True,
                "require_aud": True,
                "leeway": settings.jwt_leeway_seconds,
            },
        )
    except JWTError:
        return None
    return payload
