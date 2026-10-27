"""FR-09 stage graph: derive stage rows from already-authorised moves.

PRD FR-09 (P0): "Auto-advance when authorised user marks stage complete"
(PS A), over the §7 stage list. This module keeps one ``StageInstance`` row
per PRD stage of a case, derived from ``rules/stage_graph.json`` + the
case's current state. It is called by ``workflow_service`` inside the same
transaction as every accepted transition and every revert — and by nothing
else: a refused transition changes no stage row, and nothing here moves a
case, gates a transition or bumps ``baseline_version`` (DEC-0003, PRD §0:
people decide, the system routes).

The derivation in one paragraph: the stage whose ``active_states`` contain
the case's current state becomes/stays active; stages before it that were
active are completed (the case moved on); stages after it are reset to
pending (a revert retracted them). A terminal decision (approved/rejected,
config ``terminal_states``) completes the stage it was made in and any
active stage — plus earlier stages the route *provably* passed through
(the ones without which the case could not have reached that state, a cut
set over the route's own transition graph — this is what honestly records
"readiness ran" for a seeded case whose rows were created after the fact).
Stages that never ran stay pending: a decision must never read as
"Appeal completed". Re-entry reactivates the same row (Re-Scrutiny is not
a second stage row); stint history lives in audit/workflow_transitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, to_utc
from ..models import Application, StageInstance
from .policy import stage_graph_policy as _load_graph
from .policy import stage_limits_policy, workflow_routes


def stage_graph_policy() -> dict[str, Any]:
    """The ``rules/stage_graph.json`` configuration (copied, not shared)."""
    return dict(_load_graph())


def statuses() -> tuple[str, ...]:
    """The only stage statuses a row may carry (config ``statuses``)."""
    return tuple(stage_graph_policy().get("statuses", ()))


def due_dates(db: Session, application: Application) -> list[dict[str, Any]]:
    """Per-stage due dates for one case, computed on read (Plan 3.3).

    Derived from the stage rows plus the placeholder day counts in
    ``rules/stage_limits.json`` — nothing here is stored: the row keeps
    only its stint timestamps, and the due date is start + configured
    days, exactly as the deadline sweep derives its stage-ageing clock
    (which reads the same config through ``policy.stage_sla_days``). A
    change to the day counts therefore changes every due date at once,
    with no stale column anywhere.

    Only an ACTIVE stage has a due date: the clock starts on entry and
    stops on completion, so pending and completed stages answer None.
    The count is the stage's base ``days``, except when the case sits in
    a state the stage maps differently (a held EVC visit counts 10, a
    booked one 30) — then the state override wins. Stages without a
    configured count (days: null in config) answer None with the note
    that explains why, never a guessed default. All counts are labelled
    placeholders until AICTE answers §19 Q1.
    """
    rows = {
        row.stage_key: row
        for row in db.scalars(
            select(StageInstance).where(StageInstance.application_id == application.id)
        ).all()
    }
    limits = stage_limits_policy()
    route_limits = limits.get("routes", {}).get(application.route_key, {})
    state = application.current_state

    out: list[dict[str, Any]] = []
    for entry in _route_stages(application.route_key):
        stage_key = entry["stage_key"]
        limit = route_limits.get(stage_key, {})
        row = rows.get(stage_key)
        status = row.status if row is not None else "pending"
        days: int | None = limit.get("days")
        if state in entry["active_states"]:
            days = limit.get("state_overrides", {}).get(state, days)
        due_at = None
        if (
            status == "active"
            and row is not None
            and row.started_at is not None
            and days is not None
        ):
            due_at = to_utc(row.started_at) + timedelta(days=days)
        out.append(
            {
                "id": row.id if row is not None else None,
                "stage_key": stage_key,
                "status": status,
                "days": days,
                "due_at": due_at,
                "placeholder": bool(limits.get("placeholder", False)),
                "note": limit.get("note"),
            }
        )
    return out


def _route_stages(route_key: str) -> list[dict[str, Any]]:
    """The route's ordered stage list; raises KeyError if config omits it.

    Failing loudly beats silently deriving no stages: a route that exists
    in workflow_routes.json but not in stage_graph.json is a configuration
    hole, not an empty result.
    """
    stages = stage_graph_policy()["routes"].get(route_key)
    if not stages:
        raise KeyError(
            f"stage_graph.json has no stage list for route {route_key!r} — "
            "the stage mapping is missing from configuration"
        )
    return list(stages)


def _edges(route_key: str) -> list[tuple[str, str]]:
    """The (from_state, to_state) pairs this route's transitions define."""
    definition = workflow_routes()["routes"][route_key]
    return [
        (entry["from_state"], entry["to_state"])
        for entry in definition["transitions"]
    ]


