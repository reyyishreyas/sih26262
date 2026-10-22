"""Identity, roles, permissions and scoped assignments."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, new_id, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assignments: Mapped[list["UserRoleAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_perm"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE")
    )


class UserRoleAssignment(Base):
    """Role grant, optionally narrowed to a scope (region / institution / committee).

    `scope_type='global'` is only granted to administrators. Officers never get
    implicit global read access.
    """

    __tablename__ = "user_role_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    scope_type: Mapped[str] = mapped_column(String(32), default="global")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="assignments")
    role: Mapped[Role] = relationship()


class JurisdictionAssignment(Base):
    __tablename__ = "jurisdiction_assignments"
    __table_args__ = (UniqueConstraint("user_id", "region_id", name="uq_jurisdiction"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    region_id: Mapped[str] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseAssignment(Base):
    """Explicit case/committee assignment. Membership never implies visibility."""

    __tablename__ = "case_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    committee_id: Mapped[str | None] = mapped_column(
        ForeignKey("committees.id", ondelete="CASCADE"), nullable=True
    )
    role_name: Mapped[str] = mapped_column(String(64), default="scrutiny_officer")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
