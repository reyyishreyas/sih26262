from __future__ import annotations

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
        now=get_clock().now(),
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
    now = get_clock().now()
    email = payload.email.strip().lower()
    client = client_ip(request.scope, settings)

    decision = login_throttle.evaluate(
        db, email=email, client_ip=client, now=now, settings=settings
    )
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many failed sign-in attempts; try again later",
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