def _reachable_without(edges: list[tuple[str, str]], target: str, blocked: set[str]) -> bool:
    """Can `target` be reached from 'draft' without touching a blocked state?

    Used for the decision-time backfill: a pending earlier stage is
    completed only when the case *could not* have reached the decision
    state without passing through one of that stage's states — i.e. the
    stage provably ran even though its row was created after the fact
    (seeded cases are born mid-flow). Never the other way round: a stage
    the case could have skipped (the compliance cycle off the EVC path)
    stays pending.
    """
    graph: dict[str, set[str]] = {}
    for source, destination in edges:
        graph.setdefault(source, set()).add(destination)
    seen: set[str] = {"draft"}
    stack = ["draft"]
    while stack:
        state = stack.pop()
        for destination in graph.get(state, ()):
            if destination in blocked or destination in seen:
                continue
            if destination == target:
                return True
            seen.add(destination)
            stack.append(destination)
    return False


def _complete(row: StageInstance, actor_id: str | None, now: datetime) -> None:
    row.status = "completed"
    row.completed_at = now
    row.completed_by = actor_id


def _activate(row: StageInstance, now: datetime) -> None:
    """Enter (or re-enter) the stage: a fresh stint on the same row.

    Re-entry (Re-Scrutiny after return/resubmit, or a revert undoing a
    completion) resets the stint clock and clears the previous completion
    markers — the earlier stints stay in the audit timeline, which is
    where history belongs (the row describes the current stint only).
    An already-active row is left untouched so a re-sync is idempotent.
    """
    if row.status == "active":
        return
    row.status = "active"
    row.started_at = now
    row.completed_at = None
    row.completed_by = None


def _retract(row: StageInstance) -> None:
    """A revert put the case back before this stage: pending again.

    ``started_at`` is kept — the stint did happen, and the audit timeline
    holds why it ended; only the completion markers go, so status and
    timestamps never contradict each other.
    """
    row.status = "pending"
    row.completed_at = None
    row.completed_by = None


def sync_stage_instances(
    db: Session,
    application: Application,
    *,
    actor_id: str | None = None,
    from_state: str | None = None,
    retract: bool = False,
) -> list[StageInstance]:
    """Create/refresh this case's stage rows from config + current state.

    Runs inside the caller's transaction (accepted transitions and reverts
    only). `from_state` is the state the case moved *out of*; on a
    terminal decision it anchors the "provably entered" backfill.
    `retract` distinguishes an undo (a stage the case is pulled back from
    had its stint retracted — nothing completed it) from a forward move
    (leaving a stage — even a later one, as resubmit ends the compliance
    cycle — completes that stint). Writing nothing but the rows themselves:
    no audit event (the transition that caused this sync is already
    audited), no baseline_version bump, no state change — stage
    bookkeeping is not a case action.
    """
    graph = stage_graph_policy()
    stages_cfg = _route_stages(application.route_key)
    state = application.current_state
    now = get_clock().now()

    rows: dict[str, StageInstance] = {
        row.stage_key: row
        for row in db.scalars(
            select(StageInstance).where(
                StageInstance.application_id == application.id
            )
        ).all()
    }
    ordered: list[StageInstance] = []
    for index, entry in enumerate(stages_cfg):
        row = rows.get(entry["stage_key"])
        if row is None:
            row = StageInstance(
                application_id=application.id,
                stage_key=entry["stage_key"],
                sequence=index,
                # Explicit, not just the column default: the status is read
                # in this same call before any flush, and a None here would
                # silently skip every stage comparison below.
                status="pending",
            )
            db.add(row)
        else:
            row.sequence = index  # stay in step with the config's stage order
        ordered.append(row)

    active_index = next(
        (
            index
            for index, entry in enumerate(stages_cfg)
            if state in entry["active_states"]
        ),
        None,
    )

    if active_index is None:
        if state not in graph.get("terminal_states", ()):
            # An unmapped state (draft, or a state no stage owns — e.g.
            # 'sac_review' in evc_sac_shc, whose PRD-stage mapping is an
            # open question): the case is in no PRD stage. Change nothing
            # rather than guess an activation.
            return ordered
        _complete_on_decision(
            db,
            application,
            ordered,
            stages_cfg,
            from_state=from_state,
            actor_id=actor_id,
            now=now,
        )
        return ordered

    # A stage owns the current state: it is the live stage.
    _activate(ordered[active_index], now)
    if from_state is not None:
        source_index = next(
            (
                index
                for index, entry in enumerate(stages_cfg)
                if from_state in entry["active_states"]
            ),
            None,
        )
        if source_index is not None and source_index < active_index:
            source_row = ordered[source_index]
            if source_row.status == "pending":
                # The accepted transition itself proves this stage was entered
                # and then left, even if another configured exception route
                # means the stage is not mandatory on every path.
                _complete(source_row, actor_id, now)
    for index, row in enumerate(ordered):
        if index == active_index:
            continue
        if row.status != "active":
            continue
        if index > active_index and retract:
            # The undo pulled the case back before this stage: its stint is
            # retracted, not completed — nothing completed it.
            _retract(row)
        else:
            # Forward move: the case left this stage through a workflow
            # transition. Earlier stages were passed (Scrutiny -> EVC);
            # a later stage that was active was exited forwards (the
            # compliance cycle ends when the institution replies and the
            # case resubmits, which lands back at Readiness).
            _complete(row, actor_id, now)
    _backfill_necessary(
        db,
        application,
        ordered,
        stages_cfg,
        anchor_index=active_index,
        anchor_state=state,
        actor_id=actor_id,
        now=now,
    )
    return ordered


