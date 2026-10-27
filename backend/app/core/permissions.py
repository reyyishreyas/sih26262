"""Permission catalogue and the role -> permission matrix.

Hiding a control in React is not security. Every permission below is checked on the
server, and scope (which institutions/regions/cases) is checked separately.
"""

from __future__ import annotations

from dataclasses import dataclass

APPLICATION_READ = "application.read"
APPLICATION_CREATE = "application.create"
APPLICATION_SUBMIT = "application.submit"
CASE_READ = "case.read"
CASE_TRANSITION = "case.transition"
CASE_DECIDE = "case.decide"
DOCUMENT_READ = "document.read"
DOCUMENT_UPLOAD = "document.upload"
EVC_REPORT_UPLOAD = "evc.report.upload"
DOCUMENT_VERIFY = "document.verify"
COMPLIANCE_EVALUATE = "compliance.evaluate"
REHEARSAL_RUN = "rehearsal.run"
AUDIT_READ = "audit.read"
MONITORING_READ = "monitoring.read"
UNDERTAKING_READ = "undertaking.read"
UNDERTAKING_SUBMIT = "undertaking.submit"
ADMIN_USERS = "admin.users"
ADMIN_RULES = "admin.rules"
ADMIN_ASSIGNMENTS = "admin.assignments"
ALERT_DELIVER = "alert.deliver"
EVC_VISIT_CONFIRM = "evc.visit.confirm"
FRAUD_REFERRAL_READ = "fraud.referral.read"
SHC_QUEUE_READ = "shc.queue.read"

ALL_PERMISSIONS: dict[str, str] = {
    APPLICATION_READ: "Read applications within scope",
    APPLICATION_CREATE: "Create an application draft",
    APPLICATION_SUBMIT: "Submit an application for scrutiny",
    CASE_READ: "Read a case, its evidence and findings",
    CASE_TRANSITION: "Request a workflow transition",
    CASE_DECIDE: "Record a committee or authority decision",
    DOCUMENT_READ: "Read documents within scope",
    DOCUMENT_UPLOAD: "Upload document versions",
    EVC_REPORT_UPLOAD: "Upload a report for an assigned EVC visit",
    DOCUMENT_VERIFY: "Verify or correct extracted fields",
    COMPLIANCE_EVALUATE: "Run the compliance rule engine",
    REHEARSAL_RUN: "Run an isolated Approval Rehearsal",
    AUDIT_READ: "Read the audit timeline",
    MONITORING_READ: "Read pendency/ageing monitoring data",
    UNDERTAKING_READ: "Read undertakings and obligations",
    UNDERTAKING_SUBMIT: "Submit undertaking evidence",
    ADMIN_USERS: "Administer users",
    ADMIN_RULES: "Administer rule versions",
    ADMIN_ASSIGNMENTS: "Administer roles and scopes",
    ALERT_DELIVER: "Run scheduled alert delivery",
    EVC_VISIT_CONFIRM: "Confirm a scheduled EVC visit for an institution",
    FRAUD_REFERRAL_READ: "Review fraud referrals within authority scope",
    SHC_QUEUE_READ: "Read SHC cases referred after an EVC deficiency report",
}

INSTITUTION_REPRESENTATIVE = "institution_representative"
SCRUTINY_OFFICER = "scrutiny_officer"
REGIONAL_OFFICER = "regional_officer"
EVC_MEMBER = "evc_member"
COMPETENT_AUTHORITY = "competent_authority"
SHC_MEMBER = "shc_member"
SUPERVISORY_OFFICER = "supervisory_officer"
ADMINISTRATOR = "administrator"

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    INSTITUTION_REPRESENTATIVE: (
        APPLICATION_READ,
        APPLICATION_CREATE,
        APPLICATION_SUBMIT,
        DOCUMENT_READ,
        DOCUMENT_UPLOAD,
        COMPLIANCE_EVALUATE,
        REHEARSAL_RUN,
        AUDIT_READ,
        UNDERTAKING_READ,
        UNDERTAKING_SUBMIT,
        EVC_VISIT_CONFIRM,
    ),
    SCRUTINY_OFFICER: (
        CASE_READ,
        CASE_TRANSITION,
        DOCUMENT_READ,
        DOCUMENT_VERIFY,
        COMPLIANCE_EVALUATE,
        REHEARSAL_RUN,
        AUDIT_READ,
        UNDERTAKING_READ,
        MONITORING_READ,
    ),
    REGIONAL_OFFICER: (
        CASE_READ,
        CASE_TRANSITION,
        DOCUMENT_READ,
        COMPLIANCE_EVALUATE,
        REHEARSAL_RUN,
        AUDIT_READ,
        MONITORING_READ,
        UNDERTAKING_READ,
    ),
    EVC_MEMBER: (
        CASE_READ,
        CASE_DECIDE,
        DOCUMENT_READ,
        EVC_REPORT_UPLOAD,
        AUDIT_READ,
        UNDERTAKING_READ,
    ),
    COMPETENT_AUTHORITY: (FRAUD_REFERRAL_READ, AUDIT_READ),
    SHC_MEMBER: (SHC_QUEUE_READ, AUDIT_READ),
    SUPERVISORY_OFFICER: (
        MONITORING_READ,
        CASE_READ,
        DOCUMENT_READ,
        AUDIT_READ,
        UNDERTAKING_READ,
    ),
    ADMINISTRATOR: tuple(
        permission
        for permission in ALL_PERMISSIONS
        if permission != EVC_VISIT_CONFIRM
    ),
}

SCOPE_GLOBAL = "global"
SCOPE_REGION = "region"
SCOPE_INSTITUTION = "institution"
SCOPE_COMMITTEE = "committee"
SCOPE_ASSIGNED = "assigned"

ROLE_DEFAULT_SCOPE: dict[str, str] = {
    INSTITUTION_REPRESENTATIVE: SCOPE_INSTITUTION,
    SCRUTINY_OFFICER: SCOPE_ASSIGNED,
    REGIONAL_OFFICER: SCOPE_REGION,
    EVC_MEMBER: SCOPE_COMMITTEE,
    COMPETENT_AUTHORITY: SCOPE_REGION,
    SHC_MEMBER: SCOPE_REGION,
    SUPERVISORY_OFFICER: SCOPE_REGION,
    ADMINISTRATOR: SCOPE_GLOBAL,
}


@dataclass(frozen=True)
class PermissionCheck:
    allowed: bool
    reason: str = ""


class PermissionDenied(Exception):
    def __init__(self, message: str, *, code: str = "forbidden") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
