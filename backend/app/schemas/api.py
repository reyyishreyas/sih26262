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
    upload_reason: str | None = None
    status: str
    uploaded_at: Any
    fields: list[FieldOut] = []


class VerifyFieldRequest(BaseModel):
    verification_status: str = Field(pattern="^(verified|rejected|unverified)$")
    note: str = ""


class TransitionRequest(BaseModel):
    action: str
    reason: str = ""
    # Optimistic concurrency (Essentials §14a): when the client sends the
    # baseline_version it loaded, a case that has moved underneath it is
    # rejected with a reload message instead of acted on from a stale view.
    # Optional so existing clients keep working; the UI adopts it separately.
    expected_baseline_version: int | None = None


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


class DeficiencyCreate(BaseModel):
    document_id: str | None = None
    extracted_field_id: str | None = None
    category: str = "document_deficiency"
    rule_key: str | None = None
    field_name: str | None = None
    extracted_value: Any = None
    explanation: str = Field(min_length=1)
    corrective_action: str = Field(min_length=1)
    status: str = Field(default="open", pattern="^(draft|open)$")


class DeficiencyUpdate(BaseModel):
    explanation: str | None = None
    corrective_action: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|open|addressed|closed)$")
    resolution_note: str | None = None


class DeficiencyCloseRequest(BaseModel):
    resolution_note: str = ""


class DeficiencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    document_id: str | None
    extracted_field_id: str | None
    category: str
    rule_key: str | None
    field_name: str | None
    extracted_value: Any
    explanation: str
    corrective_action: str
    status: str
    created_by: str
    created_at: Any
    resolved_by: str | None
    resolved_at: Any
    resolution_note: str | None
    corrective_document_id: str | None


class BlockedFlagDecision(BaseModel):
    """An officer's PRD §7 decision on one FR-03 flag: clear or hold.

    The pattern is the whole point: the vocabulary has no ``rejected`` (an
    Unverified flag never rejects — PRD §0, plan 2.2), so recording one is a
    422 before it can reach the database. The same two values are pinned in
    ``readiness_policy.json -> blocked_flags.decisions`` by a test.
    """

    decision: str = Field(pattern="^(cleared|held)$")
    note: str = ""


class BlockedFlagOut(BaseModel):
    """One FR-03 flag as the endpoint returns it: configuration + evaluation
    + the officer's decision if one exists (otherwise None)."""

    flag_id: str
    rule: str
    clause: str
    source: str
    status: str
    advisory_only: bool
    evaluation: str
    reason: str
    missing_inputs: list[str]
    decision: str | None
    decided_by: str | None
    decided_at: Any = None
    note: str | None
    state: str


class LeaseCheckOut(BaseModel):
    """FR-05 / RULE-LEASE-01 lease-years computation (advisory, read-only).

    ``evaluation`` is three-valued (sufficient | insufficient | needs_review)
    and the configuration the answer was derived from is echoed inline, so an
    officer sees the duration actually on file (null today) alongside the
    computed years. No request body exists: the check is a GET.
    """

    rule_id: str
    rule: str
    clause: str
    source: str
    status: str
    advisory_only: bool
    valid_to: str | None
    as_of: str
    verified: bool
    remaining_years: float | None
    longest_course_duration_years: int | None
    extension_years: int | None
    extension_on_file: bool | None
    comparison: str
    evaluation: str
    reason: str
    missing_inputs: list[str]


class PortalDocumentBrief(BaseModel):
    """One document as the FR-01 feed lists it (contents are not embedded)."""

    doc_type: str
    file_name: str
    version: int
    status: str


class PortalFeedRecord(BaseModel):
    """One final-submitted case in the PRD's FR-01 field order.

    ``pid``/``institution_type``/``ter_status`` are served as null: this
    repo records no such data, and a stub that guessed them would be worse
    than one that admits the gap (``rules/portal_feed.json -> fields``).
    """

    application_id: str
    pid: str | None
    category: str
    institution_type: str | None
    submission_time: str | None
    ter_status: str | None
    documents: list[PortalDocumentBrief]


class PortalFeedOut(BaseModel):
    """The stubbed portal feed envelope: identity, "as of" stamp, records."""

    source: str
    as_of: str
    status: str
    advisory_only: bool
    sync_cadence: str | None
    records: list[PortalFeedRecord]

