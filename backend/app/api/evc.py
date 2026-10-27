"""Expert Visit Committee scheduling and the EVC queue.

Scheduling records *when* and *where* a visit happens and feeds the queue and
timeline reports plus the deadline sweep (visits that were due but never
recorded). When a booking is made and the route's `schedule_evc` transition is
available to the caller — right state, right role, evidence and rules met — the
case moves to the committee stage with the booking instead of waiting for a
second click; otherwise the statutory gate stays exactly where it is.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import (
    APPLICATION_READ,
    CASE_DECIDE,
    CASE_READ,
    CASE_TRANSITION,
    COMPETENT_AUTHORITY,
    DOCUMENT_READ,
    EVC_REPORT_UPLOAD,
    EVC_VISIT_CONFIRM,
    EXECUTIVE_COMMITTEE_MEMBER,
    EXECUTIVE_DECISION_RECORD,
    EXECUTIVE_ORDER_UPLOAD,
    EXECUTIVE_QUEUE_READ,
    FRAUD_REFERRAL_READ,
    MONITORING_READ,
    SHC_HEARING_SCHEDULE,
    SHC_MEMBER,
    SHC_QUEUE_READ,
    SHC_RECOMMENDATION_WRITE,
)
from ..models import (
    Application,
    CaseAssignment,
    Committee,
    Document,
    EvcReport,
    EvcVisit,
    FraudReferral,
    Institution,
    Region,
    ScrutinyOverallResult,
    ShcHearing,
    WorkflowTransitionDefinition,
)
from ..services import evc_service, workflow_service
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
    scope_filter,
)
from ..services.policy import stage_sla_days
from .deps import require, require_any

router = APIRouter(tags=["evc"])


class VisitScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_date: date
    visit_mode: Literal["online", "physical"]
    venue: str = Field(default="", max_length=255)
    meeting_url: str | None = Field(default=None, max_length=2048)
    committee_id: str | None = None
    expert_user_ids: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=1024)


class EvcReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    summary: str = Field(default="", max_length=10000)
    deficiency_present: bool
    fraud_flag: bool = False
    fraud_referral_reason: str | None = Field(default=None, max_length=2000)


class ShcScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_date: date
    visit_mode: Literal["online", "physical"]
    venue: str = Field(default="", max_length=255)
    meeting_url: str | None = Field(default=None, max_length=2048)


class ShcRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compliance_record: str = Field(min_length=1, max_length=10000)
    recommendation: str = Field(min_length=1, max_length=10000)


class ExecutiveDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["approved", "rejected"]
    speaking_order_document_id: str
    reason: str = Field(min_length=1, max_length=1024)
    expected_baseline_version: int | None = None


def _reject_evc_action(
    db: Session,
    *,
    application: Application,
    access: EffectiveAccess,
    visit_id: str,
    reason_code: str,
    message: str,
    status_code: int,
    action: str = "evc.report_submission_rejected",
) -> None:
    AuditService(db).append(
        action=action,
        entity_type="application",
        entity_id=application.id,
        outcome="rejected",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=reason_code,
        after={"visit_id": visit_id, "reason_code": reason_code},
        request_id=current_request_id(),
    )
    db.commit()
    raise HTTPException(status_code, message)


@router.post(
    "/applications/{application_id}/evc/visits/{visit_id}/report/document",
    status_code=201,
)
def upload_evc_report_document(
    application_id: str,
    visit_id: str,
    file: UploadFile = File(...),
    access: EffectiveAccess = Depends(require(EVC_REPORT_UPLOAD)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    visit = db.get(EvcVisit, visit_id)
    if visit is None or visit.application_id != application.id:
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="visit_not_found", message="visit not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if "evc_member" not in access.roles or not evc_service.is_assigned_expert(
        db, visit_id=visit.id, user_id=access.user_id
    ):
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="expert_not_assigned", message="assigned EVC expert role required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if visit.status != "scheduled":
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="visit_not_open", message="visit is not open for report upload",
            status_code=status.HTTP_409_CONFLICT,
        )
    from .documents import upload_document

    return upload_document(
        application_id=application.id,
        doc_type="evc_report",
        file=file,
        reason="EVC visit report",
        access=access,
        db=db,
    )


def _serialise(
    visit: EvcVisit,
    committee_name: str | None,
    assigned_experts: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "id": visit.id,
        "application_id": visit.application_id,
        "committee_id": visit.committee_id,
        "committee_name": committee_name,
        "scheduled_date": visit.scheduled_date.isoformat(),
        "visit_mode": visit.visit_mode,
        "venue": visit.venue,
        "meeting_url": visit.meeting_url,
        "confirmation_status": visit.confirmation_status,
        "confirmed_at": iso(visit.confirmed_at),
        "assigned_experts": assigned_experts or [],
        "status": visit.status,
        "notes": visit.notes,
        "created_at": iso(visit.created_at),
        "completed_at": iso(visit.completed_at),
    }


@router.post("/applications/{application_id}/evc/visits/{visit_id}/report", status_code=201)
def submit_evc_report(
    application_id: str,
    visit_id: str,
    payload: EvcReportRequest,
    access: EffectiveAccess = Depends(require(CASE_DECIDE)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    visit = db.get(EvcVisit, visit_id)
    if visit is None or visit.application_id != application.id:
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="visit_not_found", message="visit not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if "evc_member" not in access.roles or not evc_service.is_assigned_expert(
        db, visit_id=visit.id, user_id=access.user_id
    ):
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="expert_not_assigned", message="assigned EVC expert role required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    document = db.get(Document, payload.document_id)
    if (
        document is None
        or document.application_id != application.id
        or document.doc_type != "evc_report"
    ):
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="invalid_report_document",
            message="an EVC report document for this case is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if visit.status != "scheduled":
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="visit_not_open", message="visit is not open for report submission",
            status_code=status.HTTP_409_CONFLICT,
        )
    if payload.fraud_flag and not (payload.fraud_referral_reason or "").strip():
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="fraud_reason_required",
            message="fraud referral reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if db.scalar(select(EvcReport.id).where(EvcReport.visit_id == visit.id)):
        _reject_evc_action(
            db, application=application, access=access, visit_id=visit_id,
            reason_code="report_already_recorded",
            message="a report is already recorded for this visit",
            status_code=status.HTTP_409_CONFLICT,
        )

    report = EvcReport(
        visit_id=visit.id,
        document_id=document.id,
        submitted_by=access.user_id,
        summary=payload.summary.strip(),
        deficiency_present=payload.deficiency_present,
        fraud_flag=payload.fraud_flag,
        created_at=get_clock().now(),
    )
    db.add(report)
    db.flush()
    application.baseline_version += 1
    if payload.fraud_flag:
        referral = FraudReferral(
            report_id=report.id,
            application_id=application.id,
            referred_by=access.user_id,
            reason=payload.fraud_referral_reason.strip(),
            status="pending",
            created_at=get_clock().now(),
        )
        db.add(referral)
        db.flush()
    else:
        referral = None

    AuditService(db).append(
        action="evc.report_submitted",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "visit_id": visit.id,
            "report_id": report.id,
            "document_id": document.id,
            "deficiency_present": report.deficiency_present,
            "fraud_flag": report.fraud_flag,
            "fraud_referral_id": referral.id if referral else None,
        },
        request_id=current_request_id(),
    )
    if referral:
        AuditService(db).append(
            action="fraud.referral_created",
            entity_type="application",
            entity_id=application.id,
            outcome="accepted",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            after={"referral_id": referral.id, "report_id": report.id},
            request_id=current_request_id(),
        )
    db.commit()
    return {
        "id": report.id,
        "visit_id": visit.id,
        "document_id": document.id,
        "deficiency_present": report.deficiency_present,
        "fraud_flag": report.fraud_flag,
        "fraud_referral_id": referral.id if referral else None,
        "created_at": iso(report.created_at),
    }


@router.get("/applications/{application_id}/evc/visits/{visit_id}/report")
def get_evc_report(
    application_id: str,
    visit_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    report = db.scalar(
        select(EvcReport).join(EvcVisit).where(
            EvcVisit.id == visit_id,
            EvcVisit.application_id == application.id,
        )
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report not found")
    return {
        "id": report.id,
        "visit_id": report.visit_id,
        "document_id": report.document_id,
        "summary": report.summary,
        "deficiency_present": report.deficiency_present,
        "fraud_flag": report.fraud_flag,
        "created_at": iso(report.created_at),
    }


@router.get("/evc/fraud-referrals")
def list_fraud_referrals(
    access: EffectiveAccess = Depends(require(FRAUD_REFERRAL_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    if COMPETENT_AUTHORITY not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "competent authority role required")
    query = (
        select(FraudReferral, Application, EvcReport)
        .join(Application, Application.id == FraudReferral.application_id)
        .join(EvcReport, EvcReport.id == FraudReferral.report_id)
        .where(FraudReferral.status == "pending")
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    return [
        {
            "id": referral.id,
            "application_id": application.id,
            "report_id": referral.report_id,
            "reason": referral.reason,
            "summary": report.summary,
            "status": referral.status,
            "created_at": iso(referral.created_at),
            "penal_action_taken": False,
        }
        for referral, application, report in db.execute(
            query.order_by(FraudReferral.created_at, FraudReferral.id)
        ).all()
    ]


@router.get("/evc/fraud-referrals/{referral_id}/document")
def download_fraud_referral_report(
    referral_id: str,
    access: EffectiveAccess = Depends(require(FRAUD_REFERRAL_READ)),
    db: Session = Depends(get_db),
) -> Response:
    if COMPETENT_AUTHORITY not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "competent authority role required")
    query = (
        select(FraudReferral, EvcReport, Application)
        .join(EvcReport, EvcReport.id == FraudReferral.report_id)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == FraudReferral.application_id)
        .where(FraudReferral.id == referral_id, FraudReferral.status == "pending")
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    row = db.execute(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral not found")
    _referral, report, application = row
    from .documents import download_document

    return download_document(
        application_id=application.id,
        document_id=report.document_id,
        access=access,
        db=db,
    )


@router.get("/shc/queue")
def shc_queue(
    access: EffectiveAccess = Depends(require(SHC_QUEUE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    if SHC_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SHC member role required")
    query = (
        select(EvcReport, Application, Institution, EvcVisit, ShcHearing)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == EvcVisit.application_id)
        .join(Institution, Institution.id == Application.institution_id)
        .outerjoin(ShcHearing, ShcHearing.report_id == EvcReport.id)
        .where(
            EvcReport.deficiency_present.is_(True),
            EvcVisit.status == "completed",
            or_(ShcHearing.id.is_(None), ShcHearing.recommendation.is_(None)),
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    rows = db.execute(query.order_by(EvcVisit.completed_at, EvcReport.id)).all()
    return {
        "count": len(rows),
        "source": "human-recorded EVC deficiency reports",
        "rows": [
            {
                "application_id": application.id,
                "institution": institution.name,
                "report_id": report.id,
                "summary": report.summary,
                "visit_id": visit.id,
                "reported_at": iso(report.created_at),
                "hearing": {
                    "id": hearing.id,
                    "scheduled_date": hearing.scheduled_date.isoformat(),
                    "visit_mode": hearing.visit_mode,
                    "venue": hearing.venue,
                    "meeting_url": hearing.meeting_url,
                    "status": hearing.status,
                } if hearing else None,
            }
            for report, application, institution, visit, hearing in rows
        ],
    }


@router.post("/shc/queue/{report_id}/hearing", status_code=201)
def schedule_shc_hearing(
    report_id: str,
    payload: ShcScheduleRequest,
    access: EffectiveAccess = Depends(require(SHC_HEARING_SCHEDULE)),
    db: Session = Depends(get_db),
) -> dict:
    if SHC_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SHC member role required")
    query = (
        select(EvcReport, Application)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == EvcVisit.application_id)
        .where(
            EvcReport.id == report_id,
            EvcReport.deficiency_present.is_(True),
            EvcVisit.status == "completed",
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    row = db.execute(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SHC referral not found")
    report, application = row
    if payload.scheduled_date < get_clock().now().date():
        _reject_evc_action(
            db, application=application, access=access, visit_id=report_id,
            reason_code="hearing_date_in_past", message="hearing date cannot be in the past",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, action="shc.hearing_rejected",
        )
    if payload.visit_mode == "physical" and not payload.venue.strip():
        _reject_evc_action(
            db, application=application, access=access, visit_id=report_id,
            reason_code="hearing_venue_required", message="venue is required for a physical hearing",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, action="shc.hearing_rejected",
        )
    try:
        meeting_url = urlsplit(payload.meeting_url or "")
        secure_meeting_url = (
            meeting_url.scheme == "https"
            and bool(meeting_url.hostname)
            and meeting_url.username is None
            and meeting_url.password is None
        )
    except ValueError:
        secure_meeting_url = False
    if payload.visit_mode == "online" and not secure_meeting_url:
        _reject_evc_action(
            db, application=application, access=access, visit_id=report_id,
            reason_code="secure_hearing_link_required", message="an HTTPS link is required for an online hearing",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, action="shc.hearing_rejected",
        )
    hearing = db.scalar(select(ShcHearing).where(ShcHearing.report_id == report.id))
    before = None
    if hearing is not None:
        if hearing.status == "completed":
            _reject_evc_action(
                db, application=application, access=access, visit_id=report_id,
                reason_code="hearing_already_completed", message="completed hearing cannot be rescheduled",
                status_code=status.HTTP_409_CONFLICT, action="shc.hearing_rejected",
            )
        before = {
            "scheduled_date": hearing.scheduled_date.isoformat(),
            "visit_mode": hearing.visit_mode,
            "venue": hearing.venue,
        }
        hearing.scheduled_date = payload.scheduled_date
        hearing.visit_mode = payload.visit_mode
        hearing.venue = payload.venue.strip()
        hearing.meeting_url = payload.meeting_url
    else:
        hearing = ShcHearing(
            report_id=report.id,
            scheduled_date=payload.scheduled_date,
            visit_mode=payload.visit_mode,
            venue=payload.venue.strip(),
            meeting_url=payload.meeting_url,
            status="scheduled",
            scheduled_by=access.user_id,
            created_at=get_clock().now(),
        )
        db.add(hearing)
    application.baseline_version += 1
    db.flush()
    AuditService(db).append(
        action="shc.hearing_rescheduled" if before else "shc.hearing_scheduled",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        before=before,
        after={
            "hearing_id": hearing.id,
            "report_id": report.id,
            "scheduled_date": hearing.scheduled_date.isoformat(),
            "visit_mode": hearing.visit_mode,
            "venue": hearing.venue,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return {
        "id": hearing.id,
        "report_id": report.id,
        "scheduled_date": hearing.scheduled_date.isoformat(),
        "visit_mode": hearing.visit_mode,
        "venue": hearing.venue,
        "meeting_url": hearing.meeting_url,
        "status": hearing.status,
    }


@router.post("/shc/queue/{report_id}/recommendation")
def record_shc_recommendation(
    report_id: str,
    payload: ShcRecommendationRequest,
    access: EffectiveAccess = Depends(require(SHC_RECOMMENDATION_WRITE)),
    db: Session = Depends(get_db),
) -> dict:
    if SHC_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SHC member role required")
    query = (
        select(ShcHearing, Application)
        .join(EvcReport, EvcReport.id == ShcHearing.report_id)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == EvcVisit.application_id)
        .where(
            EvcReport.id == report_id,
            EvcReport.deficiency_present.is_(True),
            EvcVisit.status == "completed",
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    row = db.execute(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SHC hearing not found")
    hearing, application = row
    if hearing.status != "scheduled" or hearing.recommendation is not None:
        _reject_evc_action(
            db, application=application, access=access, visit_id=report_id,
            reason_code="hearing_not_open", message="hearing is not open for recommendation",
            status_code=status.HTTP_409_CONFLICT, action="shc.recommendation_rejected",
        )
    if hearing.scheduled_date > get_clock().now().date():
        _reject_evc_action(
            db, application=application, access=access, visit_id=report_id,
            reason_code="hearing_not_yet_due", message="recommendation can be recorded on or after the hearing date",
            status_code=status.HTTP_409_CONFLICT, action="shc.recommendation_rejected",
        )
    hearing.compliance_record = payload.compliance_record.strip()
    hearing.recommendation = payload.recommendation.strip()
    hearing.status = "completed"
    hearing.recorded_by = access.user_id
    hearing.recorded_at = get_clock().now()
    application.baseline_version += 1
    AuditService(db).append(
        action="shc.recommendation_recorded",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "hearing_id": hearing.id,
            "report_id": report_id,
            "status": hearing.status,
            "compliance_record_present": True,
            "recommendation_present": True,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return {
        "id": hearing.id,
        "report_id": report_id,
        "status": hearing.status,
        "recorded_at": iso(hearing.recorded_at),
    }


@router.get("/executive-committee/queue")
def executive_committee_queue(
    access: EffectiveAccess = Depends(require(EXECUTIVE_QUEUE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    if EXECUTIVE_COMMITTEE_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Executive Committee member role required")
    query = select(Application, Institution).join(
        Institution, Institution.id == Application.institution_id
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    applications = db.execute(query.order_by(Application.created_at, Application.id)).all()
    rows = []
    for application, institution in applications:
        readiness = _executive_decision_readiness(db, application)
        if readiness is None:
            continue
        transitions = db.scalars(
            select(WorkflowTransitionDefinition).where(
                WorkflowTransitionDefinition.route_key == application.route_key,
                WorkflowTransitionDefinition.from_state == application.current_state,
                WorkflowTransitionDefinition.action.in_(("approve", "reject")),
            )
        ).all()
        actions = [row.action for row in transitions if EXECUTIVE_COMMITTEE_MEMBER in row.allowed_roles]
        if not actions:
            continue
        report = db.scalar(
            select(EvcReport)
            .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
            .where(EvcVisit.application_id == application.id, EvcVisit.status == "completed")
        )
        hearing = db.scalar(
            select(ShcHearing).where(ShcHearing.report_id == report.id)
        ) if report and report.deficiency_present else None
        rows.append(
            {
                "application_id": application.id,
                "institution": institution.name,
                "current_state": application.current_state,
                "readiness": readiness,
                "report_id": report.id if report else None,
                "hearing_id": hearing.id if hearing else None,
                "summary": report.summary if report else "Nil-deficiency scrutiny record",
                "compliance_record": hearing.compliance_record if hearing else None,
                "recommendation": hearing.recommendation if hearing else None,
                "decision_actions": actions,
                "document_available": report is not None,
            }
        )
    return {
        "count": len(rows),
        "rows": rows,
    }


def _executive_decision_readiness(db: Session, application: Application) -> str | None:
    """Return a human-recorded queue basis; never infer readiness from AI findings."""
    report = db.scalar(
        select(EvcReport)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .where(EvcVisit.application_id == application.id, EvcVisit.status == "completed")
    )
    if report is not None:
        if not report.deficiency_present:
            return "nil_list"
        hearing = db.scalar(
            select(ShcHearing).where(
                ShcHearing.report_id == report.id,
                ShcHearing.status == "completed",
                ShcHearing.recommendation.is_not(None),
            )
        )
        return "shc_recommendation" if hearing else None
    result = db.scalar(
        select(ScrutinyOverallResult).where(
            ScrutinyOverallResult.application_id == application.id,
            ScrutinyOverallResult.result == "nil_deficiency",
        )
    )
    return "nil_list" if result else None


@router.post("/executive-committee/applications/{application_id}/decision")
def record_executive_decision(
    application_id: str,
    payload: ExecutiveDecisionRequest,
    access: EffectiveAccess = Depends(require(EXECUTIVE_DECISION_RECORD)),
    db: Session = Depends(get_db),
) -> dict:
    if EXECUTIVE_COMMITTEE_MEMBER not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Executive Committee member role required")
    application = require_application(db, access, application_id)
    if _executive_decision_readiness(db, application) is None:
        AuditService(db).append(
            action="executive.decision_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            reason="case has no completed human recommendation or nil-deficiency record",
            after={"outcome": payload.outcome},
            request_id=current_request_id(),
        )
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "case is not ready for an Executive Committee decision")
    order = db.get(Document, payload.speaking_order_document_id)
    if order is None or order.application_id != application.id or order.doc_type != "speaking_order":
        AuditService(db).append(
            action="executive.decision_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            reason="linked Speaking Order is missing or belongs to another application",
            after={"outcome": payload.outcome},
            request_id=current_request_id(),
        )
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "a Speaking Order for this application is required")
    if EXECUTIVE_ORDER_UPLOAD not in access.permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Speaking Order upload permission required")
    decision = workflow_service.request_transition(
        db,
        access,
        application_id,
        "approve" if payload.outcome == "approved" else "reject",
        payload.reason.strip(),
        request_id=current_request_id(),
        expected_baseline_version=payload.expected_baseline_version,
        speaking_order_document_id=order.id,
    )
    return {**decision.as_dict(), "speaking_order_document_id": order.id}


@router.get("/executive-committee/queue/{queue_item_id}/document")
def download_executive_case_report(
    queue_item_id: str,
    access: EffectiveAccess = Depends(require(EXECUTIVE_QUEUE_READ)),
    db: Session = Depends(get_db),
) -> Response:
    if EXECUTIVE_COMMITTEE_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Executive Committee member role required")
    query = (
        select(EvcReport, Application)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == EvcVisit.application_id)
        .outerjoin(ShcHearing, ShcHearing.report_id == EvcReport.id)
        .where(
            or_(
                and_(
                    ShcHearing.id == queue_item_id,
                    ShcHearing.status == "completed",
                    ShcHearing.recommendation.is_not(None),
                ),
                and_(EvcReport.id == queue_item_id, EvcReport.deficiency_present.is_(False)),
            )
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    row = db.execute(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Executive Committee item not found")
    report, application = row
    from .documents import download_document

    return download_document(
        application_id=application.id,
        document_id=report.document_id,
        access=access,
        db=db,
    )


@router.get("/shc/queue/{report_id}/document")
def download_shc_report(
    report_id: str,
    access: EffectiveAccess = Depends(require(SHC_QUEUE_READ)),
    db: Session = Depends(get_db),
) -> Response:
    if SHC_MEMBER not in access.roles and "administrator" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SHC member role required")
    query = (
        select(EvcReport, Application)
        .join(EvcVisit, EvcVisit.id == EvcReport.visit_id)
        .join(Application, Application.id == EvcVisit.application_id)
        .where(
            EvcReport.id == report_id,
            EvcReport.deficiency_present.is_(True),
            EvcVisit.status == "completed",
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    row = db.execute(query).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SHC report not found")
    report, application = row
    from .documents import download_document

    return download_document(
        application_id=application.id,
        document_id=report.document_id,
        access=access,
        db=db,
    )


@router.get("/evc/committees")
def list_committees(
    # Committee names only — no case data. The college sees them so it knows
    # who is visiting; case scoping happens on the application endpoints.
    access: EffectiveAccess = Depends(
        require_any(CASE_READ, MONITORING_READ, APPLICATION_READ)
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(Committee).order_by(Committee.name)).all()
    regions = {region.id: region for region in db.scalars(select(Region)).all()}
    return [
        {
            "id": committee.id,
            "name": committee.name,
            "kind": committee.kind,
            "region_code": regions[committee.region_id].code
            if committee.region_id in regions
            else None,
        }
        for committee in rows
    ]


@router.get("/applications/{application_id}/evc/visits")
def list_visits(
    application_id: str,
    # APPLICATION_READ: the college can see the visit booked on its own case
    # (require_application still scopes it to their own records). Booking a
    # visit still needs CASE_TRANSITION.
    access: EffectiveAccess = Depends(
        require_any(CASE_READ, MONITORING_READ, APPLICATION_READ)
    ),
    db: Session = Depends(get_db),
) -> list[dict]:
    require_application(db, access, application_id)
    rows = db.scalars(
        select(EvcVisit)
        .where(EvcVisit.application_id == application_id)
        .order_by(EvcVisit.scheduled_date.desc())
    ).all()
    names = {
        committee.id: committee.name
        for committee in db.scalars(select(Committee)).all()
    }
    return [
        _serialise(
            visit,
            names.get(visit.committee_id),
            evc_service.experts_for_visit(db, visit.id),
        )
        for visit in rows
    ]


@router.get("/applications/{application_id}/evc/committees/{committee_id}/experts")
def list_committee_experts(
    application_id: str,
    committee_id: str,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    require_application(db, access, application_id)
    committee = db.get(Committee, committee_id)
    if committee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "committee not found")
    return [
        {"id": expert.id, "name": expert.full_name}
        for expert in evc_service.available_experts(
            db,
            committee_id=committee.id,
            application_id=application_id,
        )
    ]


@router.post(
    "/applications/{application_id}/evc/visits",
    status_code=status.HTTP_201_CREATED,
)
def schedule_visit(
    application_id: str,
    payload: VisitScheduleRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    require_permission(access, CASE_TRANSITION)

    if len(set(payload.expert_user_ids)) != len(payload.expert_user_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "expert_user_ids must not contain duplicates",
        )

    venue = payload.venue.strip()
    meeting_url = payload.meeting_url.strip() if payload.meeting_url else None
    if payload.visit_mode == "physical" and not venue:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "physical visits need a place")
    if payload.visit_mode == "online" and (
        meeting_url is None or not meeting_url.startswith("https://")
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "online visits need an HTTPS meeting link",
        )
    if payload.visit_mode == "physical" and meeting_url:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "physical visits cannot include an online meeting link",
        )
    if payload.visit_mode == "online" and venue:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "online visits use a meeting link instead of a physical place",
        )

    committee = db.get(Committee, payload.committee_id) if payload.committee_id else None
    if payload.committee_id is not None and committee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "committee not found")
    if payload.expert_user_ids and committee is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "select a committee before assigning experts",
        )
    eligible_experts = (
        evc_service.available_experts(
            db,
            committee_id=committee.id,
            application_id=application.id,
        )
        if committee
        else []
    )
    eligible_ids = {expert.id for expert in eligible_experts}
    if not set(payload.expert_user_ids).issubset(eligible_ids):
        rejected = sorted(set(payload.expert_user_ids) - eligible_ids)
        AuditService(db).append(
            action="evc.visit_schedule_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            after={"reason": "expert_not_in_committee_or_conflicted", "expert_count": len(rejected)},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "one or more selected experts are not active members of this committee or have an open conflict",
        )

    # The route must actually prescribe an EVC stage.
    if "evc" not in application.route_key and "evc" not in _route_states(db, application):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "this route does not include an expert visit stage",
        )

    previous = db.scalars(
        select(EvcVisit).where(
            EvcVisit.application_id == application.id,
            EvcVisit.status == "scheduled",
        )
    ).all()
    for visit in previous:
        visit.status = "rescheduled"
        for assignment in db.scalars(
            select(CaseAssignment).where(
                CaseAssignment.source_evc_visit_id == visit.id,
                CaseAssignment.revoked_at.is_(None),
            )
        ).all():
            assignment.revoked_at = get_clock().now()

    visit = EvcVisit(
        application_id=application.id,
        committee_id=payload.committee_id,
        scheduled_date=payload.scheduled_date,
        visit_mode=payload.visit_mode,
        venue=venue,
        meeting_url=meeting_url,
        status="scheduled",
        notes=payload.notes.strip(),
        scheduled_by=access.user_id,
        created_at=get_clock().now(),
    )
    db.add(visit)
    db.flush()
    if committee is not None:
        evc_service.assign_visit_experts(
            db,
            visit=visit,
            committee=committee,
            expert_ids=payload.expert_user_ids,
        )
    names = {
        committee.id: committee.name
        for committee in db.scalars(select(Committee)).all()
    }
    AuditService(db).append(
        action="evc.visit_scheduled",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "visit_id": visit.id,
            "scheduled_date": visit.scheduled_date.isoformat(),
            "venue": visit.venue,
            "visit_mode": visit.visit_mode,
            "assigned_expert_ids": sorted(payload.expert_user_ids),
            "committee": names.get(visit.committee_id) if visit.committee_id else None,
        },
    )
    db.commit()

    # Booking the visit also moves the case when the route's schedule_evc
    # transition is available to this caller right now (right stage, right role,
    # evidence and rules met). When it is not, the booking still stands — the
    # statutory gate simply stays where it is and the officer books first.
    decision = workflow_service.auto_transition_if_available(
        db,
        access,
        application.id,
        "schedule_evc",
        reason=(
            f"Committee visit booked for {visit.scheduled_date.isoformat()}"
            + (f" at {visit.venue}" if visit.venue else "")
        ),
    )
    body = _serialise(
        visit,
        names.get(visit.committee_id),
        evc_service.experts_for_visit(db, visit.id),
    )
    body["case_advanced_to"] = decision.to_state if decision and decision.accepted else None
    return body


@router.get("/evc/calendar")
def evc_region_calendar(
    start_date: date | None = None,
    end_date: date | None = None,
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Read scheduled visits inside the caller's application/region scope."""
    from ..services.authorization_service import scope_filter

    if start_date is None and end_date is None:
        start_date = get_clock().now().date()
        end_date = start_date + timedelta(days=30)
    elif start_date is None or end_date is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "provide both start_date and end_date, or neither",
        )
    if end_date < start_date or (end_date - start_date).days > 92:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "calendar range must be ordered and no longer than 93 days",
        )

    query = (
        select(EvcVisit, Application, Institution, Region, Committee)
        .join(Application, Application.id == EvcVisit.application_id)
        .join(Institution, Institution.id == Application.institution_id)
        .join(Region, Region.id == Institution.region_id)
        .outerjoin(Committee, Committee.id == EvcVisit.committee_id)
        .where(
            EvcVisit.status == "scheduled",
            EvcVisit.scheduled_date.between(start_date, end_date),
        )
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)

    rows = db.execute(
        query.order_by(EvcVisit.scheduled_date, Institution.name, EvcVisit.id)
    ).all()
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "count": len(rows),
        "events": [
            {
                "visit_id": visit.id,
                "application_id": application.id,
                "institution": institution.name,
                "region_code": region.code,
                "scheduled_date": visit.scheduled_date.isoformat(),
                "visit_mode": visit.visit_mode,
                "venue": visit.venue,
                "meeting_url": visit.meeting_url,
                "committee_name": committee.name if committee else None,
            }
            for visit, application, institution, region, committee in rows
        ],
    }


