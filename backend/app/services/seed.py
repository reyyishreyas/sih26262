"""Synthetic demo dataset.

Every record here is fictional. The dataset is deterministic for a given clock so the
demo and the tests see the same case.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.permissions import (
    ADMINISTRATOR,
    ALL_PERMISSIONS,
    COMPETENT_AUTHORITY,
    COUNCIL_MEMBER,
    EVC_MEMBER,
    INSTITUTION_REPRESENTATIVE,
    REGIONAL_OFFICER,
    ROLE_PERMISSIONS,
    SAC_MEMBER,
    SCRUTINY_OFFICER,
    SUPERVISORY_OFFICER,
)
from ..core.security import hash_password
from ..models import (
    Application,
    Committee,
    Document,
    ExtractedField,
    Institution,
    JurisdictionAssignment,
    Permission,
    Region,
    Role,
    RolePermission,
    Rule,
    RuleVersion,
    Undertaking,
    User,
    UserRoleAssignment,
    WorkflowTransition,
    WorkflowTransitionDefinition,
)
from .audit_service import AuditService
from .policy import compliance_rules, workflow_routes

DEMO_PASSWORD = "DemoPassw0rd!"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_or_create(db: Session, model, defaults: dict | None = None, **lookup):
    instance = db.scalars(select(model).filter_by(**lookup)).first()
    if instance is not None:
        return instance, False
    instance = model(**lookup, **(defaults or {}))
    db.add(instance)
    db.flush()
    return instance, True


def _ensure_access_model(db: Session) -> dict[str, Role]:
    for code, description in ALL_PERMISSIONS.items():
        _get_or_create(
            db, Permission, {"description": description}, code=code
        )
    db.flush()
    permissions = {p.code: p for p in db.scalars(select(Permission)).all()}

    roles: dict[str, Role] = {}
    for name in ROLE_PERMISSIONS:
        role, _ = _get_or_create(db, Role, {"description": name.replace("_", " ")}, name=name)
        roles[name] = role
    db.flush()

    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles[role_name]
        for code in codes:
            _get_or_create(
                db,
                RolePermission,
                None,
                role_id=role.id,
                permission_id=permissions[code].id,
            )
    db.flush()
    return roles


def _ensure_rules(db: Session, admin: User) -> None:
    catalogue = compliance_rules()
    for entry in catalogue["rules"]:
        rule, _ = _get_or_create(
            db,
            Rule,
            {
                "title": entry["title"],
                "description": entry.get("description", ""),
                "regulatory_reference": entry.get("regulatory_reference", ""),
            },
            key=entry["key"],
        )
        existing = db.scalars(
            select(RuleVersion).where(
                RuleVersion.rule_id == rule.id, RuleVersion.version == 1
            )
        ).first()
        if existing is not None:
            continue
        version = RuleVersion(
            rule_id=rule.id,
            version=1,
            status="approved",
            applicability=entry.get("applicability", {"op": "always"}),
            condition=entry["condition"],
            missing_outcome=entry.get("missing_outcome", "NOT_EVALUATED"),
            unverified_outcome=entry.get("unverified_outcome", "NEEDS_REVIEW"),
            failure_outcome=entry.get("failure_outcome", "FAIL"),
            blocking=entry.get("blocking", False),
            severity=entry.get("severity", "major"),
            content_hash=_hash(repr(sorted(entry["condition"].items()))),
            approved_by=admin.id,
            approved_at=get_clock().now(),
        )
        db.add(version)
    db.flush()


def _ensure_routes(db: Session) -> None:
    for route_key, route in workflow_routes()["routes"].items():
        for transition in route["transitions"]:
            definition, created = _get_or_create(
                db,
                WorkflowTransitionDefinition,
                {
                    "from_state": transition["from_state"],
                    "to_state": transition["to_state"],
                    "required_permission": transition["required_permission"],
                    "allowed_roles": transition["allowed_roles"],
                    "required_rules": transition.get("required_rules", []),
                    "required_documents": transition.get("required_documents", []),
                    "requires_reason": transition.get("requires_reason", False),
                    "description": transition.get("description", ""),
                },
                route_key=route_key,
                action=transition["action"],
            )
            if not created:
                # Route definitions are policy-as-data: an edited JSON must
                # reach an existing database on the next seed, not only new
                # rows. Only the mutable guard fields are refreshed — the
                # route_key/action identity is the row's key.
                definition.from_state = transition["from_state"]
                definition.to_state = transition["to_state"]
                definition.required_permission = transition["required_permission"]
                definition.allowed_roles = transition["allowed_roles"]
                definition.required_rules = transition.get("required_rules", [])
                definition.required_documents = transition.get("required_documents", [])
                definition.requires_reason = transition.get("requires_reason", False)
                definition.description = transition.get("description", "")
    db.flush()


def _add_document(
    db: Session,
    *,
    application: Application,
    doc_type: str,
    file_name: str,
    fields: list[tuple[str, object, int, float, str]],
    uploaded_at,
    sha: str | None = None,
) -> Document:
    document = Document(
        institution_id=application.institution_id,
        application_id=application.id,
        doc_type=doc_type,
        file_name=file_name,
        content_type="application/pdf",
        file_sha256=sha or _hash(file_name + application.id),
        perceptual_hash=_hash(doc_type + file_name)[:32],
        storage_ref=f"seed://{application.id}/{file_name}",
        size_bytes=1024,
        uploaded_at=uploaded_at,
    )
    db.add(document)
    db.flush()
    for name, value, page, confidence, status in fields:
        db.add(
            ExtractedField(
                document_id=document.id,
                document_version=1,
                field_name=name,
                value=value,
                source_page=page,
                source_span=f"page {page}",
                method="seed",
                confidence=confidence,
                verification_status=status,
            )
        )
    db.flush()
    return document


def seed(db: Session) -> dict:
    now = get_clock().now()
    roles = _ensure_access_model(db)

    region_north, _ = _get_or_create(db, Region, {"name": "Northern Region"}, code="NR")
    region_south, _ = _get_or_create(db, Region, {"name": "Southern Region"}, code="SR")

    institution, _ = _get_or_create(
        db,
        Institution,
        {"name": "Example Institute of Technology", "region_id": region_north.id},
        aicte_id="1-12345678",
    )
    other_institution, _ = _get_or_create(
        db,
        Institution,
        {"name": "Sample Polytechnic College", "region_id": region_south.id},
        aicte_id="1-87654321",
    )

    committee, _ = _get_or_create(
        db,
        Committee,
        {"name": "EVC — Northern Region", "region_id": region_north.id},
        kind="EVC",
    )

    def user(email: str, name: str) -> User:
        instance, _ = _get_or_create(
            db,
            User,
            {"full_name": name, "password_hash": hash_password(DEMO_PASSWORD)},
            email=email,
        )
        return instance

    admin = user("admin@demo.local", "Demo Administrator")
    scrutiny = user("scrutiny@demo.local", "Demo Scrutiny Officer")
    regional = user("regional@demo.local", "Demo Regional Officer")
    evc = user("evc@demo.local", "Demo EVC Member")
    supervisor = user("supervisor@demo.local", "Demo Supervisory Officer")
    representative = user("institution@demo.local", "Demo Institution Representative")
    sac_member = user("sac@demo.local", "Demo SAC Member")
    council_member = user("council@demo.local", "Demo Council Member")
    competent_authority = user("competent-authority@demo.local", "Demo Competent Authority")

    def grant(user_obj: User, role_name: str, scope_type: str, scope_id: str | None):
        existing = db.scalars(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user_obj.id,
                UserRoleAssignment.role_id == roles[role_name].id,
            )
        ).first()
        if existing is None:
            db.add(
                UserRoleAssignment(
                    user_id=user_obj.id,
                    role_id=roles[role_name].id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                )
            )
            db.flush()

    grant(admin, ADMINISTRATOR, "global", None)
    grant(scrutiny, SCRUTINY_OFFICER, "assigned", None)
    grant(regional, REGIONAL_OFFICER, "region", region_north.id)
    grant(evc, EVC_MEMBER, "committee", committee.id)
    grant(supervisor, SUPERVISORY_OFFICER, "region", region_north.id)
    grant(representative, INSTITUTION_REPRESENTATIVE, "institution", institution.id)
    grant(sac_member, SAC_MEMBER, "region", region_north.id)
    grant(council_member, COUNCIL_MEMBER, "global", None)
    grant(competent_authority, COMPETENT_AUTHORITY, "region", region_north.id)

    existing_jurisdiction = db.scalars(
        select(JurisdictionAssignment).where(
            JurisdictionAssignment.user_id == regional.id,
            JurisdictionAssignment.region_id == region_north.id,
        )
    ).first()
    if existing_jurisdiction is None:
        db.add(
            JurisdictionAssignment(user_id=regional.id, region_id=region_north.id)
        )
        db.flush()

    _ensure_rules(db, admin)
    _ensure_routes(db)

    main, created = _get_or_create(
        db,
        Application,
        {
            "institution_id": institution.id,
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2026-27",
            "cycle_end": None,
            "current_state": "scrutiny",
            "status": "scrutiny",
            "assigned_officer_id": scrutiny.id,
            "current_state_since": now - timedelta(days=6),
            "submitted_at": now - timedelta(days=8),
        },
        id="app-main-0001",
    )
    if main.cycle_end is None:
        from datetime import date

        main.cycle_end = date(2027, 3, 31)

    second, _ = _get_or_create(
        db,
        Application,
        {
            "institution_id": other_institution.id,
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2026-27",
            "current_state": "submitted",
            "status": "submitted",
            "assigned_officer_id": None,
            "current_state_since": now - timedelta(days=2),
            "submitted_at": now - timedelta(days=2),
        },
        id="app-second-0002",
    )

    existing_route, _ = _get_or_create(
        db,
        Application,
        {
            "institution_id": institution.id,
            "category": "existing_technical",
            "route_key": "existing_technical",
            "cycle": "2026-27",
            "current_state": "scrutiny",
            "status": "scrutiny",
            "assigned_officer_id": scrutiny.id,
            "current_state_since": now - timedelta(days=12),
            "submitted_at": now - timedelta(days=14),
        },
        id="app-existing-0003",
    )

    draft, _ = _get_or_create(
        db,
        Application,
        {
            "institution_id": institution.id,
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2026-27",
            "current_state": "draft",
            "status": "draft",
            "current_state_since": now,
        },
        id="app-draft-0004",
    )
    for application in (main, second, existing_route, draft):
        from datetime import date

        if application.cycle_end is None:
            application.cycle_end = date(2027, 3, 31)
    db.flush()

    from ..models import CaseAssignment

    for target, role_name, user_id, committee_id in (
        (main, "scrutiny_officer", scrutiny.id, None),
        (existing_route, "scrutiny_officer", scrutiny.id, None),
        (main, "evc_member", evc.id, committee.id),
    ):
        existing_assignment = db.scalars(
            select(CaseAssignment).where(
                CaseAssignment.application_id == target.id,
                CaseAssignment.user_id == user_id,
                CaseAssignment.revoked_at.is_(None),
            )
        ).first()
        if existing_assignment is None:
            db.add(
                CaseAssignment(
                    application_id=target.id,
                    user_id=user_id,
                    committee_id=committee_id,
                    role_name=role_name,
                )
            )
    db.flush()

    if created:
        # Main case: verified lease, conflicting ownership record, missing affidavit.
        lease = _add_document(
            db,
            application=main,
            doc_type="lease_deed",
            file_name="lease-deed.pdf",
            uploaded_at=now - timedelta(days=9),
            fields=[
                ("valid_from", "2026-04-01", 1, 0.97, "verified"),
                ("valid_to", "2028-03-31", 7, 0.93, "verified"),
                ("issuing_authority", "Sub-Registrar, Demo District", 1, 0.88, "verified"),
                ("lessee_name", "Example Institute of Technology", 2, 0.95, "verified"),
            ],
        )
        _add_document(
            db,
            application=main,
            doc_type="ownership_record",
            file_name="ownership-record.pdf",
            uploaded_at=now - timedelta(days=8),
            fields=[
                ("lease_expiry", "2027-03-31", 3, 0.86, "verified"),
                ("record_holder", "Example Institute of Technology", 1, 0.9, "verified"),
            ],
        )
        _add_document(
            db,
            application=main,
            doc_type="fire_safety_certificate",
            file_name="fire-safety.pdf",
            uploaded_at=now - timedelta(days=30),
            fields=[
                ("valid_to", (now + timedelta(days=45)).date().isoformat(), 2, 0.9, "verified"),
                ("issuing_authority", "Demo Fire Department", 1, 0.87, "verified"),
            ],
        )
        _add_document(
            db,
            application=second,
            doc_type="lease_deed",
            file_name="lease-deed-shared.pdf",
            uploaded_at=now - timedelta(days=3),
            sha=lease.file_sha256,
            fields=[
                ("valid_from", "2026-04-01", 1, 0.9, "unverified"),
                ("valid_to", "2028-03-31", 7, 0.82, "unverified"),
            ],
        )
        _add_document(
            db,
            application=existing_route,
            doc_type="lease_deed",
            file_name="existing-lease.pdf",
            uploaded_at=now - timedelta(days=20),
            fields=[
                ("valid_from", "2026-04-01", 1, 0.95, "verified"),
                ("valid_to", "2028-03-31", 6, 0.91, "verified"),
                ("issuing_authority", "Sub-Registrar, Demo District", 1, 0.9, "verified"),
                ("lessee_name", "Example Institute of Technology", 2, 0.94, "verified"),
            ],
        )
        _add_document(
            db,
            application=existing_route,
            doc_type="ownership_record",
            file_name="existing-ownership.pdf",
            uploaded_at=now - timedelta(days=20),
            fields=[("lease_expiry", "2028-03-31", 2, 0.9, "verified")],
        )
        _add_document(
            db,
            application=existing_route,
            doc_type="affidavit",
            file_name="existing-affidavit.pdf",
            uploaded_at=now - timedelta(days=19),
            fields=[
                ("institution_name", "Example Institute of Technology", 1, 0.93, "verified"),
                ("aicte_id", "1-12345678", 1, 0.9, "verified"),
            ],
        )
        _add_document(
            db,
            application=existing_route,
            doc_type="faculty_list",
            file_name="faculty-list.pdf",
            uploaded_at=now - timedelta(days=19),
            fields=[("faculty_count", 72, 2, 0.8, "verified")],
        )

        db.add(
            Undertaking(
                application_id=main.id,
                obligation_key="land_document_undertaking",
                title="Submit registered land document within 90 days",
                condition_text="Registered lease deed to be submitted post-approval.",
                evidence_required="Registered lease deed",
                due_at=now + timedelta(days=20),
                status="pending",
                reminder_policy={"profile": "undertaking_default"},
            )
        )
        db.add(
            Undertaking(
                application_id=main.id,
                obligation_key="faculty_recruitment_undertaking",
                title="Complete faculty recruitment",
                condition_text="Appoint 12 faculty against sanctioned posts.",
                evidence_required="Appointment orders",
                due_at=now - timedelta(days=10),
                status="pending",
                reminder_policy={"profile": "undertaking_default"},
            )
        )
        db.flush()

        audit = AuditService(db)
        audit.append(
            action="application.created",
            entity_type="application",
            entity_id=main.id,
            outcome="accepted",
            actor_id=representative.id,
            actor_role=INSTITUTION_REPRESENTATIVE,
            after={"state": "draft", "category": main.category},
        )
        audit.append(
            action="workflow.submit",
            entity_type="application",
            entity_id=main.id,
            outcome="accepted",
            actor_id=representative.id,
            actor_role=INSTITUTION_REPRESENTATIVE,
            before={"state": "draft"},
            after={"state": "submitted"},
        )
        audit.append(
            action="workflow.start_scrutiny",
            entity_type="application",
            entity_id=main.id,
            outcome="accepted",
            actor_id=scrutiny.id,
            actor_role=SCRUTINY_OFFICER,
            before={"state": "submitted"},
            after={"state": "scrutiny"},
        )
        # Transition rows to match the audit trail, so "undo the last step"
        # works on the demo data exactly as it does on live cases.
        db.add(
            WorkflowTransition(
                application_id=main.id,
                action="submit",
                from_state="draft",
                to_state="submitted",
                actor_id=representative.id,
                reason="",
                created_at=main.submitted_at or now,
            )
        )
        db.add(
            WorkflowTransition(
                application_id=main.id,
                action="start_scrutiny",
                from_state="submitted",
                to_state="scrutiny",
                actor_id=scrutiny.id,
                reason="",
                created_at=now - timedelta(days=6),
            )
        )
        db.commit()

    # Re-running the seed must persist idempotent additions (a new route, a new
    # rule) even when every demo row already existed.
    db.commit()

    return {
        "users": {
            "admin": admin.email,
            "scrutiny": scrutiny.email,
            "regional": regional.email,
            "evc": evc.email,
            "supervisor": supervisor.email,
            "institution": representative.email,
        },
        "password": DEMO_PASSWORD,
        "applications": {
            "main": main.id,
            "second": second.id,
            "existing": existing_route.id,
            "draft": draft.id,
        },
        "institution_id": institution.id,
        "region_id": region_north.id,
        "committee_id": committee.id,
    }


def main() -> None:
    from ..core.db import SessionLocal, create_all

    create_all()
    db = SessionLocal()
    try:
        summary = seed(db)
        print("Seeded demo data:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
