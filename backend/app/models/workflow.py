"""Route-aware workflow definitions and accepted transition history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class WorkflowTransitionDefinition(Base):
    """APH-derived transition table, seeded from `rules/workflow_routes.json`.

    This is data: changing a route or a guard does not require a code change.
    """

    __tablename__ = "workflow_transition_defs"
    __table_args__ = (
        UniqueConstraint("route_key", "action", name="uq_route_action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    route_key: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    from_state: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    required_permission: Mapped[str] = mapped_column(String(64), default="case.transition")
    allowed_roles: Mapped[list] = mapped_column(JSON, default=list)
    required_rules: Mapped[list] = mapped_column(JSON, default=list)
    required_documents: Mapped[list] = mapped_column(JSON, default=list)
    requires_reason: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    from_state: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    # FR-28: a return/revert carries a structured reason code from
    # rules/reason_codes.json alongside the free text, so §11's "returns by
    # reason code" metric reads data, not prose. Nullable: non-return
    # actions carry no code (FR-28 mandates it only on return/revert).
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # When an officer undid this step, the row stays but is marked, so the
    # history keeps showing what actually happened (including the undo).
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reverted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StageInstance(Base):
    """One PRD §7 stage of one case — a DERIVED record, not a decision.

    FR-09: an authorised completion auto-advances the stage list. These rows
    are where already-authorised transitions left the case, derived from
    `rules/stage_graph.json` + the case's current state by
    `services.stages.sync_stage_instances`, which runs in the same
    transaction as the transition (accepted moves only — a refused
    transition changes no row). The stage service never moves a case, never
    gates a transition and never bumps `baseline_version`: people decide,
    the system routes (DEC-0003, PRD §0).

    One row per application + stage key: re-entry (Re-Scrutiny after a
    return/resubmit) reactivates the same row rather than appending a
    duplicate; the stint history lives in the audit timeline and
    workflow_transitions, not here. Statuses are exactly
    pending|active|completed (config `statuses`) — pendency/overdue state
    is computed separately (Phase 3.3/3.4), never baked into the row.

    Stages the prototype state machine cannot reach (SHC, Appeal, Grant…)
    ship as pending rows with empty active_states in config and are never
    completed by a decision they were never part of.
    """

    __tablename__ = "stage_instances"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "stage_key", name="uq_stage_instance_stage"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    # The config stage key from stage_graph.json (readiness … grant).
    stage_key: Mapped[str] = mapped_column(String(64))
    # Position in the route's PRD §7 stage order; kept in step with config.
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    # "pending" | "active" | "completed" — validated against config by a test.
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # When the case first entered this stage on the current stint; None while
    # pending. A re-entry resets the clock (audit keeps earlier stints).
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Who moved the case out of this stage (the authorised actor of the
    # completing transition); None while pending/active.
    completed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
