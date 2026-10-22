"""Shared FastAPI dependencies: identity, effective access, permission gates."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import PermissionDenied
from ..core.security import decode_access_token, password_marker
from ..models import Application, User
from ..services.authorization_service import (
    EffectiveAccess,
    effective_access,
    require_application,
    require_permission,
)

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "inactive or unknown user")
    expected_marker = password_marker(user.password_hash)
    if payload.get("pwd") != expected_marker:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "token is no longer valid; sign in again"
        )
    return user


def get_access(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> EffectiveAccess:
    return effective_access(db, user)


def require(permission: str) -> Callable[..., EffectiveAccess]:
    def dependency(access: EffectiveAccess = Depends(get_access)) -> EffectiveAccess:
        require_permission(access, permission)
        return access

    return dependency


def require_any(*permissions: str) -> Callable[..., EffectiveAccess]:
    """Pass if the caller holds at least one of the listed permissions.

    Institutions and officers reach the same case record through different
    permissions; the scope check still decides which records they can reach.
    """

    def dependency(access: EffectiveAccess = Depends(get_access)) -> EffectiveAccess:
        if not any(access.has(permission) for permission in permissions):
            raise PermissionDenied(
                f"role {access.primary_role!r} holds none of {list(permissions)!r}"
            )
        return access

    return dependency


def scoped_application(
    application_id: str,
    access: EffectiveAccess = Depends(get_access),
    db: Session = Depends(get_db),
) -> Application:
    return require_application(db, access, application_id)


def translate_permission_error(exc: PermissionDenied) -> HTTPException:
    code = 404 if exc.code == "not_found" else 403
    return HTTPException(code, exc.message)
