"""Expert Visit Committee scheduling and the EVC queue.

Scheduling records *when* and *where* a visit happens and feeds the queue and
timeline reports plus the deadline sweep (visits that were due but never
recorded). When a booking is made and the route's `schedule_evc` transition is
available to the caller — right state, right role, evidence and rules met — the
case moves to the committee stage with the booking instead of waiting for a
second click; otherwise the statutory gate stays exactly where it is.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..core.db import get_db
from ..core.permissions import (
    APPLICATION_READ,
    CASE_READ,
    CASE_TRANSITION,
    MONITORING_READ,
)
from ..models import Application, Committee, EvcVisit, Institution, Region
from ..services import workflow_service
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
)
from ..services.policy import stage_sla_days
from .deps import require, require_any

router = APIRouter(tags=["evc"])


class VisitScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_date: date
    venue: str = Field(default="", max_length=255)
    committee_id: str | None = None
    notes: str = Field(default="", max_length=1024)


def _serialise(visit: EvcVisit, committee_name: str | None) -> dict:
    return {
        "id": visit.id,
        "application_id": visit.application_id,
        "committee_id": visit.committee_id,
        "committee_name": committee_name,
        "scheduled_date": visit.scheduled_date.isoformat(),
        "venue": visit.venue,
        "status": visit.status,
        "notes": visit.notes,
        "created_at": iso(visit.created_at),
        "completed_at": iso(visit.completed_at),
    }


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
        _serialise(visit, names.get(visit.committee_id)) for visit in rows
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

    if payload.committee_id is not None and db.get(Committee, payload.committee_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "committee not found")

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

    visit = EvcVisit(
        application_id=application.id,
        committee_id=payload.committee_id,
        scheduled_date=payload.scheduled_date,
        venue=payload.venue.strip(),
        status="scheduled",
        notes=payload.notes.strip(),
        scheduled_by=access.user_id,
        created_at=get_clock().now(),
    )
    db.add(visit)
    db.flush()
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
    body = _serialise(visit, names.get(visit.committee_id))
    body["case_advanced_to"] = decision.to_state if decision and decision.accepted else None
    return body


@router.get("/evc/queue")
def evc_queue(
    access: EffectiveAccess = Depends(require(MONITORING_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Cases that are at an EVC stage, with visit scheduling and ageing.

    Scoped through the caller's monitoring scope like every other report.
    """
    from ..services.authorization_service import scope_filter

    now = get_clock().now()
    # Cases at an EVC stage, plus any case that already has a live appointment
    # (visits are routinely booked while scrutiny is still finishing).
    scheduled_ids = db.scalars(
        select(EvcVisit.application_id).where(EvcVisit.status == "scheduled")
    ).all()
    query = select(Application).where(
        Application.current_state.in_(("evc_scheduled", "evc_completed"))
        | Application.id.in_(tuple(scheduled_ids) or ("",))
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
                "visit": _serialise(visit, committees.get(visit.committee_id))
                if visit
                else None,
                "latest_visit": _serialise(latest, committees.get(latest.committee_id))
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
