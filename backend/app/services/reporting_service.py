"""Consolidated operational reports for officers and supervisors.

Every section is computed through the caller's scope filter, so a regional
officer's "overdue" list never contains another region's cases. The numbers are
counts of live records — there is no synthetic or cached figure anywhere here.

Sections:

* ``pendency``      — how many cases sit at each stage, and how old they are
* ``region``        — per-region throughput and overdue load
* ``evc``           — the expert-visit queue: booked, due soon, overdue, missing
* ``undertakings``  — follow-up tasks: open, due soon, overdue, by obligation
* ``documents``     — validity register: which evidence is expiring or expired
* ``overdue``       — everything past its deadline, in one list to work through
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso, to_utc
from ..models import (
    Alert,
    Application,
    Document,
    EvcVisit,
    ExtractedField,
    Institution,
    Region,
    Undertaking,
    User,
)
from .authorization_service import EffectiveAccess, scope_filter
from .policy import stage_sla_days


def _scoped(db: Session, access: EffectiveAccess, model):
    query = select(model)
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    return query


def _application_ids(db: Session, access: EffectiveAccess) -> list[str]:
    return list(db.scalars(_scoped(db, access, Application.id)).all())


def pendency_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    now = get_clock().now()
    applications = db.scalars(_scoped(db, access, Application)).all()

    by_state: dict[str, int] = {}
    age_sum = 0
    oldest: dict[str, Any] = None
    for application in applications:
        state = application.current_state
        by_state[state] = by_state.get(state, 0) + 1
        since = to_utc(application.current_state_since) or now
        age = max(0, (now - since).days)
        age_sum += age
        if oldest is None or age > oldest["age_days"]:
            institution = db.get(Institution, application.institution_id)
            oldest = {
                "application_id": application.id,
                "institution": institution.name if institution else None,
                "state": state,
                "age_days": age,
            }

    total = len(applications)
    return {
        "total_cases": total,
        "by_state": dict(sorted(by_state.items(), key=lambda kv: -kv[1])),
        "average_age_days": round(age_sum / total, 1) if total else 0,
        "oldest_case": oldest,
        "generated_at": iso(now),
    }


def region_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """Per-region load: how many cases, how many late, how fast they move."""
    now = get_clock().now()
    regions = db.scalars(select(Region).order_by(Region.code)).all()
    institutions = {
        institution.id: institution
        for institution in db.scalars(select(Institution)).all()
    }
    applications = db.scalars(_scoped(db, access, Application)).all()

    # Which regions the caller may see at all: derived from the cases that came
    # back through their scope, so an empty region outside scope stays hidden.
    visible_region_ids = {
        institutions[application.institution_id].region_id
        for application in applications
        if application.institution_id in institutions
    }

    rows: list[dict[str, Any]] = []
    for region in regions:
        if region.id not in visible_region_ids:
            continue
        mine = [
            application
            for application in applications
            if application.institution_id in institutions
            and institutions[application.institution_id].region_id == region.id
        ]

        overdue = 0
        age_sum = 0
        for application in mine:
            since = to_utc(application.current_state_since) or now
            age = max(0, (now - since).days)
            age_sum += age
            sla = stage_sla_days(application.route_key, application.current_state)
            if sla is not None and age > sla:
                overdue += 1

        rows.append(
            {
                "region_code": region.code,
                "region_name": region.name,
                "cases": len(mine),
                "overdue": overdue,
                "on_track": len(mine) - overdue,
                "average_age_days": round(age_sum / len(mine), 1) if mine else 0,
            }
        )
    return {"generated_at": iso(now), "regions": rows}


def evc_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """The expert-visit queue, including visits booked ahead of the stage."""
    now = get_clock().now()
    app_ids = _application_ids(db, access)

    visit_app_ids = set(
        db.scalars(select(EvcVisit.application_id).where(EvcVisit.status == "scheduled")).all()
    )
    stage_ids = set(
        db.scalars(
            select(Application.id).where(
                Application.current_state.in_(("evc_scheduled", "evc_completed"))
            )
        ).all()
    )
    relevant = (visit_app_ids | stage_ids) & set(app_ids)

    rows: list[dict[str, Any]] = []
    not_scheduled = 0
    due_soon = 0
    overdue = 0
    for application_id in sorted(relevant):
        application = db.get(Application, application_id)
        if application is None:
            continue
        institution = db.get(Institution, application.institution_id)
        visit = db.scalars(
            select(EvcVisit)
            .where(
                EvcVisit.application_id == application_id,
                EvcVisit.status == "scheduled",
            )
            .order_by(EvcVisit.scheduled_date)
        ).first()

        if visit is None:
            not_scheduled += 1
            rows.append(
                {
                    "application_id": application_id,
                    "institution": institution.name if institution else None,
                    "visit_state": "not_scheduled",
                    "scheduled_date": None,
                    "days_until_visit": None,
                }
            )
            continue

        days = (visit.scheduled_date - now.date()).days
        if days < 0:
            visit_state = "visit_overdue"
            overdue += 1
        elif days <= 7:
            visit_state = "visit_due_soon"
            due_soon += 1
        else:
            visit_state = "visit_scheduled"
        rows.append(
            {
                "application_id": application_id,
                "institution": institution.name if institution else None,
                "visit_state": visit_state,
                "scheduled_date": visit.scheduled_date.isoformat(),
                "venue": visit.venue,
                "days_until_visit": days,
            }
        )

    return {
        "generated_at": iso(now),
        "cases_needing_visit": len(rows),
        "not_scheduled": not_scheduled,
        "visit_due_soon": due_soon,
        "visit_overdue": overdue,
        "rows": rows,
    }


def undertaking_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """Follow-up tasks: what is open, what is late, and who owes it."""
    now = get_clock().now()
    app_ids = _application_ids(db, access)
    if not app_ids:
        return _empty_undertaking(now)

    undertakings = db.scalars(
        select(Undertaking).where(Undertaking.application_id.in_(app_ids))
    ).all()

    by_status: dict[str, int] = {}
    overdue = 0
    due_soon = 0
    by_obligation: dict[str, dict[str, int]] = {}
    overdue_rows: list[dict[str, Any]] = []

    for undertaking in undertakings:
        by_status[undertaking.status] = by_status.get(undertaking.status, 0) + 1
        bucket = by_obligation.setdefault(
            undertaking.obligation_key, {"total": 0, "overdue": 0, "open": 0}
        )
        bucket["total"] += 1

        if undertaking.status in ("verified", "closed", "waived"):
            continue
        bucket["open"] += 1
        due = to_utc(undertaking.due_at)
        if due is None:
            continue
        if due < now:
            overdue += 1
            bucket["overdue"] += 1
            application = db.get(Application, undertaking.application_id)
            institution = (
                db.get(Institution, application.institution_id) if application else None
            )
            overdue_rows.append(
                {
                    "undertaking_id": undertaking.id,
                    "application_id": undertaking.application_id,
                    "institution": institution.name if institution else None,
                    "title": undertaking.title,
                    "due_at": iso(undertaking.due_at),
                    "days_late": max(0, (now - due).days),
                    "status": undertaking.status,
                }
            )
        elif due <= now + timedelta(days=7):
            due_soon += 1

    overdue_rows.sort(key=lambda row: -row["days_late"])
    return {
        "generated_at": iso(now),
        "total": len(undertakings),
        "by_status": by_status,
        "open": sum(bucket["open"] for bucket in by_obligation.values()),
        "overdue": overdue,
        "due_soon": due_soon,
        "by_obligation": dict(sorted(by_obligation.items())),
        "overdue_rows": overdue_rows,
    }


def _empty_undertaking(now) -> dict[str, Any]:
    return {
        "generated_at": iso(now),
        "total": 0,
        "by_status": {},
        "open": 0,
        "overdue": 0,
        "due_soon": 0,
        "by_obligation": {},
        "overdue_rows": [],
    }


def document_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """Validity register: every dated piece of evidence, soonest expiry first."""
    now = get_clock().now()
    today = now.date()
    app_ids = _application_ids(db, access)
    if not app_ids:
        return _empty_documents(now)

    documents = db.scalars(
        select(Document).where(
            Document.application_id.in_(app_ids),
            Document.status != "rejected",
        )
    ).all()
    latest: dict[tuple[str, str], Document] = {}
    for document in sorted(documents, key=lambda d: d.uploaded_at):
        if document.application_id:
            latest[(document.application_id, document.doc_type)] = document

    rows: list[dict[str, Any]] = []
    expired = 0
    expiring_30 = 0
    expiring_60 = 0
    undated = 0

    for (application_id, doc_type), document in latest.items():
        field_row = db.scalars(
            select(ExtractedField).where(
                ExtractedField.document_id == document.id,
                ExtractedField.document_version == document.version,
                ExtractedField.field_name.in_(("valid_to", "lease_expiry")),
            )
        ).first()
        application = db.get(Application, application_id)
        institution = (
            db.get(Institution, application.institution_id) if application else None
        )

        if field_row is None or not field_row.value:
            undated += 1
            rows.append(
                {
                    "application_id": application_id,
                    "institution": institution.name if institution else None,
                    "doc_type": doc_type,
                    "file_name": document.file_name,
                    "valid_to": None,
                    "days_left": None,
                    "state": "no_date_read",
                    "verified": False,
                }
            )
            continue

        try:
            expiry = date.fromisoformat(str(field_row.value)[:10])
        except ValueError:
            undated += 1
            continue

        days_left = (expiry - today).days
        if days_left < 0:
            state = "expired"
            expired += 1
        elif days_left <= 30:
            state = "expiring_30"
            expiring_30 += 1
        elif days_left <= 60:
            state = "expiring_60"
            expiring_60 += 1
        else:
            state = "valid"
        rows.append(
            {
                "application_id": application_id,
                "institution": institution.name if institution else None,
                "doc_type": doc_type,
                "file_name": document.file_name,
                "valid_to": expiry.isoformat(),
                "days_left": days_left,
                "state": state,
                "verified": field_row.verification_status == "verified",
            }
        )

    def sort_key(row):
        # Expired first, then soonest, undated last.
        if row["valid_to"] is None:
            return (1, 0)
        return (0, row["days_left"])

    rows.sort(key=sort_key)
    return {
        "generated_at": iso(now),
        "documents_dated": len(rows) - undated,
        "expired": expired,
        "expiring_30_days": expiring_30,
        "expiring_60_days": expiring_60,
        "no_date_read": undated,
        "rows": rows,
    }


def _empty_documents(now) -> dict[str, Any]:
    return {
        "generated_at": iso(now),
        "documents_dated": 0,
        "expired": 0,
        "expiring_30_days": 0,
        "expiring_60_days": 0,
        "no_date_read": 0,
        "rows": [],
    }


def overdue_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """One list of everything late, so an officer can work top to bottom."""
    now = get_clock().now()
    items: list[dict[str, Any]] = []

    # 1. Cases sitting past their stage SLA.
    for application in db.scalars(_scoped(db, access, Application)).all():
        since = to_utc(application.current_state_since) or now
        age = max(0, (now - since).days)
        sla = stage_sla_days(application.route_key, application.current_state)
        if sla is None or age <= sla:
            continue
        institution = db.get(Institution, application.institution_id)
        items.append(
            {
                "kind": "case_overdue",
                "application_id": application.id,
                "institution": institution.name if institution else None,
                "title": f"Case waiting {age} days at this stage (limit {sla})",
                "days_late": age - sla,
            }
        )

    # 2. Late follow-up tasks.
    undertaking_rows = undertaking_report(db, access)
    for row in undertaking_rows["overdue_rows"]:
        items.append(
            {
                "kind": "undertaking_overdue",
                "application_id": row["application_id"],
                "institution": row["institution"],
                "title": row["title"],
                "days_late": row["days_late"],
            }
        )

    # 3. Expired evidence.
    document_rows = document_report(db, access)
    for row in document_rows["rows"]:
        if row["state"] != "expired":
            continue
        items.append(
            {
                "kind": "document_expired",
                "application_id": row["application_id"],
                "institution": row["institution"],
                "title": f"{row['doc_type']} expired on {row['valid_to']}",
                "days_late": abs(row["days_left"]),
            }
        )

    # 4. Visits that were due but never recorded.
    for row in evc_report(db, access)["rows"]:
        if row["visit_state"] != "visit_overdue":
            continue
        items.append(
            {
                "kind": "visit_overdue",
                "application_id": row["application_id"],
                "institution": row["institution"],
                "title": f"Committee visit was due {abs(row['days_until_visit'])} days ago",
                "days_late": abs(row["days_until_visit"]),
            }
        )

    items.sort(key=lambda item: -item["days_late"])

    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1

    return {
        "generated_at": iso(now),
        "total_overdue": len(items),
        "by_kind": by_kind,
        "open_escalated_alerts": _escalated_count(db, access),
        "items": items,
    }


def _escalated_count(db: Session, access: EffectiveAccess) -> int:
    app_ids = set(_application_ids(db, access))
    if not app_ids:
        return 0
    scoped_undertakings = set(
        db.scalars(select(Undertaking.id).where(Undertaking.application_id.in_(app_ids))).all()
    )
    scoped_documents = set(
        db.scalars(select(Document.id).where(Document.application_id.in_(app_ids))).all()
    )
    scoped_visits = set(
        db.scalars(select(EvcVisit.id).where(EvcVisit.application_id.in_(app_ids))).all()
    )
    count = 0
    for alert in db.scalars(
        select(Alert).where(Alert.level == "escalated", Alert.status != "closed")
    ).all():
        in_scope = (
            (alert.entity_type == "application" and alert.entity_id in app_ids)
            or (alert.entity_type == "undertaking" and alert.entity_id in scoped_undertakings)
            or (alert.entity_type == "document" and alert.entity_id in scoped_documents)
            or (alert.entity_type == "evc_visit" and alert.entity_id in scoped_visits)
        )
        if in_scope:
            count += 1
    return count


def officer_workload(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """How the work is distributed across the officers the caller can see."""
    now = get_clock().now()
    applications = db.scalars(_scoped(db, access, Application)).all()
    officers = {
        user.id: user
        for user in db.scalars(select(User).where(User.is_active.is_(True))).all()
    }

    rows: dict[str, dict[str, Any]] = {}
    for application in applications:
        officer_id = application.assigned_officer_id or "unassigned"
        bucket = rows.setdefault(
            officer_id,
            {"officer": None, "cases": 0, "overdue": 0, "states": {}},
        )
        bucket["cases"] += 1
        state = application.current_state
        bucket["states"][state] = bucket["states"].get(state, 0) + 1
        since = to_utc(application.current_state_since) or now
        age = max(0, (now - since).days)
        sla = stage_sla_days(application.route_key, application.current_state)
        if sla is not None and age > sla:
            bucket["overdue"] += 1

    for officer_id, bucket in rows.items():
        if officer_id == "unassigned":
            bucket["officer"] = "Not yet assigned"
        else:
            user = officers.get(officer_id)
            bucket["officer"] = user.full_name if user else officer_id

    ordered = sorted(rows.values(), key=lambda b: -b["cases"])
    return {"generated_at": iso(now), "officers": ordered}


def full_report(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """Every section in one call, so the Reports page loads in one round trip."""
    return {
        "generated_at": iso(get_clock().now()),
        "scope": {
            "type": "global" if access.global_scope else "scoped",
            "regions": sorted(access.regions),
            "institutions": sorted(access.institutions),
        },
        "pendency": pendency_report(db, access),
        "regions": region_report(db, access),
        "evc": evc_report(db, access),
        "undertakings": undertaking_report(db, access),
        "documents": document_report(db, access),
        "overdue": overdue_report(db, access),
        "workload": officer_workload(db, access),
    }
