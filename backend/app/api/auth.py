from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import create_access_token, verify_password
from ..models import User
from ..schemas.api import LoginRequest, TokenResponse
from ..services.authorization_service import effective_access
from .deps import get_access, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")
    access = effective_access(db, user)
    return TokenResponse(
        access_token=create_access_token(user.id),
        user={
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
        },
    )


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
    access=Depends(get_access),
) -> dict:
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
