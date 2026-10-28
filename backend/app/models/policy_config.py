"""Immutable snapshots used by the four-eyes policy configuration console."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_id, utcnow


class PolicyConfigVersion(Base):
    __tablename__ = "policy_config_versions"
    __table_args__ = (
        UniqueConstraint("policy_key", "version", name="uq_policy_config_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    policy_key: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(512), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(PolicyConfigVersion, "before_update")
def _freeze_approved_snapshot(_mapper, connection, target: PolicyConfigVersion) -> None:
    state = inspect(target)
    immutable = ("policy_key", "version", "content", "content_hash", "summary", "created_by")
    if not any(state.attrs[name].history.has_changes() for name in immutable):
        return
    status = connection.execute(
        text("SELECT status FROM policy_config_versions WHERE id = :id"),
        {"id": target.id},
    ).scalar()
    if status == "approved":
        raise ValueError("approved policy snapshots are immutable")


@event.listens_for(PolicyConfigVersion, "before_delete")
def _preserve_approved_snapshot(_mapper, connection, target: PolicyConfigVersion) -> None:
    status = connection.execute(
        text("SELECT status FROM policy_config_versions WHERE id = :id"),
        {"id": target.id},
    ).scalar()
    if status == "approved":
        raise ValueError("approved policy snapshots cannot be deleted")
