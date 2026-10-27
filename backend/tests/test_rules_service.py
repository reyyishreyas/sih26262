"""Rule versions: approval, immutability, and identical evaluation everywhere."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Application, Rule, RuleVersion
from app.services import compliance_service


def test_seeded_rule_set_loads_only_approved_versions(db):
    specs = compliance_service.load_rule_specs(db)
    keys = {spec.key for spec in specs}
    assert "REQUIRED_DOC_AFFIDAVIT" in keys
    assert "UNDERTAKING_NO_OVERDUE" in keys
    assert len(specs) == 7
    assert all(spec.version == 1 for spec in specs)
    assert all(spec.regulatory_status == "unverified" for spec in specs)
    assert all(spec.blocking is False for spec in specs)


def test_operational_assessment_labels_unverified_rules_nonblocking(db):
    report = compliance_service.evaluate_application(
        db, db.get(Application, "app-main-0001"), persist=False
    )
    assert report.results
    assert all(result.regulatory_status == "unverified" for result in report.results)
    assert all(result.blocking is False for result in report.results)


def test_approved_version_is_immutable(db):
    version = db.scalars(select(RuleVersion)).first()
    assert version.status == "approved"
    version.condition = {"op": "always"}
    with pytest.raises(ValueError, match="immutable"):
        db.flush()
    db.rollback()


def test_regulatory_status_cannot_be_changed_on_approved_version(db):
    version = db.scalars(select(RuleVersion)).first()
    assert version.status == "approved"
    version.regulatory_status = "verified"
    with pytest.raises(ValueError, match="immutable"):
        db.flush()
    db.rollback()


def test_retiring_an_approved_version_is_allowed(db):
    version = db.scalars(select(RuleVersion)).first()
    version.status = "retired"
    db.flush()
    db.commit()
    assert db.get(RuleVersion, version.id).status == "retired"


def test_new_version_can_be_drafted_and_approved(db):
    rule = db.scalars(select(Rule)).first()
    draft = RuleVersion(
        rule_id=rule.id,
        version=2,
        status="draft",
        condition={"op": "always"},
        applicability={"op": "always"},
        content_hash="draft",
    )
    db.add(draft)
    db.flush()
    draft.condition = {"op": "exists", "field": "documents.lease_deed.valid_to"}
    draft.content_hash = "final"
    draft.status = "approved"
    db.flush()
    db.commit()

    specs = {spec.key: spec for spec in compliance_service.load_rule_specs(db)}
    assert specs[rule.key].version == 2

    draft.condition = {"op": "always"}
    with pytest.raises(ValueError, match="immutable"):
        db.flush()
    db.rollback()


def test_draft_version_does_not_change_assessment(db):
    """A draft must not be picked up by operational evaluation."""
    rule = db.scalars(select(Rule)).first()
    db.add(
        RuleVersion(
            rule_id=rule.id,
            version=9,
            status="draft",
            condition={"op": "always"},
            applicability={"op": "always"},
            content_hash="wip",
        )
    )
    db.flush()
    specs = {spec.key: spec for spec in compliance_service.load_rule_specs(db)}
    assert specs[rule.key].version == 1
