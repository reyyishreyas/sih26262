from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..core.db import get_db
from ..core.pagination import PageParams, apply_page, pagination, set_total
from ..core.permissions import APPLICATION_CREATE, APPLICATION_READ, CASE_READ
from ..models import Application, Institution
from ..schemas.api import ApplicationCreate, ApplicationOut
from ..services import compliance_service, workflow_service
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    scope_filter,
)
from ..services.evidence_service import build_snapshot
from .deps import require, require_any

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    response: Response,
    page: PageParams = Depends(pagination),
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> list[Application]:
    query = select(Application).order_by(Application.created_at)
    count_query = select(func.count()).select_from(Application)
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
        count_query = count_query.where(clause)
    total = int(db.scalar(count_query) or 0)
    set_total(response, total)
    return list(db.scalars(apply_page(query, page)).all())


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    access: EffectiveAccess = Depends(require(APPLICATION_CREATE)),
    db: Session = Depends(get_db),
) -> Application:
    institution = db.get(Institution, payload.institution_id)
    if institution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "institution not found")
    if not access.global_scope and institution.id not in access.institutions:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "institution is outside your authorised scope"
        )

    application = Application(
        institution_id=institution.id,
        category=payload.category,
        route_key=payload.route_key,
        cycle=payload.cycle,
        cycle_end=payload.cycle_end,
        current_state="draft",
        status="draft",
        current_state_since=get_clock().now(),
    )
    db.add(application)
    db.flush()
    AuditService(db).append(
        action="application.created",
        entity_type="application",
        entity_id=application.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={"category": application.category, "route_key": application.route_key},
    )
    db.commit()
    db.refresh(application)
    return application


@router.get("/{application_id}")
def get_application(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    institution = db.get(Institution, application.institution_id)
    snapshot = build_snapshot(db, application)
    transitions = workflow_service.available_transitions(db, access, application)
    return {
        "application": ApplicationOut.model_validate(application).model_dump(),
        "institution": {
            "id": institution.id,
            "name": institution.name,
            "aicte_id": institution.aicte_id,
        }
        if institution
        else None,
        "state_since": iso(application.current_state_since),
        "evidence_paths": sorted(snapshot.values.get("documents", {}).keys()),
        "available_transitions": transitions,
    }


@router.get("/{application_id}/evidence")
def get_evidence(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    snapshot = build_snapshot(db, application)
    return {
        "application_id": application.id,
        "values": snapshot.values,
        "verified": snapshot.verified,
        "sources": snapshot.sources,
        "note": "Extracted values are candidates until verification_status is 'verified'.",
    }


@router.get("/{application_id}/compliance")
def get_compliance(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(APPLICATION_READ, CASE_READ)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    from ..models import RuleEvaluation

    latest = db.scalars(
        select(RuleEvaluation)
        .where(RuleEvaluation.application_id == application.id)
        .order_by(RuleEvaluation.evaluated_at.desc())
    ).first()
    # A stored batch is a snapshot. If evidence or workflow state changed since it
    # was produced, showing it would present stale findings as current.
    if (
        latest is None
        or latest.application_baseline_version != application.baseline_version
    ):
        report = compliance_service.evaluate_application(db, application, persist=True)
        db.commit()
        return report.as_dict()

    rows = db.scalars(
        select(RuleEvaluation)
        .where(
            RuleEvaluation.application_id == application.id,
            RuleEvaluation.batch_id == latest.batch_id,
        )
        .order_by(RuleEvaluation.rule_key)
    ).all()
    return {
        "application_id": application.id,
        "batch_id": latest.batch_id,
        "baseline_version": latest.application_baseline_version,
        "evaluated_at": iso(latest.evaluated_at),
        "context": "operational",
        "findings": [
            {
                "rule_key": row.rule_key,
                "rule_version": row.rule_version,
                "outcome": row.outcome,
                "explanation": row.explanation,
                "evidence_refs": row.evidence_refs,
                "missing_inputs": row.missing_inputs,
                "unverified_inputs": row.unverified_inputs,
                "title": row.title,
                "severity": row.severity,
                "regulatory_reference": row.regulatory_reference,
                "blocking": row.blocking,
            }
            for row in rows
        ],
        "counts": _counts(rows),
    }


def _counts(rows) -> dict[str, int]:
    counts = {
        "PASS": 0,
        "FAIL": 0,
        "NEEDS_REVIEW": 0,
        "NOT_APPLICABLE": 0,
        "NOT_EVALUATED": 0,
    }
    for row in rows:
        counts[row.outcome] = counts.get(row.outcome, 0) + 1
    return counts
