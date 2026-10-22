"""Route-aware workflow definitions and accepted transition history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
