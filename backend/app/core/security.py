"""Password hashing and JWT handling.

PBKDF2-SHA256 from the standard library: no native build step, no bcrypt-version
surprises, and a format we control.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from .config import get_settings


_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    iterations = get_settings().password_hash_iterations
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(subject: str, extra: dict | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None
    return payload.get("sub")
