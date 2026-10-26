from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.config import get_settings
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.http import client_ip
from ..core.security import (
    create_access_token,
    hash_password,
    password_marker,
    validate_password_strength,
    verify_password,
)
from ..models import User
from ..models.base import sha256_hex
from ..schemas.api import ChangePasswordRequest, LoginRequest, TokenResponse
from ..services import login_throttle
from ..services.audit_service import AuditService
from ..services.authorization_service import effective_access
from .deps import get_access, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# A fixed hash keeps the unknown-email path close to the known-email path so the
# response time does not reveal whether an account exists.
_DUMMY_HASH = hash_password("dummy-password-not-used-by-any-account")


def _origin_of(request: Request) -> str | None:
    """The origin this request came from, if the caller named one.

    Browsers attach `Origin` to every POST they send (and `Referer` when
    `Origin` is absent). Command-line clients — curl, wget, an API explorer's
    "Execute" button — send neither unless they deliberately copy one.
    """
    origin = request.headers.get("origin", "").strip()
    if origin:
        # "null" is an opaque origin (file:// pages, some privacy modes): it
        # names no site we serve.
        return None if origin.lower() == "null" else origin.rstrip("/")
    referer = request.headers.get("referer", "").strip()
    parts = urlsplit(referer)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return None


def _sign_in_comes_from_the_screen(request: Request, settings) -> bool:
    """True only when the sign-in screen could have made this request.

    Sign-in is a UI-only action. The accepted callers are the deployed
    front-end origins (`SIH_CORS_ORIGINS`) and the API's own host, which is
    what a deployment serving the UI and the API from one host looks like.

    This is a channel rule, not a security boundary: an HTTP client can copy
    an `Origin` header, and nothing on a server can tell a browser apart from
    a script that mimics one. What actually protects an account is unchanged
    here — the password check, the persisted throttling, the short-lived
    signed token. This rule removes the second sign-in door (curl, the API
    explorer) so there is one sign-in screen, and nothing else.
    """
    origin = _origin_of(request)
    if not origin:
        return False
    if origin in {candidate.rstrip("/") for candidate in settings.cors_origins}:
        return True
    # Same-host deployment: compare hosts only, so the scheme a proxy adds in
    # front does not decide whether a real person can sign in.
    host = request.headers.get("host", "").strip()
    return bool(host) and urlsplit(origin).netloc == host


def _lockout_message(retry_after_seconds: int) -> str:
    """Say how long the wait actually is — "try again later" is not an answer."""
    minutes = -(-retry_after_seconds // 60)  # round up
    if minutes < 1:
        return "Too many failed sign-in attempts. Try again in a few seconds."
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-in attempts. Try again in {minutes} {unit}."


def _audit_login(
    db: Session,
    *,
    email: str,
    user: User | None,
    outcome: str,
    reason: str,
) -> None:
    AuditService(db).append(
        action="auth.login",
        entity_type="user",
        entity_id=user.id if user is not None else sha256_hex(email)[:36],
        outcome=outcome,
        actor_id=user.id if user is not None else None,
        reason=reason,
        request_id=current_request_id(),
    )


def _reject_login(
    db: Session,
    *,
    email: str,
    user: User | None,
    client: str,
    reason: str,
) -> None:
    settings = get_settings()
    login_throttle.record(
        db,
        email=email,
        client_ip=client,
        now=login_throttle.wall_now(),
        successful=False,
        settings=settings,
    )
    _audit_login(db, email=email, user=user, outcome="rejected", reason=reason)
    db.commit()


def _user_payload(user: User, access) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": access.roles,
        "permissions": sorted(access.permissions),
        "scope": {
            "global": access.global_scope,
            "regions": sorted(access.regions),
            "institutions": sorted(access.institutions),
            "committees": sorted(access.committees),
            "assigned_cases_only": access.assigned_cases_only,
        },
    }


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    settings = get_settings()
    # Before anything is read or written: a request that did not come from the
    # sign-in screen is refused without touching the throttle table (so it can
    # never lock a real person out of their account) and without writing an
    # audit row (so an unauthenticated caller cannot use us as a free write
    # path). The access log still records every one of these.
    if not _sign_in_comes_from_the_screen(request, settings):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign-in is only available from the application's sign-in screen.",
        )
    email = payload.email.strip().lower()
    client = client_ip(request.scope, settings)
    # Wall-clock time: see login_throttle.wall_now(). The demo clock freezes
    # the case timeline and must not freeze the lockout window with it.
    now = login_throttle.wall_now()

    decision = login_throttle.evaluate(
        db, email=email, client_ip=client, now=now, settings=settings
    )
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            _lockout_message(decision.retry_after_seconds),
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        _reject_login(
            db,
            email=email,
            user=None,
            client=client,
            reason="invalid_credentials",
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(payload.password, user.password_hash):
        _reject_login(
            db,
            email=email,
            user=user,
            client=client,
            reason="invalid_credentials",
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        # Same response as a bad password: a disabled account is not a user
        # enumeration oracle.
        _reject_login(
            db,
            email=email,
            user=user,
            client=client,
            reason="account_disabled",
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_throttle.record(
        db,
        email=email,
        client_ip=client,
        now=now,
        successful=True,
        settings=settings,
    )
    _audit_login(db, email=email, user=user, outcome="accepted", reason="")
    db.commit()

    return TokenResponse(
        access_token=create_access_token(
            user.id, extra={"pwd": password_marker(user.password_hash)}
        ),
        user=_user_payload(user, effective_access(db, user)),
    )


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
    access=Depends(get_access),
) -> dict:
    return _user_payload(user, access)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    access=Depends(get_access),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "current password is incorrect"
        )
    try:
        validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "new password must differ from the current password",
        )

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = get_clock().now()
    AuditService(db).append(
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        request_id=current_request_id(),
    )
    db.commit()
    return {
        "status": "changed",
        "note": "All previously issued tokens are now invalid; sign in again.",
    }