def _complete_on_decision(
    db: Session,
    application: Application,
    ordered: list[StageInstance],
    stages_cfg: list[dict[str, Any]],
    *,
    from_state: str | None,
    actor_id: str | None,
    now: datetime,
) -> None:
    """A terminal decision completes only what the case actually entered.

    Everything active is done (the decision closed the stint). The stage
    the decision was made in (the owner of `from_state`) is done too — a
    seeded case can reach this point with its rows created only now.
    Earlier pending stages are completed only when the route proves they
    ran (see ``_backfill_necessary``); everything after the decision stage
    stays pending: 'approved' must never read as "EVC/Appeal/Grant
    completed" when they never ran.
    """
    for row in ordered:
        if row.status == "active":
            _complete(row, actor_id, now)

    if from_state is None:
        return  # no anchor: only the active rows above are provably done
    anchor_index = next(
        (
            index
            for index, entry in enumerate(stages_cfg)
            if from_state in entry["active_states"]
        ),
        None,
    )
    if anchor_index is None:
        return  # the case came from a state no stage owns: no backfill
    _backfill_necessary(
        db,
        application,
        ordered,
        stages_cfg,
        anchor_index=anchor_index,
        anchor_state=from_state,
        actor_id=actor_id,
        now=now,
        include_anchor=True,
    )


def _backfill_necessary(
    db: Session,
    application: Application,
    ordered: list[StageInstance],
    stages_cfg: list[dict[str, Any]],
    *,
    anchor_index: int,
    anchor_state: str,
    actor_id: str | None,
    now: datetime,
    include_anchor: bool = False,
) -> None:
    """Complete pending earlier stages the route *provably* passed through.

    The rows only know about moves made since they started existing, so a
    case seeded (or first synced) mid-flow shows earlier stages as
    pending even though the case could not be where it is without having
    passed them. A pending stage before the anchor is completed only when
    blocking all of its states disconnects the anchor state from 'draft' —
    every path went through it, so it ran. A stage the case could have
    skipped (compliance cycle off the direct EVC path) is left pending:
    an unentered stage is never marked completed.

    Entry timestamps are left NULL for backfilled rows — the completion is
    recorded at decision/derivation time because the true entry time is
    not recorded anywhere; a guessed start time would be worse than none.
    """
    edges = _edges(application.route_key)
    for index, row in enumerate(ordered):
        if row.status != "pending":
            continue
        if index == anchor_index:
            if include_anchor:
                _complete(row, actor_id, now)
            continue
        if index > anchor_index:
            continue
        blocked = set(stages_cfg[index]["active_states"])
        if not blocked or _reachable_without(edges, anchor_state, blocked):
            continue  # the case could have reached the anchor without it
        _complete(row, actor_id, now)
