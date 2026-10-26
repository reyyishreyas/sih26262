"""Demo clock control endpoints (Phase 3.8, PRD "Demo extras").

Advance / reset the injectable clock so the demo can show reminders and
escalation without waiting for real days. Gated by ``ADMIN_USERS``: moving
time re-ages every case and fires every reminder, so only an administrator may
do it. Refuses outright in production (the service guards this too, but the
endpoint says so plainly) and refuses on a deployment whose clock is not
injectable, so a "demo clock" can never look like it works when it does not.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import ADMIN_USERS
from ..services import demo_clock
from ..services.authorization_service import EffectiveAccess
from .deps import require

router = APIRouter(prefix="/admin/demo-clock", tags=["admin"])


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: float


class SetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moment: str


@router.get("")
def clock_status(access: EffectiveAccess = Depends(require(ADMIN_USERS))) -> dict:
    """Read-only view of the demo clock for the panel (hides itself in prod)."""
    return demo_clock.status_view()


@router.post("/advance")
def advance_clock(
    payload: AdvanceRequest,
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Move the demo clock forward by ``days`` (fractional days allowed)."""
    return demo_clock.advance(
        db, access, payload.days, request_id=current_request_id()
    )


@router.post("/set")
def set_clock(
    payload: SetRequest,
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Move the demo clock to an explicit instant (ISO-8601)."""
    return demo_clock.set_to(
        db, access, payload.moment, request_id=current_request_id()
    )


@router.post("/reset")
def reset_clock(
    access: EffectiveAccess = Depends(require(ADMIN_USERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Return the demo clock to the configured fixed instant."""
    return demo_clock.reset(db, access, request_id=current_request_id())
