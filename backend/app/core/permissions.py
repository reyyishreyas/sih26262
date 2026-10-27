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
SHC_HEARING_SCHEDULE = "shc.hearing.schedule"
SHC_RECOMMENDATION_WRITE = "shc.recommendation.write"
EXECUTIVE_QUEUE_READ = "executive.queue.read"
EXECUTIVE_ORDER_UPLOAD = "executive.order.upload"
EXECUTIVE_DECISION_RECORD = "executive.decision.record"
APPEAL_SUBMIT = "appeal.submit"
SAC_APPEAL_READ = "sac.appeal.read"
SAC_APPEAL_MANAGE = "sac.appeal.manage"
COUNCIL_APPEAL_READ = "council.appeal.read"
COUNCIL_DECISION_RECORD = "council.decision.record"
COUNCIL_ORDER_UPLOAD = "council.order.upload"
REOPENING_REQUEST = "reopening.request"
REOPENING_REVIEW = "reopening.review"

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
    SHC_HEARING_SCHEDULE: "Schedule SHC hearings for referred reports",
    SHC_RECOMMENDATION_WRITE: "Record SHC compliance notes and recommendations",
    EXECUTIVE_QUEUE_READ: "Read completed SHC recommendations awaiting decision",
    EXECUTIVE_ORDER_UPLOAD: "Upload a Speaking Order document",
    EXECUTIVE_DECISION_RECORD: "Record an Executive Committee decision",
    APPEAL_SUBMIT: "Submit an institution appeal against an Executive Committee decision",
    SAC_APPEAL_READ: "Read appeal records within SAC assignment scope",
    SAC_APPEAL_MANAGE: "Schedule appeal hearings and record SAC recommendations",
    COUNCIL_APPEAL_READ: "Read appeals and SAC recommendations within Council scope",
    COUNCIL_DECISION_RECORD: "Record the final Council decision on an appeal",
    COUNCIL_ORDER_UPLOAD: "Upload the portal copy of a Council final decision",
    REOPENING_REQUEST: "Request the one-time reopening of a wrongly submitted application",
    REOPENING_REVIEW: "Review reopening requests and verify required payment evidence",
}

INSTITUTION_REPRESENTATIVE = "institution_representative"
SCRUTINY_OFFICER = "scrutiny_officer"
REGIONAL_OFFICER = "regional_officer"
EVC_MEMBER = "evc_member"
COMPETENT_AUTHORITY = "competent_authority"
SHC_MEMBER = "shc_member"
EXECUTIVE_COMMITTEE_MEMBER = "executive_committee_member"
SAC_MEMBER = "sac_member"
COUNCIL_MEMBER = "council_member"
SUPERVISORY_OFFICER = "supervisory_officer"
ADMINISTRATOR = "administrator"

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    INSTITUTION_REPRESENTATIVE: (
        APPLICATION_READ,
        APPLICATION_CREATE,
        APPLICATION_SUBMIT,
        REOPENING_REQUEST,
        DOCUMENT_READ,
        DOCUMENT_UPLOAD,
        COMPLIANCE_EVALUATE,
        REHEARSAL_RUN,
        AUDIT_READ,
        UNDERTAKING_READ,
        UNDERTAKING_SUBMIT,
        EVC_VISIT_CONFIRM,
        APPEAL_SUBMIT,
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
    COMPETENT_AUTHORITY: (FRAUD_REFERRAL_READ, REOPENING_REVIEW, AUDIT_READ),
    SHC_MEMBER: (
        SHC_QUEUE_READ,
        SHC_HEARING_SCHEDULE,
        SHC_RECOMMENDATION_WRITE,
        AUDIT_READ,
    ),
    EXECUTIVE_COMMITTEE_MEMBER: (
        EXECUTIVE_QUEUE_READ,
        EXECUTIVE_ORDER_UPLOAD,
        EXECUTIVE_DECISION_RECORD,
        AUDIT_READ,
    ),
    SAC_MEMBER: (SAC_APPEAL_READ, SAC_APPEAL_MANAGE, AUDIT_READ),
    COUNCIL_MEMBER: (COUNCIL_APPEAL_READ, COUNCIL_DECISION_RECORD, COUNCIL_ORDER_UPLOAD, AUDIT_READ),
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
        if permission
        not in (
            EVC_VISIT_CONFIRM,
            EXECUTIVE_ORDER_UPLOAD,
            EXECUTIVE_DECISION_RECORD,
            APPEAL_SUBMIT,
            SAC_APPEAL_READ,
            SAC_APPEAL_MANAGE,
            COUNCIL_APPEAL_READ,
            COUNCIL_DECISION_RECORD,
            COUNCIL_ORDER_UPLOAD,
            REOPENING_REQUEST,
            REOPENING_REVIEW,
        )
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
    EXECUTIVE_COMMITTEE_MEMBER: SCOPE_REGION,
    SAC_MEMBER: SCOPE_REGION,
    COUNCIL_MEMBER: SCOPE_GLOBAL,
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
