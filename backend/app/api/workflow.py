from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import APPLICATION_READ, CASE_READ, CASE_TRANSITION
from ..schemas.api import TransitionRequest
from ..services import (
    appeal,
    checklist,
    escalation,
    routing,
    scrutiny_results,
    security_deposit,
    workflow_service,
)
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application
from ..services.policy import reason_codes_policy, workflow_routes
from .deps import get_access, require, require_any

router = APIRouter(tags=["workflow"])


class RevertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = ""
    # FR-28: the undo needs a structured reason code (from
    # GET /workflow/reason-codes) alongside the free text.
    reason_code: str | None = None
    # Same optimistic-concurrency contract as TransitionRequest.
    expected_baseline_version: int | None = None


@router.get("/workflow/routes")
def list_routes(access: EffectiveAccess = Depends(get_access)) -> list[dict]:
    """Route catalogue used by the application-creation form and the review UI."""
    catalogue = workflow_routes().get("routes", {})
    return [
        {
            "key": key,
            "label": route.get("label", key),
            "states": sorted(
                {
                    transition["from_state"]
                    for transition in route.get("transitions", [])
                }
                | {
                    transition["to_state"]
                    for transition in route.get("transitions", [])
                }
            ),
        }
        for key, route in catalogue.items()
    ]


@router.get("/workflow/reason-codes")
def list_reason_codes(access: EffectiveAccess = Depends(get_access)) -> dict:
    """FR-28's structured reason-code vocabulary for returns and reverts.

    Served straight from `rules/reason_codes.json` — a clearly-labelled
    placeholder until AICTE confirms the official list (the PRD mandates a
    code but never enumerates the codes). Signed-in users only.
    """
    config = reason_codes_policy()
    return {
        "status": config.get("status"),
        "placeholder": config.get("placeholder", False),
        "source": config.get("source"),
        "codes": config.get("codes", []),
    }


@router.get("/workflow/table-2-3-scoreboard")
def table_2_3_scoreboard(
    access: EffectiveAccess = Depends(get_access),
) -> dict:
    """The 21 Table 2.3 rows, their stages, and coverage (Phase 1.9).

    A read-only scoreboard of the routing catalogue — no case data, so it
    needs only an authenticated user, not a per-case permission. Advisory
    like the rows themselves (Unverified, DEC-0003): it displays
    configuration and makes no routing decision.
    """
    return routing.scoreboard()


