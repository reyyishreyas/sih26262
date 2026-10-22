"""Role-scoped monitoring.

Every number here is computed from records through the caller's scope filter. The
same filter feeds the dashboard total and the drill-down list, so they reconcile by
construction rather than by coincidence.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..models import (
    Alert,
    Application,
    CaseAssignment,
    Document,
    Institution,
    Region,
    RuleEvaluation,
    Undertaking,
    User,
)
from .authorization_service import EffectiveAccess, scope_filter
from .policy import stage_sla_days


def _scoped_application_ids(db: Session, access: EffectiveAccess):
    clause = scope_filter(access)
    query = select(Application.id)
    if clause is not None:
        query = query.where(clause)
    return query


def _scoped_applications(db: Session, access: EffectiveAccess):
    clause = scope_filter(access)
    query = select(Application)
    if clause is not None:
        query = query.where(clause)
    return query


def _pendency_row(db: Session, application: Application, now) -> dict[str, Any]:
    institution = db.get(Institution, application.institution_id)
    region = db.get(Region, institution.region_id) if institution else None
    officer = db.get(User, application.assigned_officer_id) if application.assigned_officer_id else None
    since = to_utc(application.current_state_since) or now
    age_days = max(0, (now - since).days)
    sla = stage_sla_days(application.route_key, application.current_state)
    if sla is None:
        deadline_state = "not_configured"
        days_remaining = None
    else:
        days_remaining = sla - age_days
        if days_remaining < 0:
            deadline_state = "overdue"
        elif days_remaining <= 2:
            deadline_state = "due_soon"
        else:
            deadline_state = "on_track"

    next_undertaking = db.scalars(
        select(Undertaking)
        .where(
            Undertaking.application_id == application.id,
            Undertaking.status.in_(("pending", "submitted")),
        )
        .order_by(Undertaking.due_at.asc())
    ).first()

    return {
        "application_id": application.id,
        "institution": institution.name if institution else None,
        "region": region.code if region else None,
        "category": application.category,
        "route_key": application.route_key,
        "state": application.current_state,
        "age_days": age_days,
        "sla_days": sla,
        "days_remaining": days_remaining,
        "deadline_state": deadline_state,
        "assigned_officer": officer.full_name if officer else None,
        "next_undertaking_due": iso(next_undertaking.due_at) if next_undertaking else None,
    }


def dashboard(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    now = get_clock().now()
    clause = scope_filter(access)

    apps_query = select(Application)
    if clause is not None:
        apps_query = apps_query.where(clause)
    applications = db.scalars(apps_query).all()
    app_ids = [application.id for application in applications]

    by_state: dict[str, int] = {}
    for application in applications:
        by_state[application.current_state] = by_state.get(application.current_state, 0) + 1

    overdue_obligations = 0
    upcoming = 0
    if app_ids:
        undertakings = db.scalars(
            select(Undertaking).where(
                Undertaking.application_id.in_(app_ids),
                Undertaking.status.in_(("pending", "submitted")),
            )
        ).all()
        for undertaking in undertakings:
            due = to_utc(undertaking.due_at)
            if due is None:
                continue
            if due < now:
                overdue_obligations += 1
            elif due <= now + timedelta(days=7):
                upcoming += 1

    alerts = db.scalars(select(Alert)).all()
    scoped_undertaking_ids = set(
        db.scalars(
            select(Undertaking.id).where(Undertaking.application_id.in_(app_ids))
        ).all()
    ) if app_ids else set()
    scoped_document_ids = set(
        db.scalars(
            select(Document.id).where(Document.application_id.in_(app_ids))
        ).all()
    ) if app_ids else set()

    open_alerts = [
        alert
        for alert in alerts
        if alert.status != "closed"
        and (
            (alert.entity_type == "application" and alert.entity_id in set(app_ids))
            or (alert.entity_type == "undertaking" and alert.entity_id in scoped_undertaking_ids)
            or (alert.entity_type == "document" and alert.entity_id in scoped_document_ids)
        )
    ]

    assigned = db.scalars(
        select(CaseAssignment).where(
            CaseAssignment.user_id == access.user_id,
            CaseAssignment.revoked_at.is_(None),
        )
    ).all()

    needs_review_cases = db.scalar(
        select(func.count(func.distinct(RuleEvaluation.application_id))).where(
            RuleEvaluation.application_id.in_(app_ids),
            RuleEvaluation.outcome == "NEEDS_REVIEW",
        )
    ) if app_ids else 0

    return {
        "role": access.primary_role,
        "roles": access.roles,
        "scope": {
            "type": "global" if access.global_scope else "scoped",
            "regions": sorted(access.regions),
            "institutions": sorted(access.institutions),
            "committees": sorted(access.committees),
            "assigned_cases_only": access.assigned_cases_only,
        },
        "cases_in_scope": len(applications),
        "cases_by_state": by_state,
        "overdue_obligations": overdue_obligations,
        "upcoming_deadlines_7d": upcoming,
        "open_alerts": len(open_alerts),
        "escalated_alerts": len([a for a in open_alerts if a.level == "escalated"]),
        "needs_review_cases": needs_review_cases,
        "my_assignments": len(assigned),
        "generated_at": iso(now),
        "data_source": "live records, no synthetic counts",
    }


def pendency(
    db: Session,
    access: EffectiveAccess,
    *,
    state: str | None = None,
    region_code: str | None = None,
    officer_id: str | None = None,
) -> list[dict[str, Any]]:
    """Filters are applied *on top of* the scope filter, never instead of it."""
    now = get_clock().now()
    query = _scoped_applications(db, access)
    if state:
        query = query.where(Application.current_state == state)
    if officer_id:
        query = query.where(Application.assigned_officer_id == officer_id)
    applications = db.scalars(query.order_by(Application.current_state_since.asc())).all()

    rows = [_pendency_row(db, application, now) for application in applications]
    if region_code:
        rows = [row for row in rows if row["region"] == region_code]
    return sorted(rows, key=lambda row: row["age_days"], reverse=True)


def ageing(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    now = get_clock().now()
    applications = db.scalars(_scoped_applications(db, access)).all()
    bands = {"0-7": 0, "8-15": 0, "16-30": 0, "31-60": 0, "60+": 0}
    for application in applications:
        since = to_utc(application.current_state_since) or now
        age = max(0, (now - since).days)
        if age <= 7:
            bands["0-7"] += 1
        elif age <= 15:
            bands["8-15"] += 1
        elif age <= 30:
            bands["16-30"] += 1
        elif age <= 60:
            bands["31-60"] += 1
        else:
            bands["60+"] += 1
    return {"total": len(applications), "bands": bands}


def escalations(db: Session, access: EffectiveAccess, limit: int = 100) -> list[dict[str, Any]]:
    scoped_ids = set(db.scalars(_scoped_application_ids(db, access)).all())
    rows = db.scalars(
        select(Alert)
        .where(Alert.level == "escalated")
        .order_by(Alert.fired_at.desc())
        .limit(limit)
    ).all()
    out = []
    for alert in rows:
        application_id = None
        if alert.entity_type == "application":
            application_id = alert.entity_id
        elif alert.entity_type == "undertaking":
            undertaking = db.get(Undertaking, alert.entity_id)
            application_id = undertaking.application_id if undertaking else None
        elif alert.entity_type == "document":
            document = db.get(Document, alert.entity_id)
            application_id = document.application_id if document else None
        if application_id not in scoped_ids:
            continue
        out.append(
            {
                "alert_id": alert.id,
                "application_id": application_id,
                "alert_type": alert.alert_type,
                "level": alert.level,
                "due_at": iso(alert.due_at),
                "fired_at": iso(alert.fired_at),
                "status": alert.status,
                "recipients": alert.recipients,
                "payload": alert.payload,
            }
        )
    return out


def assignments(db: Session, access: EffectiveAccess) -> list[dict[str, Any]]:
    now = get_clock().now()
    rows = db.scalars(
        select(CaseAssignment).where(
            CaseAssignment.user_id == access.user_id,
            CaseAssignment.revoked_at.is_(None),
        )
    ).all()
    out = []
    for assignment in rows:
        application = db.get(Application, assignment.application_id)
        if application is None:
            continue
        out.append(
            {
                "application_id": application.id,
                "role": assignment.role_name,
                "assigned_at": iso(assignment.assigned_at),
                "pendency": _pendency_row(db, application, now),
            }
        )
    return out
