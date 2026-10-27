"""Institution representation and human-controlled one-time reopening flow."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.config import get_settings
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import REOPENING_REQUEST, REOPENING_REVIEW
from ..models import Application, Document, ReopeningRequest
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application, scope_filter
from ..services.workflow_service import request_transition
from .deps import require, require_any

router = APIRouter(tags=["reopening"])


class ReopeningIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=4000)
    resolution_document_id: str


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    reason: str = Field(min_length=10, max_length=4000)
    public_notice_document_id: str | None = None


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_document_id: str


class PaymentReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verified: bool
    reason: str = Field(min_length=10, max_length=4000)


def _audit(db: Session, action: str, item: ReopeningRequest, access: EffectiveAccess,
           outcome: str, reason: str = "", document_id: str | None = None) -> None:
    AuditService(db).append(
        action=action,
        entity_type="application",
        entity_id=item.application_id,
        outcome=outcome,
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason,
        after={"reopening_id": item.id, "status": item.status, "document_id": document_id},
        request_id=current_request_id(),
    )


def _case(db: Session, access: EffectiveAccess, application_id: str) -> Application:
    application = db.scalar(
        select(Application).where(Application.id == application_id, scope_filter(access))
    )
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found in scope")
    return application


def _view(item: ReopeningRequest) -> dict:
    return {
        "id": item.id,
        "application_id": item.application_id,
        "status": item.status,
        "reason": item.reason,
        "requested_at": iso(item.requested_at),
        "review_reason": item.review_reason,
        "representation_document_id": item.representation_document_id,
        "public_notice_document_id": item.public_notice_document_id,
        "payment_evidence_document_id": item.payment_evidence_document_id,
        "filing_window_confirmed": item.filing_window_confirmed_at is not None,
        "payment_verified": item.payment_verified_at is not None,
        "resumed_at": iso(item.resumed_at),
    }


@router.post("/applications/{application_id}/reopening", status_code=201)
def request_reopening(
    application_id: str,
    payload: ReopeningIn,
    access: EffectiveAccess = Depends(require(REOPENING_REQUEST)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    resolution = db.get(Document, payload.resolution_document_id)
    if application.current_state != "submitted" or resolution is None or resolution.application_id != application.id or resolution.doc_type != "reopening_resolution":
        item = ReopeningRequest(application_id=application.id, institution_actor_id=access.user_id,
                                representation_document_id=payload.resolution_document_id or "invalid",
                                reason=payload.reason.strip(), status="rejected")
        _audit(db, "reopening.request_rejected", item, access, "rejected", "invalid_state_or_resolution")
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "reopening is available only while submitted; attach this case's reopening resolution")
    item = ReopeningRequest(application_id=application.id, institution_actor_id=access.user_id,
                            representation_document_id=resolution.id, reason=payload.reason.strip())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "reopening is one-time and a request already exists") from None
    _audit(db, "reopening.requested", item, access, "accepted")
    db.commit()
    db.refresh(item)
    return _view(item)


@router.get("/applications/{application_id}/reopening")
def get_reopening(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(REOPENING_REQUEST, REOPENING_REVIEW)),
    db: Session = Depends(get_db),
) -> dict:
    application = _case(db, access, application_id)
    item = db.scalar(select(ReopeningRequest).where(ReopeningRequest.application_id == application.id))
    return {"application_id": application.id, "reopening": _view(item) if item else None}


@router.get("/reopening/queue")
def reopening_queue(
    access: EffectiveAccess = Depends(require(REOPENING_REVIEW)),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(select(ReopeningRequest).where(
        ReopeningRequest.status.in_(("requested", "approved_pending_payment", "payment_submitted")),
        ReopeningRequest.application_id.in_(select(Application.id).where(scope_filter(access))),
    ).order_by(ReopeningRequest.requested_at)).all()
    return {"items": [_view(row) for row in rows]}


@router.get("/reopening/{reopening_id}/documents/{document_id}")
def download_reopening_evidence(
    reopening_id: str,
    document_id: str,
    access: EffectiveAccess = Depends(require_any(REOPENING_REVIEW, "document.read")),
    db: Session = Depends(get_db),
) -> Response:
    item = db.get(ReopeningRequest, reopening_id)
    if item is None or db.scalar(
        select(Application.id).where(Application.id == item.application_id, scope_filter(access))
    ) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reopening request not found in scope")
    if document_id not in {
        item.representation_document_id,
        item.public_notice_document_id,
        item.payment_evidence_document_id,
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document is not linked to this reopening request")
    document = db.get(Document, document_id)
    if document is None or document.application_id != item.application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reopening document not found")
    if document.storage_ref.startswith("seed://"):
        from .documents import _placeholder_pdf
        content = _placeholder_pdf(document)
    else:
        root = Path(get_settings().storage_dir).resolve()
        path = Path(document.storage_ref).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(status.HTTP_410_GONE, "reopening evidence is unavailable")
        content = path.read_bytes()
    _audit(db, "reopening.document_accessed", item, access, "accepted", document_id=document.id)
    db.commit()
    return Response(content, media_type=document.content_type, headers={
        "Content-Disposition": f'attachment; filename="{document.file_name}"',
        "X-Content-SHA256": document.file_sha256,
    })


@router.post("/reopening/{reopening_id}/review")
def review_reopening(
    reopening_id: str,
    payload: ReviewIn,
    access: EffectiveAccess = Depends(require(REOPENING_REVIEW)),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(ReopeningRequest, reopening_id)
    if item is None or db.scalar(select(Application.id).where(Application.id == item.application_id,
                                                              scope_filter(access))) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reopening request not found in scope")
    if item.status != "requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "request is no longer awaiting review")
    notice = db.get(Document, payload.public_notice_document_id) if payload.public_notice_document_id else None
    if payload.approved and (
        notice is None
        or notice.doc_type != "public_notice"
        or notice.application_id not in (None, item.application_id)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "approval requires a public-notice document supporting filing-window confirmation")
    item.reviewer_id = access.user_id
    item.review_reason = payload.reason.strip()
    item.reviewed_at = get_clock().now()
    if payload.approved:
        item.status = "approved_pending_payment"
        item.public_notice_document_id = notice.id
        item.filing_window_confirmed_at = get_clock().now()
    else:
        item.status = "denied"
    _audit(db, "reopening.reviewed", item, access, "accepted", payload.reason.strip())
    db.commit()
    return _view(item)


@router.post("/reopening/{reopening_id}/payment")
def submit_reopening_payment(
    reopening_id: str,
    payload: PaymentIn,
    access: EffectiveAccess = Depends(require(REOPENING_REQUEST)),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(ReopeningRequest, reopening_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reopening request not found")
    _case(db, access, item.application_id)
    evidence = db.get(Document, payload.evidence_document_id)
    if item.status not in ("approved_pending_payment", "payment_rejected") or evidence is None or evidence.application_id != item.application_id or evidence.doc_type != "reopening_payment_evidence":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "upload this case's TER and applicable late-penalty payment evidence after approval")
    item.payment_evidence_document_id = evidence.id
    item.status = "payment_submitted"
    _audit(db, "reopening.payment_submitted", item, access, "accepted")
    db.commit()
    return _view(item)


@router.post("/reopening/{reopening_id}/payment-review")
def review_reopening_payment(
    reopening_id: str,
    payload: PaymentReviewIn,
    access: EffectiveAccess = Depends(require(REOPENING_REVIEW)),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(ReopeningRequest, reopening_id)
    if item is None or db.scalar(select(Application.id).where(Application.id == item.application_id,
                                                              scope_filter(access))) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reopening request not found in scope")
    if item.status != "payment_submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "payment evidence is not awaiting review")
    if not payload.verified:
        item.status = "payment_rejected"
        item.payment_verification_note = payload.reason.strip()
        _audit(db, "reopening.payment_rejected", item, access, "rejected", payload.reason.strip())
        db.commit()
        return _view(item)
    item.payment_verified_at = get_clock().now()
    item.payment_verification_note = payload.reason.strip()
    app = _case(db, access, item.application_id)
    outcome = request_transition(db, access, app.id, "reopen_application", payload.reason.strip())
    if not outcome.accepted:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(outcome.reasons))
    item.status = "resumed"
    item.resumed_at = get_clock().now()
    item.reviewer_id = access.user_id
    _audit(db, "reopening.resumed", item, access, "accepted", payload.reason.strip())
    db.commit()
    return _view(item)