@router.post(
    "/applications/{application_id}/evc/visits/{visit_id}/confirm"
)
def confirm_visit(
    application_id: str,
    visit_id: str,
    access: EffectiveAccess = Depends(require(EVC_VISIT_CONFIRM)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    require_permission(access, EVC_VISIT_CONFIRM)
    if "institution_representative" not in access.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "institution representative role required")
    visit = db.get(EvcVisit, visit_id)
    if visit is None or visit.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visit not found")
    if visit.status != "scheduled":
        AuditService(db).append(
            action="evc.visit_confirmation_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role="institution_representative",
            after={"visit_id": visit.id, "reason": "visit_not_scheduled"},
        )
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "only a currently scheduled visit can be confirmed",
        )
    if visit.confirmation_status != "confirmed":
        visit.confirmation_status = "confirmed"
        visit.confirmed_by = access.user_id
        visit.confirmed_at = get_clock().now()
        AuditService(db).append(
            action="evc.visit_confirmed",
            entity_type="application",
            entity_id=application.id,
            outcome="accepted",
            actor_id=access.user_id,
            actor_role="institution_representative",
            after={"visit_id": visit.id, "scheduled_date": visit.scheduled_date.isoformat()},
        )
        db.commit()
    committee = db.get(Committee, visit.committee_id) if visit.committee_id else None
    return _serialise(
        visit,
        committee.name if committee else None,
        evc_service.experts_for_visit(db, visit.id),
    )


