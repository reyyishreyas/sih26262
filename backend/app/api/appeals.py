"""Institution appeals and the human SAC/Council steps (APH Chapter II)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..core.config import get_settings
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import (
    APPEAL_SUBMIT,
    COUNCIL_APPEAL_READ,
    COUNCIL_DECISION_RECORD,
    COUNCIL_MEMBER,
    SAC_APPEAL_MANAGE,
    SAC_APPEAL_READ,
    SAC_MEMBER,
)
from ..models import (
    Appeal,
    AppealEvidence,
    AppealRepresentative,
    Application,
    Document,
    Institution,
    WorkflowTransition,
)
from ..services import appeal as appeal_policy_service
from ..services.appeal import window_days
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    scope_filter,
)
from ..services.workflow_service import request_transition
from .deps import require, require_any

router = APIRouter(tags=["appeals"])


class AppealSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grounds: str = Field(min_length=10, max_length=8000)
    supporting_document_ids: list[str] = Field(min_length=1, max_length=20)


class RepresentativeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=128)
    institutional_role: str = Field(min_length=2, max_length=128)
    id_document_id: str
    authorization_attested: bool


class RepresentativesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    representatives: list[RepresentativeIn] = Field(min_length=2, max_length=2)


class HearingSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hearing_at: datetime
    venue: str | None = Field(default=None, max_length=512)
    meeting_url: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_location(self):
        if bool(self.venue and self.venue.strip()) == bool(self.meeting_url):
            raise ValueError("provide exactly one hearing venue or secure meeting URL")
        return self


class HearingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation: str = Field(min_length=10, max_length=8000)


class CouncilDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["approved", "not_approved"]
    decision: str = Field(min_length=10, max_length=8000)
    decision_document_id: str


def _representatives(db: Session, appeal_id: str) -> list[AppealRepresentative]:
    return list(
        db.scalars(
            select(AppealRepresentative)
            .where(AppealRepresentative.appeal_id == appeal_id)
            .order_by(AppealRepresentative.position)
        ).all()
    )


def _view(db: Session, appeal: Appeal, *, include_private: bool = False) -> dict:
    app = db.get(Application, appeal.application_id)
    institution = db.get(Institution, app.institution_id) if app else None
    result = {
        "id": appeal.id,
        "application_id": appeal.application_id,
        "institution": institution.name if institution else "",
        "status": appeal.status,
        "submitted_at": iso(to_utc(appeal.submitted_at)),
        "appeal_deadline": iso(to_utc(appeal.appeal_deadline)),
        "hearing_at": iso(to_utc(appeal.hearing_at)),
        "hearing_venue": appeal.hearing_venue,
        "hearing_url": appeal.hearing_url,
        "sac_recommendation": appeal.sac_recommendation,
        "council_outcome": appeal.council_outcome,
        "council_decision": appeal.council_decision,
    }
    if include_private:
        result["grounds"] = appeal.grounds
        result["evidence"] = [
            row.document_id
            for row in db.scalars(
                select(AppealEvidence).where(AppealEvidence.appeal_id == appeal.id)
            ).all()
        ]
        result["representatives"] = [
            {
                "position": row.position,
                "name": row.name,
                "institutional_role": row.institutional_role,
                "id_document_id": row.id_document_id,
                "authorization_attested": row.authorization_attested,
            }
            for row in _representatives(db, appeal.id)
        ]
    return result


def _audit(db: Session, *, action: str, application_id: str, access: EffectiveAccess,
           outcome: str, after: dict, reason: str = "") -> None:
    AuditService(db).append(
        action=action,
        entity_type="application",
        entity_id=application_id,
        outcome=outcome,
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason,
        after=after,
        request_id=current_request_id(),
    )


def _appeal(db: Session, appeal_id: str) -> Appeal:
    item = db.get(Appeal, appeal_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appeal not found")
    return item


def _case(db: Session, access: EffectiveAccess, item: Appeal) -> Application:
    return require_application(db, access, item.application_id)


def _decision_upload(db: Session, application: Application) -> WorkflowTransition | None:
    return db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application.id,
            WorkflowTransition.to_state == application.current_state,
            WorkflowTransition.action.in_(("approve", "reject")),
            WorkflowTransition.reverted_at.is_(None),
            WorkflowTransition.speaking_order_document_id.is_not(None),
        )
        .order_by(WorkflowTransition.created_at.desc(), WorkflowTransition.id.desc())
    ).first()


@router.post("/applications/{application_id}/appeals", status_code=status.HTTP_201_CREATED)
def submit_appeal(
    application_id: str,
    payload: AppealSubmission,
    access: EffectiveAccess = Depends(require(APPEAL_SUBMIT)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    now = to_utc(get_clock().now())
    if not appeal_policy_service.in_verified_scope(application):
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "application_outside_verified_chapter_ii_scope"})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "appeals are enabled only for the verified Chapter II application routes")
    decision = _decision_upload(db, application) if application.current_state in {"approved", "rejected"} else None
    if decision is None:
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "no_uploaded_executive_decision"})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "an uploaded Executive Committee decision is required")
    order = db.get(Document, decision.speaking_order_document_id)
    if order is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the linked decision document is unavailable")
    deadline = to_utc(order.uploaded_at) + timedelta(days=window_days())
    if now > deadline:
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "appeal_period_elapsed", "deadline": iso(deadline)})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "the verified seven-day appeal period has elapsed")
    existing = db.scalar(select(Appeal.id).where(Appeal.application_id == application.id))
    if existing:
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "appeal_already_filed"})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "only one appeal may be filed for this decision")
    docs = db.scalars(
        select(Document).where(
            Document.id.in_(payload.supporting_document_ids),
            Document.application_id == application.id,
            Document.doc_type == "appeal_supporting_evidence",
        )
    ).all()
    if len(set(payload.supporting_document_ids)) != len(payload.supporting_document_ids) or len({doc.id for doc in docs}) != len(payload.supporting_document_ids):
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "invalid_supporting_document_reference"})
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "supporting evidence must be uploaded to this application as appeal evidence")

    item = Appeal(
        application_id=application.id,
        decision_transition_id=decision.id,
        appellant_id=access.user_id,
        grounds=payload.grounds.strip(),
        submitted_at=now,
        appeal_deadline=deadline,
        status="submitted",
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        _audit(db, action="appeal.submission_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"reason": "appeal_already_filed"})
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "only one appeal may be filed for this decision") from None
    db.add_all(AppealEvidence(appeal_id=item.id, document_id=doc.id) for doc in docs)
    _audit(db, action="appeal.submitted", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id, "evidence_count": len(docs), "deadline": iso(deadline)})
    db.commit()
    db.refresh(item)
    return _view(db, item, include_private=True)


@router.get("/applications/{application_id}/appeal")
def get_application_appeal(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPEAL_SUBMIT, SAC_APPEAL_READ, SAC_APPEAL_MANAGE, COUNCIL_APPEAL_READ, COUNCIL_DECISION_RECORD)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    if not ({APPEAL_SUBMIT, SAC_APPEAL_READ, SAC_APPEAL_MANAGE, COUNCIL_APPEAL_READ, COUNCIL_DECISION_RECORD} & access.permissions):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "appeal access required")
    item = db.scalar(select(Appeal).where(Appeal.application_id == application.id))
    if item is None:
        return {"application_id": application.id, "appeal": None}
    return {"application_id": application.id, "appeal": _view(db, item, include_private=True)}


@router.post("/appeals/{appeal_id}/representatives")
def set_representatives(
    appeal_id: str,
    payload: RepresentativesIn,
    access: EffectiveAccess = Depends(require(APPEAL_SUBMIT)),
    db: Session = Depends(get_db),
) -> dict:
    item = _appeal(db, appeal_id)
    application = _case(db, access, item)
    if item.appellant_id != access.user_id or item.status not in {"submitted", "scheduled"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "representatives can be recorded by the appellant before the hearing")
    ids = [row.id_document_id for row in payload.representatives]
    docs = db.scalars(select(Document).where(Document.id.in_(ids), Document.application_id == application.id, Document.doc_type == "appeal_representative_id")).all()
    if len(docs) != 2 or any(not row.authorization_attested for row in payload.representatives):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "two authorized representatives and their self-attested photo ID documents are required")
    for existing in _representatives(db, item.id):
        db.delete(existing)
    db.flush()
    for position, row in enumerate(payload.representatives, start=1):
        db.add(AppealRepresentative(appeal_id=item.id, position=position, name=row.name.strip(), institutional_role=row.institutional_role.strip(), id_document_id=row.id_document_id, authorization_attested=True))
    _audit(db, action="appeal.representatives_recorded", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id, "representative_count": 2})
    db.commit()
    return _view(db, item, include_private=True)


def _queue(db: Session, access: EffectiveAccess, *, council: bool) -> dict:
    scope = scope_filter(access)
    query = select(Appeal).join(Application)
    query = query.where(
        Appeal.status == "heard"
        if council
        else Appeal.status.in_(("submitted", "scheduled", "heard"))
    )
    if scope is not None:
        query = query.where(scope)
    rows = db.scalars(query.order_by(Appeal.submitted_at)).all()
    return {"rows": [_view(db, row, include_private=True) for row in rows]}


@router.get("/sac/appeals")
def sac_appeals(access: EffectiveAccess = Depends(require(SAC_APPEAL_READ)), db: Session = Depends(get_db)) -> dict:
    if SAC_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SAC member role required")
    return _queue(db, access, council=False)


@router.post("/sac/appeals/{appeal_id}/schedule")
def schedule_hearing(appeal_id: str, payload: HearingSchedule, access: EffectiveAccess = Depends(require(SAC_APPEAL_MANAGE)), db: Session = Depends(get_db)) -> dict:
    if SAC_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SAC member role required")
    item = _appeal(db, appeal_id)
    application = _case(db, access, item)
    hearing_at = to_utc(payload.hearing_at)
    if item.status not in {"submitted", "scheduled"} or hearing_at <= to_utc(get_clock().now()):
        raise HTTPException(status.HTTP_409_CONFLICT, "a future SAC hearing can be scheduled only for an open appeal")
    reps = _representatives(db, item.id)
    if len(reps) != 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "the institution must register two authorized representatives and ID evidence before scheduling")
    item.hearing_at = hearing_at
    item.hearing_venue = payload.venue.strip() if payload.venue else None
    item.hearing_url = str(payload.meeting_url) if payload.meeting_url else None
    item.status = "scheduled"
    _audit(db, action="appeal.hearing_scheduled", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id, "hearing_at": iso(hearing_at)})
    db.commit()
    return _view(db, item, include_private=True)


@router.post("/sac/appeals/{appeal_id}/hearing-record")
def record_hearing(appeal_id: str, payload: HearingRecord, access: EffectiveAccess = Depends(require(SAC_APPEAL_MANAGE)), db: Session = Depends(get_db)) -> dict:
    if SAC_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SAC member role required")
    item = _appeal(db, appeal_id)
    application = _case(db, access, item)
    if item.status != "scheduled" or item.hearing_at is None or to_utc(get_clock().now()) < to_utc(item.hearing_at):
        raise HTTPException(status.HTTP_409_CONFLICT, "record the SAC outcome after the scheduled hearing")
    if len(_representatives(db, item.id)) != 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "two authorized institutional representatives must be recorded")
    item.sac_recommendation = payload.recommendation.strip()
    item.sac_recommendation_at = to_utc(get_clock().now())
    item.status = "heard"
    _audit(db, action="appeal.sac_recommendation_recorded", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id})
    db.commit()
    return _view(db, item, include_private=True)


@router.get("/council/appeals")
def council_appeals(access: EffectiveAccess = Depends(require(COUNCIL_APPEAL_READ)), db: Session = Depends(get_db)) -> dict:
    if COUNCIL_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Council member role required")
    return _queue(db, access, council=True)


@router.post("/council/appeals/{appeal_id}/decision")
def council_decision(appeal_id: str, payload: CouncilDecisionIn, access: EffectiveAccess = Depends(require(COUNCIL_DECISION_RECORD)), db: Session = Depends(get_db)) -> dict:
    if COUNCIL_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Council member role required")
    item = _appeal(db, appeal_id)
    application = _case(db, access, item)
    if item.status != "heard" or not item.sac_recommendation:
        raise HTTPException(status.HTTP_409_CONFLICT, "a completed SAC hearing recommendation is required before Council decision")
    order = db.get(Document, payload.decision_document_id)
    if order is None or order.application_id != application.id or order.doc_type != "council_decision_order":
        _audit(db, action="appeal.council_decision_rejected", application_id=application.id,
               access=access, outcome="rejected", after={"appeal_id": item.id, "reason": "invalid_decision_order"})
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Council decision order must be uploaded to this application")
    action = {
        ("approved", "approved"): "council_confirm_approval",
        ("approved", "not_approved"): "council_not_approve",
        ("rejected", "approved"): "council_grant_approval",
        ("rejected", "not_approved"): "council_confirm_rejection",
    }.get((application.current_state, payload.outcome))
    if action is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "application is no longer in an Executive Committee decision state")
    transition = request_transition(
        db, access, application.id, action, payload.decision.strip(),
        request_id=current_request_id(), commit_changes=False,
    )
    if not transition.accepted:
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(transition.reasons))
    item.status = "decided"
    item.council_outcome = payload.outcome
    item.council_decision = payload.decision.strip()
    item.council_decision_document_id = order.id
    item.council_decided_at = to_utc(get_clock().now())
    item.council_actor_id = access.user_id
    _audit(db, action="appeal.council_decision_recorded", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id, "outcome": item.council_outcome, "order_document_id": order.id})
    db.commit()
    return _view(db, item, include_private=True)


@router.get("/appeals/{appeal_id}/evidence/{document_id}")
def appeal_document(appeal_id: str, document_id: str, access: EffectiveAccess = Depends(require_any(APPEAL_SUBMIT, SAC_APPEAL_READ, SAC_APPEAL_MANAGE, COUNCIL_APPEAL_READ, COUNCIL_DECISION_RECORD)), db: Session = Depends(get_db)) -> Response:
    item = _appeal(db, appeal_id)
    application = _case(db, access, item)
    if not ({APPEAL_SUBMIT, SAC_APPEAL_READ, SAC_APPEAL_MANAGE, COUNCIL_APPEAL_READ, COUNCIL_DECISION_RECORD} & access.permissions):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "appeal evidence access required")
    evidence = db.scalar(select(AppealEvidence.id).where(AppealEvidence.appeal_id == item.id, AppealEvidence.document_id == document_id))
    representative = db.scalar(select(AppealRepresentative.id).where(AppealRepresentative.appeal_id == item.id, AppealRepresentative.id_document_id == document_id))
    document = db.get(Document, document_id)
    decision_transition = db.get(WorkflowTransition, item.decision_transition_id)
    linked_order = document_id in {
        item.council_decision_document_id,
        item.hearing_notice_document_id,
        decision_transition.speaking_order_document_id if decision_transition else None,
    }
    if document is None or document.application_id != application.id or not (evidence or representative or linked_order):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appeal document not found")
    if document.storage_ref.startswith("seed://"):
        from .documents import _placeholder_pdf
        content = _placeholder_pdf(document)
    else:
        root = Path(get_settings().storage_dir).resolve()
        path = Path(document.storage_ref).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(status.HTTP_410_GONE, "appeal document is unavailable")
        content = path.read_bytes()
    _audit(db, action="appeal.document_accessed", application_id=application.id,
           access=access, outcome="accepted", after={"appeal_id": item.id, "document_id": document.id, "sha256": document.file_sha256})
    db.commit()
    return Response(content, media_type=document.content_type, headers={"Content-Disposition": f'attachment; filename="{document.file_name}"', "X-Content-SHA256": document.file_sha256})
