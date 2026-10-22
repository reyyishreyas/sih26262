from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class ApplicationCreate(BaseModel):
    institution_id: str
    category: str = Field(description="e.g. new_technical, existing_technical")
    route_key: str
    cycle: str = "2026-27"
    cycle_end: date | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    institution_id: str
    category: str
    route_key: str
    cycle: str
    cycle_end: date | None
    current_state: str
    status: str
    baseline_version: int
    assigned_officer_id: str | None


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    field_name: str
    value: Any
    source_page: int | None
    source_span: str | None
    method: str
    confidence: float
    verification_status: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    doc_type: str
    file_name: str
    file_sha256: str
    version: int
    status: str
    uploaded_at: Any
    fields: list[FieldOut] = []


class VerifyFieldRequest(BaseModel):
    verification_status: str = Field(pattern="^(verified|rejected|unverified)$")
    note: str = ""


class TransitionRequest(BaseModel):
    action: str
    reason: str = ""


class RehearsalRequest(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class UndertakingSubmitRequest(BaseModel):
    evidence_note: str = ""


class AssignmentCreate(BaseModel):
    user_id: str
    role_name: str
    scope_type: str = Field(pattern="^(global|region|institution|committee|assigned)$")
    scope_id: str | None = None
