"""FR-01 stubbed portal feed: the FR-01 field set, with an "as of" stamp.

Read-only (nothing is written or decided here) and scope-filtered like the
applications list: an institution sees only its own cases, a Regional
officer their region. The feed is explicitly labelled ``source: "stub"``
and stamped with the clock's instant, so nothing built against it can
mistake it for live portal data (PRD line 341: live integration is
Release 1). Ingestion — "receiving" feed records into cases — is
deliberately not implemented: it needs a portal service identity, which is
a human approval gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ
from ..schemas.api import PortalFeedOut
from ..services import portal_feed
from ..services.authorization_service import EffectiveAccess
from .deps import require_any

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/feed", response_model=PortalFeedOut)
def get_portal_feed(
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """The stubbed FR-01 feed of final-submitted applications in scope.

    ``as_of`` is the moment the feed was produced (the injectable clock):
    consumers must treat it as valid as of that instant and no later — the
    §18 "not real time" contract, made explicit in the payload.
    """
    return portal_feed.build_feed(db, access)
