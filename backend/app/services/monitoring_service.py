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
    EvcVisit,
    Institution,
    Region,
    RuleEvaluation,
    Undertaking,
    User,
    WorkflowTransition,
    WorkflowTransitionDefinition,
)
from .authorization_service import EffectiveAccess, scope_filter
from .compliance import report_view as compliance_report_view
from .policy import compliance_policy, stage_graph_policy, stage_limits_policy, stage_sla_days


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


def _stage_for_state(route_key: str, state: str, graph: dict[str, Any]) -> str:
    for stage in graph.get("routes", {}).get(route_key, []):
        if state in stage.get("active_states", []):
            return stage["stage_key"]
    return f"unmapped:{state}"


def _dashboard_metrics(
    db: Session,
    applications: list[Application],
    application_rows: dict[str, dict[str, Any]],
    now,
) -> dict[str, Any]:
    """Build Phase 7.2 metrics and keep every metric tied to its case rows."""
    by_id = {application.id: application for application in applications}
    app_ids = set(by_id)
    graph = stage_graph_policy()

    age_bands: dict[str, list[dict[str, Any]]] = {
        "0-7": [],
        "8-15": [],
        "16-30": [],
        "31-60": [],
        "60+": [],
    }
    for row in application_rows.values():
        age = row["age_days"]
        band = "0-7" if age <= 7 else "8-15" if age <= 15 else "16-30" if age <= 30 else "31-60" if age <= 60 else "60+"
        age_bands[band].append(row)

    overdue_rows = [
        row for row in application_rows.values() if row["deadline_state"] == "overdue"
    ]
    due_soon_rows = [
        row for row in application_rows.values() if row["deadline_state"] == "due_soon"
    ]

    def grouped_attention(key_fn) -> dict[str, dict[str, list[dict[str, Any]]]]:
        result: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for bucket, rows in (("overdue", overdue_rows), ("due_soon", due_soon_rows)):
            for row in rows:
                key = key_fn(row)
                result.setdefault(key, {"overdue": [], "due_soon": []})[bucket].append(row)
        return dict(sorted(result.items()))

    stage_by_case = {
        application.id: _stage_for_state(
            application.route_key, application.current_state, graph
        )
        for application in applications
    }
    deadline_attention = {
        "placeholder": bool(stage_limits_policy().get("placeholder", False)),
        "advisory_only": bool(stage_limits_policy().get("advisory_only", True)),
        "source": stage_limits_policy().get("source"),
        "overdue": overdue_rows,
        "due_soon": due_soon_rows,
        "by_stage": grouped_attention(
            lambda row: stage_by_case[row["application_id"]]
        ),
        "by_region": grouped_attention(lambda row: row["region"] or "not_set"),
        "by_officer": grouped_attention(
            lambda row: row["assigned_officer"] or "unassigned"
        ),
    }

    latest_visit: dict[str, EvcVisit] = {}
    visits = db.scalars(
        select(EvcVisit)
        .where(EvcVisit.application_id.in_(app_ids))
        .order_by(EvcVisit.created_at.asc())
    ).all() if app_ids else []
    for visit in visits:
        latest_visit[visit.application_id] = visit

    schedule_pairs = set(
        db.execute(
            select(
                WorkflowTransitionDefinition.route_key,
                WorkflowTransitionDefinition.from_state,
            ).where(WorkflowTransitionDefinition.action == "schedule_evc")
        ).all()
    )
    evc_status: dict[str, list[dict[str, Any]]] = {
        "queued": [],
        "scheduled": [],
        "completed": [],
        "delayed": [],
    }
    for application in applications:
        row = application_rows[application.id]
        visit = latest_visit.get(application.id)
        if visit is not None and visit.status == "scheduled":
            days_until = (visit.scheduled_date - now.date()).days
            visit_row = {**row, "scheduled_date": visit.scheduled_date.isoformat()}
            if days_until < 0:
                visit_row["days_until_visit"] = days_until
                evc_status["delayed"].append(visit_row)
            else:
                visit_row["days_until_visit"] = days_until
                evc_status["scheduled"].append(visit_row)
        elif visit is not None and visit.status == "completed":
            evc_status["completed"].append(row)
        elif (application.route_key, application.current_state) in schedule_pairs:
            evc_status["queued"].append(row)
        elif application.current_state == "evc_completed":
            evc_status["completed"].append(row)

    evc_by_mode: dict[str, list[dict[str, Any]]] = {
        "physical": [],
        "online": [],
        "unknown": [],
    }
    for application_id, visit in latest_visit.items():
        mode = visit.visit_mode if visit.visit_mode in ("physical", "online") else "unknown"
        evc_by_mode[mode].append(application_rows[application_id])

    # The reporting horizon is a presentation window, not a policy deadline.
    horizon_weeks = 8
    week_start = (now.date() - timedelta(days=now.date().weekday())) - timedelta(
        weeks=horizon_weeks - 1
    )
    transitions = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id.in_(app_ids),
            WorkflowTransition.created_at >= week_start,
            WorkflowTransition.created_at <= now,
            WorkflowTransition.reverted_at.is_(None),
            WorkflowTransition.from_state != WorkflowTransition.to_state,
        )
        .order_by(WorkflowTransition.created_at.asc())
    ).all() if app_ids else []
    throughput: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for transition in transitions:
        application = by_id.get(transition.application_id)
        if application is None:
            continue
        event_at = to_utc(transition.created_at)
        if event_at is None:
            continue
        event_week = event_at.date() - timedelta(days=event_at.date().weekday())
        stage = _stage_for_state(application.route_key, transition.from_state, graph)
        row = {
            **application_rows[application.id],
            "event_id": transition.id,
            "event_at": iso(transition.created_at),
            "week_start": event_week.isoformat(),
            "stage_key": stage,
        }
        throughput.setdefault((event_week.isoformat(), stage), []).append(row)
    throughput_rows = [
        {
            "week_start": week,
            "stage_key": stage,
            "count": len(rows),
            "rows": rows,
        }
        for (week, stage), rows in sorted(throughput.items())
    ]

    reasoned_outcomes: dict[str, list[dict[str, Any]]] = {}
    uncoded_rejections: list[dict[str, Any]] = []
    outcome_transitions = db.scalars(
        select(WorkflowTransition)
        .where(
            WorkflowTransition.application_id.in_(app_ids),
            WorkflowTransition.action.in_(
                ("return_for_clarification", "revert", "reject")
            ),
            WorkflowTransition.created_at <= now,
        )
        .order_by(WorkflowTransition.created_at.asc())
    ).all() if app_ids else []
    for transition in outcome_transitions:
        row = {
            **application_rows[transition.application_id],
            "event_id": transition.id,
            "event_at": iso(transition.created_at),
            "event_action": transition.action,
            "reason_code": transition.reason_code,
        }
        if transition.reason_code:
            reasoned_outcomes.setdefault(transition.reason_code, []).append(row)
        elif transition.action == "reject":
            uncoded_rejections.append(row)

    compliance_config_data = compliance_policy()
    compliance_rows: dict[str, list[dict[str, Any]]] = {
        "issued": [],
        "closed": [],
        "overdue": [],
    }
    for application in applications:
        report = compliance_report_view(db, application, now, include_drafts=False)
        row = application_rows[application.id]
        if report["status"] == "issued":
            compliance_rows["issued"].append(row)
            counts = report["counts"]
            if counts["closed"] > 0 and counts["open"] == 0 and counts["addressed"] == 0:
                compliance_rows["closed"].append(row)
            if report["overdue"]:
                compliance_rows["overdue"].append(row)

    return {
        "ageing_bands": age_bands,
        "throughput_by_week": {
            "window_weeks": horizon_weeks,
            "week_start": week_start.isoformat(),
            "rows": throughput_rows,
        },
        "deadline_attention": deadline_attention,
        "evc_status": evc_status,
        "evc_by_mode": evc_by_mode,
        "outcomes_by_reason_code": reasoned_outcomes,
        "rejections_without_reason_code": uncoded_rejections,
        "compliance": {
            "placeholder": bool(compliance_config_data.get("placeholder", False)),
            "advisory_only": bool(compliance_config_data.get("advisory_only", True)),
            "source": compliance_config_data.get("source"),
            "issued": compliance_rows["issued"],
            "closed": compliance_rows["closed"],
            "overdue": compliance_rows["overdue"],
        },
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

    application_rows = {
        application.id: _pendency_row(db, application, now) for application in applications
    }

    def rows_for(ids: set[str]) -> list[dict[str, Any]]:
        return [application_rows[application_id] for application_id in sorted(ids)]

    state_ids: dict[str, set[str]] = {}
    for application in applications:
        state_ids.setdefault(application.current_state, set()).add(application.id)

    overdue_obligation_cases: set[str] = set()
    upcoming_deadline_cases: set[str] = set()
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
                overdue_obligation_cases.add(undertaking.application_id)
            elif due <= now + timedelta(days=7):
                upcoming_deadline_cases.add(undertaking.application_id)

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
    scoped_visit_ids = set(
        db.scalars(
            select(EvcVisit.id).where(EvcVisit.application_id.in_(app_ids))
        ).all()
    ) if app_ids else set()

    open_alerts: list[tuple[Alert, str]] = []
    for alert in alerts:
        if alert.status == "closed":
            continue
        application_id = None
        if alert.entity_type == "application" and alert.entity_id in app_ids:
            application_id = alert.entity_id
        elif alert.entity_type == "undertaking" and alert.entity_id in scoped_undertaking_ids:
            undertaking = db.get(Undertaking, alert.entity_id)
            application_id = undertaking.application_id if undertaking else None
        elif alert.entity_type == "document" and alert.entity_id in scoped_document_ids:
            document = db.get(Document, alert.entity_id)
            application_id = document.application_id if document else None
        elif alert.entity_type == "evc_visit" and alert.entity_id in scoped_visit_ids:
            visit = db.get(EvcVisit, alert.entity_id)
            application_id = visit.application_id if visit else None
        if application_id in application_rows:
            open_alerts.append((alert, application_id))

    needs_review_ids = set(db.scalars(
        select(func.distinct(RuleEvaluation.application_id)).where(
            RuleEvaluation.application_id.in_(app_ids),
            RuleEvaluation.outcome == "NEEDS_REVIEW",
        )
    ).all()) if app_ids else set()

    assigned_ids = set(db.scalars(
        select(CaseAssignment.application_id).where(
            CaseAssignment.user_id == access.user_id,
            CaseAssignment.revoked_at.is_(None),
            CaseAssignment.application_id.in_(app_ids),
        )
    ).all()) if app_ids else set()

    open_alert_ids = {application_id for _alert, application_id in open_alerts}
    escalated_alert_ids = {
        application_id
        for alert, application_id in open_alerts
        if alert.level == "escalated"
    }
    drilldowns = {
        "cases_in_scope": rows_for(set(app_ids)),
        "cases_by_state": {state: rows_for(ids) for state, ids in state_ids.items()},
        "overdue_obligations": rows_for(overdue_obligation_cases),
        "upcoming_deadlines_7d": rows_for(upcoming_deadline_cases),
        "open_alerts": rows_for(open_alert_ids),
        "escalated_alerts": rows_for(escalated_alert_ids),
        "needs_review_cases": rows_for(needs_review_ids),
        "my_assignments": rows_for(assigned_ids),
    }

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
        "overdue_obligations": len(overdue_obligation_cases),
        "upcoming_deadlines_7d": len(upcoming_deadline_cases),
        "open_alerts": len(open_alert_ids),
        "escalated_alerts": len(escalated_alert_ids),
        "needs_review_cases": len(needs_review_ids),
        "my_assignments": len(assigned_ids),
        "drilldowns": drilldowns,
        "metrics": _dashboard_metrics(db, applications, application_rows, now),
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
        elif alert.entity_type == "evc_visit":
            from ..models import EvcVisit

            visit = db.get(EvcVisit, alert.entity_id)
            application_id = visit.application_id if visit else None
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
