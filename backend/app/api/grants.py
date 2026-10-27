"""Chapter II consolidated grant list, Council ratification and EoA publication."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import (
    APPLICATION_READ,
    CASE_READ,
    COUNCIL_MEMBER,
    GRANT_BATCH_MANAGE,
    GRANT_COUNCIL_RATIFY,
    GRANT_LETTER_UPLOAD,
    GRANT_READ,
)
from ..models import (
    Appeal,
    Application,
    Document,
    GrantBatch,
    GrantEntry,
    WorkflowTransition,
)
from ..services.appeal import window_days
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application
from ..services.working_calendar import business_date
from . import documents as documents_api
from .deps import require, require_any

router = APIRouter(prefix="/grant", tags=["grant"])


class IntakeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: str
    approved_intake: list[dict] = Field(min_length=1, max_length=200)


class GrantBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle: str = Field(min_length=4, max_length=16)
    last_grant_date: date
    calendar_source: HttpUrl
    entries: list[IntakeEntry] = Field(min_length=1, max_length=500)


class RatificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=2000)


def _audit(
    db: Session,
    *,
    access: EffectiveAccess,
    action: str,
    entity_type: str,
    entity_id: str,
    after: dict,
    outcome: str = "accepted",
) -> None:
    AuditService(db).append(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after=after,
        request_id=current_request_id(),
    )


def _eligible(db: Session, application: Application) -> bool:
    if application.current_state != "approved" or application.route_key not in {
        "existing_technical",
        "evc_only",
        "evc_sac_shc",
    }:
        return False
    appeal = db.scalar(select(Appeal).where(Appeal.application_id == application.id))
    if appeal:
        return appeal.status == "decided" and appeal.council_outcome == "approved"
    decision = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id == application.id,
            WorkflowTransition.to_state == "approved",
            WorkflowTransition.reverted_at.is_(None),
            WorkflowTransition.speaking_order_document_id.is_not(None),
        )
        .order_by(WorkflowTransition.created_at.desc())
    ).first()
    if decision is None:
        return False
    return bool(
        decision.created_at
        and to_utc(get_clock().now())
        > to_utc(decision.created_at) + timedelta(days=window_days())
    )


def _batch(db: Session, batch_id: str) -> GrantBatch:
    item = db.get(GrantBatch, batch_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grant batch not found")
    return item


def _view(db: Session, batch: GrantBatch) -> dict:
    entries = db.scalars(select(GrantEntry).where(GrantEntry.batch_id == batch.id)).all()
    return {
        "id": batch.id,
        "cycle": batch.cycle,
        "status": batch.status,
        "last_grant_date": batch.last_grant_date.isoformat(),
        "calendar_source": batch.calendar_source,
        "ratified_at": iso(to_utc(batch.ratified_at)) if batch.ratified_at else None,
        "published_at": iso(to_utc(batch.published_at)) if batch.published_at else None,
        "entries": [
            {
                "application_id": e.application_id,
                "approved_intake": e.approved_intake,
                "letter_document_id": e.letter_document_id,
            }
            for e in entries
        ],
    }


@router.get("/eligible")
def eligible_applications(
    access: EffectiveAccess = Depends(require(GRANT_BATCH_MANAGE)), db: Session = Depends(get_db)
) -> list[dict]:
    apps = db.scalars(
        select(Application)
        .where(Application.current_state == "approved")
        .order_by(Application.cycle, Application.id)
    ).all()
    already_listed = set(
        db.scalars(
            select(GrantEntry.application_id).where(
                GrantEntry.application_id.in_([app.id for app in apps])
            )
        ).all()
    )
    return [
        {
            "application_id": app.id,
            "cycle": app.cycle,
            "institution_id": app.institution_id,
            "eligible": True,
        }
        for app in apps
        if app.id not in already_listed and _eligible(db, app)
    ]


@router.post("/batches", status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: GrantBatchIn,
    access: EffectiveAccess = Depends(require(GRANT_BATCH_MANAGE)),
    db: Session = Depends(get_db),
) -> dict:
    now = to_utc(get_clock().now())
    if business_date(now) > payload.last_grant_date:
        _audit(
            db,
            access=access,
            action="grant.batch_rejected",
            entity_type="grant_batch",
            entity_id="new",
            outcome="rejected",
            after={
                "reason": "academic_calendar_last_date_elapsed",
                "last_grant_date": payload.last_grant_date.isoformat(),
            },
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "the supplied Academic Calendar grant date has elapsed"
        )
    app_ids = [item.application_id for item in payload.entries]
    if len(set(app_ids)) != len(app_ids):
        _audit(
            db,
            access=access,
            action="grant.batch_rejected",
            entity_type="grant_batch",
            entity_id="new",
            outcome="rejected",
            after={"reason": "duplicate_application_entry"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "an application may appear only once in a batch"
        )
    apps = {
        a.id: a for a in db.scalars(select(Application).where(Application.id.in_(app_ids))).all()
    }
    if len(apps) != len(app_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "one or more applications were not found")
    previously_listed = set(
        db.scalars(
            select(GrantEntry.application_id).where(GrantEntry.application_id.in_(app_ids))
        ).all()
    )
    for item in payload.entries:
        app = apps[item.application_id]
        if (
            app.id in previously_listed
            or app.cycle != payload.cycle
            or not _eligible(db, app)
        ):
            _audit(
                db,
                access=access,
                action="grant.batch_rejected",
                entity_type="application",
                entity_id=app.id,
                outcome="rejected",
                after={"reason": "application_not_finalized_for_grant"},
            )
            db.commit()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "every entry must be a finalized eligible Chapter II application in this cycle",
            )
        for course in item.approved_intake:
            if (
                set(course) != {"course_name", "approved_intake"}
                or not isinstance(course["course_name"], str)
                or not course["course_name"].strip()
                or not isinstance(course["approved_intake"], int)
                or isinstance(course["approved_intake"], bool)
                or course["approved_intake"] < 0
            ):
                _audit(
                    db,
                    access=access,
                    action="grant.intake_rejected",
                    entity_type="application",
                    entity_id=app.id,
                    outcome="rejected",
                    after={"reason": "invalid_human_entered_approved_intake"},
                )
                db.commit()
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "each approved intake needs a course name and non-negative human-entered integer",
                )
    batch = GrantBatch(
        cycle=payload.cycle,
        status="consolidated",
        last_grant_date=payload.last_grant_date,
        calendar_source=str(payload.calendar_source),
        created_by=access.user_id,
    )
    db.add(batch)
    db.flush()
    for item in payload.entries:
        db.add(
            GrantEntry(
                batch_id=batch.id,
                application_id=item.application_id,
                approved_intake=item.approved_intake,
            )
        )
    _audit(
        db,
        access=access,
        action="grant.batch_consolidated",
        entity_type="grant_batch",
        entity_id=batch.id,
        after={
            "cycle": batch.cycle,
            "entry_count": len(payload.entries),
            "last_grant_date": payload.last_grant_date.isoformat(),
            "calendar_source": str(payload.calendar_source),
        },
    )
    db.commit()
    return _view(db, batch)


@router.get("/batches")
def list_batches(
    access: EffectiveAccess = Depends(require_any(GRANT_BATCH_MANAGE, GRANT_COUNCIL_RATIFY)),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        _view(db, item)
        for item in db.scalars(select(GrantBatch).order_by(GrantBatch.created_at.desc())).all()
    ]


@router.post("/batches/{batch_id}/ratify")
def ratify_batch(
    batch_id: str,
    payload: RatificationIn,
    access: EffectiveAccess = Depends(require(GRANT_COUNCIL_RATIFY)),
    db: Session = Depends(get_db),
) -> dict:
    batch = _batch(db, batch_id)
    if COUNCIL_MEMBER not in access.roles or batch.status != "consolidated":
        _audit(
            db,
            access=access,
            action="grant.ratification_rejected",
            entity_type="grant_batch",
            entity_id=batch.id,
            outcome="rejected",
            after={"reason": "wrong_role_or_batch_state"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "only Council may ratify a consolidated batch"
        )
    batch.status = "ratified"
    batch.ratified_by = access.user_id
    batch.ratified_at = get_clock().now()
    _audit(
        db,
        access=access,
        action="grant.batch_ratified",
        entity_type="grant_batch",
        entity_id=batch.id,
        after={"reason": payload.reason},
    )
    db.commit()
    return _view(db, batch)


@router.post(
    "/batches/{batch_id}/applications/{application_id}/letter", status_code=status.HTTP_201_CREATED
)
def upload_grant_letter(
    batch_id: str,
    application_id: str,
    file: Annotated[UploadFile, File(...)],
    access: EffectiveAccess = Depends(require(GRANT_LETTER_UPLOAD)),
    db: Session = Depends(get_db),
) -> dict:
    batch = _batch(db, batch_id)
    entry = db.scalar(
        select(GrantEntry).where(
            GrantEntry.batch_id == batch.id, GrantEntry.application_id == application_id
        )
    )
    if entry is None or batch.status != "ratified":
        _audit(
            db,
            access=access,
            action="grant.letter_rejected",
            entity_type="application",
            entity_id=application_id,
            outcome="rejected",
            after={"reason": "ratified_batch_entry_required", "batch_id": batch.id},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a ratified batch entry is required before an EoA letter can be attached",
        )
    require_application(db, access, application_id)
    result = documents_api.upload_document(
        application_id,
        doc_type="eoa_letter",
        file=file,
        reason="Chapter II Extension of Approval letter",
        access=access,
        db=db,
    )
    document_id = result.get("document", {}).get("id")
    if not document_id:
        document = db.scalars(
            select(Document)
            .where(Document.application_id == application_id, Document.doc_type == "eoa_letter")
            .order_by(Document.uploaded_at.desc())
        ).first()
        document_id = document.id if document else None
    if not document_id:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "uploaded letter record was not returned"
        )
    entry.letter_document_id = document_id
    _audit(
        db,
        access=access,
        action="grant.letter_uploaded",
        entity_type="application",
        entity_id=application_id,
        after={"batch_id": batch.id, "document_id": document_id},
    )
    db.commit()
    return {"application_id": application_id, "document_id": document_id}


@router.post("/batches/{batch_id}/publish")
def publish_batch(
    batch_id: str,
    access: EffectiveAccess = Depends(require(GRANT_BATCH_MANAGE)),
    db: Session = Depends(get_db),
) -> dict:
    batch = _batch(db, batch_id)
    entries = db.scalars(select(GrantEntry).where(GrantEntry.batch_id == batch.id)).all()
    if (
        batch.status != "ratified"
        or not entries
        or any(entry.letter_document_id is None for entry in entries)
    ):
        _audit(
            db,
            access=access,
            action="grant.publication_rejected",
            entity_type="grant_batch",
            entity_id=batch.id,
            outcome="rejected",
            after={"reason": "ratification_or_eoa_letter_missing"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Council ratification and an EoA letter for every entry are required",
        )
    if business_date(to_utc(get_clock().now())) > batch.last_grant_date:
        _audit(
            db,
            access=access,
            action="grant.publication_rejected",
            entity_type="grant_batch",
            entity_id=batch.id,
            outcome="rejected",
            after={"reason": "academic_calendar_last_date_elapsed"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "the supplied Academic Calendar grant date has elapsed"
        )
    batch.status = "published"
    batch.published_at = get_clock().now()
    _audit(
        db,
        access=access,
        action="grant.batch_published",
        entity_type="grant_batch",
        entity_id=batch.id,
        after={"entry_count": len(entries)},
    )
    db.commit()
    return _view(db, batch)


@router.get("/applications/{application_id}")
def institution_grant(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(GRANT_READ, APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    require_application(db, access, application_id)
    entry = db.scalar(
        select(GrantEntry)
        .join(GrantBatch, GrantBatch.id == GrantEntry.batch_id)
        .where(GrantEntry.application_id == application_id, GrantBatch.status == "published")
    )
    if entry is None:
        return {"application_id": application_id, "published": False}
    batch = db.get(GrantBatch, entry.batch_id)
    _audit(
        db,
        access=access,
        action="grant.published_record_viewed",
        entity_type="application",
        entity_id=application_id,
        after={"batch_id": batch.id, "letter_document_id": entry.letter_document_id},
    )
    db.commit()
    return {
        "application_id": application_id,
        "published": True,
        "cycle": batch.cycle,
        "approved_intake": entry.approved_intake,
        "letter_document_id": entry.letter_document_id,
        "published_at": iso(to_utc(batch.published_at)),
    }
