"""Rule definitions and immutable approved versions."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy import (
    inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, new_id, utcnow

RULE_STATUSES = ("draft", "approved", "retired")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024), default="")
    regulatory_reference: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list[RuleVersion]] = relationship(back_populates="rule")


class RuleVersion(Base):
    """A rule version is immutable once approved.

    The ORM-level guard below is deliberate: an approved version can be retired
    (a status flip) but its condition, applicability or metadata cannot change.
    Editing a rule means drafting a new version.
    """

    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "version", name="uq_rule_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    condition: Mapped[dict] = mapped_column(JSON, default=dict)
    # Outcome when the required evidence does not exist at all.
    missing_outcome: Mapped[str] = mapped_column(String(24), default="NOT_EVALUATED")
    # Outcome when evidence exists but has not been verified.
    unverified_outcome: Mapped[str] = mapped_column(String(24), default="NEEDS_REVIEW")
    # Outcome when the condition evaluates false.
    failure_outcome: Mapped[str] = mapped_column(String(24), default="FAIL")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(16), default="major")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rule: Mapped[Rule] = relationship(back_populates="versions")

    @property
    def label(self) -> str:
        return f"{self.rule.key}@v{self.version}"


_IMMUTABLE_FIELDS = (
    "rule_id",
    "version",
    "applicability",
    "condition",
    "missing_outcome",
    "unverified_outcome",
    "failure_outcome",
    "blocking",
    "severity",
    "effective_from",
    "effective_to",
    "content_hash",
    "notes",
)


@event.listens_for(RuleVersion, "before_update")
def _guard_approved_versions(_mapper, connection, target: RuleVersion) -> None:
    """Reject edits to an approved version. Drafting a new version is the path."""
    state = sa_inspect(target)
    changed = [
        name for name in _IMMUTABLE_FIELDS if state.attrs[name].history.has_changes()
    ]
    if not changed:
        return
    previous_status = connection.execute(
        text("SELECT status FROM rule_versions WHERE id = :id"), {"id": target.id}
    ).scalar()
    if previous_status in ("approved", "retired"):
        raise ValueError(
            "approved rule versions are immutable; draft a new version "
            f"(attempted to change {', '.join(changed)})"
        )


@event.listens_for(RuleVersion.__table__, "after_create")
def _install_rule_version_guard(_target, connection, **_kwargs) -> None:
    """Install the same guard inside the database for direct-SQL writes."""
    from ..core.db_guards import install_rule_version_guard

    install_rule_version_guard(connection)


class RuleTest(Base):
    __tablename__ = "rule_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_version_id: Mapped[str] = mapped_column(
        ForeignKey("rule_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_outcome: Mapped[str] = mapped_column(String(24))
    expected_missing_inputs: Mapped[list] = mapped_column(JSON, default=list)