@router.get("/evc/queue")
def evc_queue(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Cases that are at an EVC stage, or due for one, with visit ageing.

    FR-18 (plan 6.1): a case whose route prescribes an expert visit shows up
    in the queue once it reaches the state the route schedules `schedule_evc`
    from (i.e. the scrutiny leg is over for that route) — not only after
    somebody remembers to book. "Route needs EVC" is read from the route's own
    transition definitions, never inferred from the category, and the whole
    thing is derived on read: a report, never a gate, never a stored row.

    Scoped through the caller's monitoring scope like every other report.
    """
    from ..models import WorkflowTransitionDefinition
    from ..services.authorization_service import scope_filter

    now = get_clock().now()
    # Cases at an EVC stage, plus any case that already has a live appointment
    # (visits are routinely booked while scrutiny is still finishing).
    scheduled_ids = db.scalars(
        select(EvcVisit.application_id).where(EvcVisit.status == "scheduled")
    ).all()
    # ...plus cases their own route says are due for an EVC now: the route
    # defines `schedule_evc` from the case's current state and no visit is
    # booked yet (FR-18 "queue after scrutiny when the route needs it").
    evc_pairs = db.execute(
        select(
            WorkflowTransitionDefinition.route_key,
            WorkflowTransitionDefinition.from_state,
        ).where(WorkflowTransitionDefinition.action == "schedule_evc")
    ).all()
    awaiting_clause = (
        or_(
            *[
                and_(
                    Application.route_key == route_key,
                    Application.current_state == from_state,
                )
                for route_key, from_state in evc_pairs
            ]
        )
        if evc_pairs
        else false()
    )
    awaiting_ids = set(
        db.scalars(select(Application.id).where(awaiting_clause)).all()
    )
    query = select(Application).where(
        Application.current_state.in_(("evc_scheduled", "evc_completed"))
        | Application.id.in_(tuple(scheduled_ids) or ("",))
        | awaiting_clause
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    applications = db.scalars(query.order_by(Application.current_state_since)).all()

    institutions = {
        institution.id: institution
        for institution in db.scalars(select(Institution)).all()
    }
    regions = {region.id: region for region in db.scalars(select(Region)).all()}
    committees = {
        committee.id: committee.name for committee in db.scalars(select(Committee)).all()
    }

    rows = []
    for application in applications:
        visit = db.scalars(
            select(EvcVisit)
            .where(
                EvcVisit.application_id == application.id,
                EvcVisit.status == "scheduled",
            )
            .order_by(EvcVisit.scheduled_date)
        ).first()
        latest = db.scalars(
            select(EvcVisit)
            .where(EvcVisit.application_id == application.id)
            .order_by(EvcVisit.created_at.desc())
        ).first()
        institution = institutions.get(application.institution_id)
        region = regions.get(institution.region_id) if institution else None
        since = to_utc(application.current_state_since) or now
        days_in_stage = max(0, (now - since).days)
        sla = stage_sla_days(application.route_key, application.current_state)

        if visit is not None:
            days_until_visit = (visit.scheduled_date - now.date()).days
            if days_until_visit < 0:
                visit_state = "visit_overdue"
            elif days_until_visit <= 7:
                visit_state = "visit_due_soon"
            else:
                visit_state = "visit_scheduled"
        else:
            days_until_visit = None
            visit_state = "not_scheduled"

        rows.append(
            {
                "application_id": application.id,
                "institution": institution.name if institution else None,
                "region_code": region.code if region else None,
                "state": application.current_state,
                "days_in_stage": days_in_stage,
                "sla_days": sla,
                "stage_overdue": sla is not None and days_in_stage > sla,
                "awaiting_scheduling": application.id in awaiting_ids
                and visit is None,
                "visit": _serialise(
                    visit,
                    committees.get(visit.committee_id),
                    evc_service.experts_for_visit(db, visit.id),
                )
                if visit
                else None,
                "latest_visit": _serialise(
                    latest,
                    committees.get(latest.committee_id),
                    evc_service.experts_for_visit(db, latest.id),
                )
                if latest
                else None,
                "visit_state": visit_state,
                "days_until_visit": days_until_visit,
            }
        )

    return {
        "generated_at": iso(now),
        "count": len(rows),
        "not_scheduled": sum(1 for row in rows if row["visit_state"] == "not_scheduled"),
        "awaiting_scheduling": sum(1 for row in rows if row["awaiting_scheduling"]),
        "visit_due_soon": sum(1 for row in rows if row["visit_state"] == "visit_due_soon"),
        "visit_overdue": sum(1 for row in rows if row["visit_state"] == "visit_overdue"),
        "rows": rows,
    }


def _route_states(db: Session, application: Application) -> str:
    from ..models import WorkflowTransitionDefinition

    definitions = db.scalars(
        select(WorkflowTransitionDefinition).where(
            WorkflowTransitionDefinition.route_key == application.route_key
        )
    ).all()
    return " ".join(
        f"{definition.from_state} {definition.to_state}" for definition in definitions
    )
