"""Approval Rehearsal: diff correctness, isolation, refusal of unsafe overrides."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import (
    Alert,
    Application,
    AuditEvent,
    Document,
    ExtractedField,
    RuleEvaluation,
    SimInputSnapshot,
    SimMetric,
    SimRuleResult,
    SimRun,
    Undertaking,
    WorkflowTransition,
)
from app.services import rehearsal_service
from app.services.rehearsal_service import OverrideRejected


def fingerprint() -> str:
    """Hash of every production row that a rehearsal must never touch."""
    session = SessionLocal()
    try:
        parts = []
        for model in (
            Application,
            Document,
            ExtractedField,
            Undertaking,
            RuleEvaluation,
            WorkflowTransition,
            AuditEvent,
            Alert,
        ):
            rows = session.execute(select(model).order_by(*model.__table__.primary_key.columns)).scalars().all()
            for row in rows:
                payload = {column.name: getattr(row, column.name) for column in model.__table__.columns}
                parts.append(f"{model.__tablename__}:{sorted(payload.items())}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()
    finally:
        session.close()


def test_rehearsal_resolves_findings_and_reports_diff(db, access_for):
    access = access_for("scrutiny@demo.local")
    before = fingerprint()

    report = rehearsal_service.run_rehearsal(
        db,
        access,
        "app-main-0001",
        overrides={
            "documents.affidavit.document_id": "hypothetical-affidavit",
            "documents.ownership_record.lease_expiry": "2028-03-31",
        },
    )

    assert report["production_modified"] is False
    assert report["metrics"] == {"load_factor": None, "formula_version": None}
    assert report["summary"]["resolved_findings"] == 2
    assert report["summary"]["new_findings"] == 0
    assert report["summary"]["regressed_findings"] == 0

    by_rule = {item["rule_key"]: item for item in report["diff"]}
    assert by_rule["REQUIRED_DOC_AFFIDAVIT"]["before"] == "FAIL"
    assert by_rule["REQUIRED_DOC_AFFIDAVIT"]["after"] == "PASS"
    assert by_rule["REQUIRED_DOC_AFFIDAVIT"]["change"] == "resolved"
    assert by_rule["LEASE_DATE_CONSISTENCY"]["before"] == "NEEDS_REVIEW"
    assert by_rule["LEASE_DATE_CONSISTENCY"]["after"] == "PASS"

    # Rehearsal shows what *would* be possible; it does not perform the transition.
    implications = {item["action"]: item for item in report["workflow_implications"]}
    assert implications["schedule_evc"]["eligible"] is True
    assert "no transition was attempted" in implications["schedule_evc"]["note"]

    # Production is byte-for-byte unchanged.
    assert fingerprint() == before


def test_rehearsal_persists_only_simulation_rows(db, access_for):
    access = access_for("scrutiny@demo.local")
    report = rehearsal_service.run_rehearsal(
        db, access, "app-main-0001", overrides={"documents.affidavit.document_id": "x"}
    )

    run = db.get(SimRun, report["run_id"])
    assert run is not None
    assert run.baseline_version == report["baseline_version"]
    assert db.scalar(select(func.count()).select_from(SimInputSnapshot)) == 1
    assert db.scalar(select(func.count()).select_from(SimRuleResult)) >= 6
    metric = db.scalars(select(SimMetric)).one()
    assert metric.name == "load_factor"
    assert metric.value is None
    assert metric.formula_version is None


def test_rehearsal_baseline_is_never_a_write_path(db, access_for):
    """The baseline connection is read-only at the database level."""
    from app.core.db import open_readonly_session
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    with open_readonly_session() as session:
        with pytest.raises(OperationalError):
            session.execute(text("UPDATE applications SET status = 'approved'"))
            session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"application.status": "approved"},
        {"application.current_state": "approved"},
        {"documents.lease_deed": "whole-document-replacement"},
        {"documents.lease_deed.valid_to": {"year": 2028}},
        {"documents.lease_deed.valid_to": 2028},
        {"documents.lease_deed.va lid": "x"},
    ],
)
def test_unsafe_overrides_are_refused(db, access_for, overrides):
    access = access_for("scrutiny@demo.local")
    runs_before = db.scalar(select(func.count()).select_from(SimRun))
    with pytest.raises(OverrideRejected):
        rehearsal_service.run_rehearsal(db, access, "app-main-0001", overrides=overrides)
    assert db.scalar(select(func.count()).select_from(SimRun)) == runs_before


def test_override_budget_is_enforced(db, access_for):
    access = access_for("scrutiny@demo.local")
    overrides = {f"documents.lease_deed.field_{i}": "x" for i in range(26)}
    with pytest.raises(OverrideRejected):
        rehearsal_service.run_rehearsal(db, access, "app-main-0001", overrides=overrides)


def test_failed_run_leaves_production_and_simulation_untouched(db, access_for):
    access = access_for("scrutiny@demo.local")
    before = fingerprint()
    with pytest.raises(OverrideRejected):
        rehearsal_service.run_rehearsal(
            db, access, "app-main-0001", overrides={"application.route_key": "x"}
        )
    assert fingerprint() == before
    assert db.scalar(select(func.count()).select_from(SimRun)) == 0


def test_rehearsal_uses_the_same_rule_versions_as_operational(db, access_for):
    from app.services import compliance_service

    operational = compliance_service.evaluate_application(db, db.get(Application, "app-main-0001"))
    db.commit()
    access = access_for("scrutiny@demo.local")
    report = rehearsal_service.run_rehearsal(db, access, "app-main-0001", overrides={})

    assert report["rule_set_version"] == operational.rule_set_version
    baseline = {item["rule_key"]: item["before"] for item in report["diff"]}
    for finding in operational.results:
        assert baseline[finding.rule_key] == finding.outcome.value


def test_run_can_be_read_back_from_simulation_storage(db, access_for):
    access = access_for("scrutiny@demo.local")
    report = rehearsal_service.run_rehearsal(
        db, access, "app-main-0001", overrides={"documents.affidavit.document_id": "x"}
    )
    stored = rehearsal_service.get_run(report["run_id"])
    assert stored is not None
    assert stored["production_modified"] is False
    assert stored["overrides"] == {"documents.affidavit.document_id": "x"}
    assert len(stored["diff"]) == len(report["diff"])
    assert stored["metrics"]["load_factor"] is None