@router.post("/applications/{application_id}/transitions")
def request_transition(
    application_id: str,
    payload: TransitionRequest,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    decision = workflow_service.request_transition(
        db,
        access,
        application_id,
        payload.action,
        payload.reason,
        reason_code=payload.reason_code,
        request_id=current_request_id(),
        expected_baseline_version=payload.expected_baseline_version,
    )
    return decision.as_dict()


@router.post("/applications/{application_id}/revert")
def revert_last_transition(
    application_id: str,
    payload: RevertRequest,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Undo the last step on a case. The undo is itself a recorded step."""
    decision = workflow_service.revert_last_transition(
        db,
        access,
        application_id,
        payload.reason,
        reason_code=payload.reason_code,
        request_id=current_request_id(),
        expected_baseline_version=payload.expected_baseline_version,
    )
    return decision.as_dict()


@router.get("/applications/{application_id}/transitions")
def available_transitions(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    application = require_application(db, access, application_id)
    return workflow_service.available_transitions(db, access, application)


@router.get("/applications/{application_id}/escalation")
def case_escalation(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Advisory escalation view for one case (Phase 3.4).

    Serves the §11 L0–L3 chain (a labelled placeholder — §19 Q5 leaves the
    designated authority per Region open) plus this case's computed level and
    recipients: how far it is through its stage limit and whether it has been
    sitting unassigned in the queue. Read-only — it moves no case and writes
    nothing (DEC-0003).
    """
    application = require_application(db, access, application_id)
    snapshot = escalation.escalation_snapshot(db, application, get_clock().now())
    config = escalation.escalation_chain_policy()
    return {
        **snapshot,
        "source": config.get("source"),
        "chain": escalation.chain(),
    }


@router.get("/applications/{application_id}/appeal-window")
def case_appeal_window(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Advisory appeal-window view for one case (Phase 3.5, FR-27).

    Serves the 7-day appeal clock on a decision (once, within 7 days of the
    decision upload — APH cl. 2.24a) plus the day-3 / day-6 reminder cadence
    from §11 line 288, all as a clearly-labelled placeholder (§19 leaves the
    figure unverified — REG-APPEAL-001 says do not activate it as binding).
    Read-only — it moves no case and writes nothing, and there is no
    ``file_appeal`` transition or speaking-order trigger yet (those are the
    approval-gated Phase 6.5/6.6 tasks); the "may file" flag is advisory
    (DEC-0003), never a gate.
    """
    application = require_application(db, access, application_id)
    return appeal.appeal_snapshot(db, application, get_clock().now())


@router.get("/applications/{application_id}/security-deposit")
def case_security_deposit(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Advisory security-deposit view for one case (Phase 3.6, FR-33).

    Serves the 15-day proof window, the 10%/20% penalty band a given date falls
    in, and the withdrawal marker once past 31 July — all as a clearly-labelled
    placeholder (APH cl. 2.25f, PRD §7 line 244). Read-only — it moves no case
    and writes nothing, and the ``withdrawal_flagged`` marker is advisory only:
    it never withdraws a case, because an actual withdrawal is a NEW REGULATORY
    STATE (rule 15 human gate), not a config change (DEC-0003).
    """
    application = require_application(db, access, application_id)
    return security_deposit.sd_snapshot(db, application, get_clock().now())


@router.get("/applications/{application_id}/checklist")
def case_checklist(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """Annexure-2 document checklist for one case (Phase 4.2, FR-13).

    Shows which documents the case's Table 2.3 categories' Annexure-2 lists
    name and which are already uploaded, so a reviewer sees the list beside
    the files. The lists are Unverified placeholders (§19 Q8 leaves the load
    order open); only the Change of Site list is transcribed so far. Advisory
    presentation only — it never blocks, returns or rejects anything
    (DEC-0003), and a case whose categories are not recorded answers
    "needs review", never an empty all-clear.
    """
    application = require_application(db, access, application_id)
    return checklist.case_checklist(db, application)


class ScrutinyItemResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str
    item_id: str
    # "nil_deficiency" | "deficiency" — validated against the configured
    # aa_gate.scrutiny_results vocabulary (the PRD's own FR-14 wording).
    result: str
    remarks: str = ""


class ScrutinyOverallResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: str
    remarks: str = ""


@router.get("/applications/{application_id}/scrutiny-results")
def case_scrutiny_results(
    application_id: str,
    access: EffectiveAccess = Depends(require_any(CASE_READ, APPLICATION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    """The scrutiny results view for one case (Phase 4.3, FR-14).

    Joins the Annexure-2 checklist lines with the officer's recorded
    per-item and overall results (both with remarks), plus counts, a
    derived-overall answer and the FR-10 "AA" gate's advisory opinion.
    Read-only: it stores nothing and moves nothing.
    """
    application = require_application(db, access, application_id)
    return scrutiny_results.results_view(db, application)


@router.post("/applications/{application_id}/scrutiny-results")
def record_scrutiny_item_result(
    application_id: str,
    payload: ScrutinyItemResultRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """Record the officer's result for ONE checklist line, with remarks.

    Refused loudly (422) for an unknown result value, a category the case
    does not record, or an item outside that category's configured list —
    a result must never attach to a checklist line that does not exist.
    Recording is a human judgement: it never moves or gates the case
    (DEC-0003), and the audit timeline keeps every recording.
    """
    application = require_application(db, access, application_id)
    try:
        row = scrutiny_results.record_item_result(
            db,
            application,
            category_id=payload.category_id,
            item_id=payload.item_id,
            result=payload.result,
            remarks=payload.remarks,
            actor_id=access.user_id,
        )
    except KeyError as exc:  # unknown category id — configuration, not guesswork
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown category {exc.args[0]!r}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    AuditService(db).append(
        action="scrutiny.item_result_recorded",
        entity_type="scrutiny_item_result",
        entity_id=row.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.result,
        after={
            "application_id": application_id,
            "category_id": row.category_id,
            "item_id": row.item_id,
            "result": row.result,
            "remarks": row.remarks,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return {
        "category_id": row.category_id,
        "item_id": row.item_id,
        "result": row.result,
        "remarks": row.remarks,
        "recorded_by": row.recorded_by,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
    }


@router.post("/applications/{application_id}/scrutiny-results/overall")
def record_scrutiny_overall_result(
    application_id: str,
    payload: ScrutinyOverallResultRequest,
    access: EffectiveAccess = Depends(require(CASE_TRANSITION)),
    db: Session = Depends(get_db),
) -> dict:
    """Record the officer's OVERALL result for the case, with remarks.

    An overall "nil_deficiency" is refused (422) while any recorded item
    result is "deficiency" — the record cannot contradict itself. Overall
    "deficiency" is always accepted: a deficiency may exist outside the
    checklist. Recording never moves or gates the case (DEC-0003).
    """
    application = require_application(db, access, application_id)
    try:
        row = scrutiny_results.record_overall_result(
            db,
            application,
            result=payload.result,
            remarks=payload.remarks,
            actor_id=access.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    AuditService(db).append(
        action="scrutiny.overall_result_recorded",
        entity_type="scrutiny_overall_result",
        entity_id=row.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.result,
        after={
            "application_id": application_id,
            "result": row.result,
            "remarks": row.remarks,
        },
        request_id=current_request_id(),
    )
    db.commit()
    return {
        "result": row.result,
        "remarks": row.remarks,
        "recorded_by": row.recorded_by,
        "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
    }
