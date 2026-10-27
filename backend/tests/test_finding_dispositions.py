from __future__ import annotations

from app.models import Application, AuditEvent, RuleEvaluation

APP_ID = "app-existing-0003"


def _finding(db, *, outcome: str, rule_key: str) -> RuleEvaluation:
    application = db.get(Application, APP_ID)
    row = RuleEvaluation(
        application_id=APP_ID,
        rule_key=rule_key,
        rule_version=1,
        regulatory_status="verified",
        blocking=True,
        batch_id="phase5-disposition-batch",
        outcome=outcome,
        application_baseline_version=application.baseline_version,
    )
    db.add(row)
    db.commit()
    return row


def test_scrutiny_exit_needs_dispositions_for_red_and_amber_findings(db, client, as_user):
    red = _finding(db, outcome="FAIL", rule_key="RULE-RED")
    amber = _finding(db, outcome="NEEDS_REVIEW", rule_key="RULE-AMBER")
    headers = as_user("scrutiny@demo.local")

    snapshot = client.get(f"/api/v1/applications/{APP_ID}/compliance", headers=headers)
    assert snapshot.status_code == 200
    actionable = {
        finding["finding_id"]
        for finding in snapshot.json()["findings"]
        if finding["rule_key"] in {"RULE-RED", "RULE-AMBER"}
    }
    assert actionable == {red.id, amber.id}

    transition = client.post(
        f"/api/v1/applications/{APP_ID}/transitions",
        headers=headers,
        json={"action": "approve", "reason": "Decision recorded"},
    )
    assert transition.status_code == 200
    assert transition.json()["accepted"] is False
    assert "RULE-RED" in " ".join(transition.json()["reasons"])
    assert "RULE-AMBER" in " ".join(transition.json()["reasons"])

    dismissed = client.post(
        f"/api/v1/applications/{APP_ID}/compliance/findings/{red.id}/disposition",
        headers=headers,
        json={"disposition": "dismissed", "reason": "Evidence reviewed by officer"},
    )
    confirmed = client.post(
        f"/api/v1/applications/{APP_ID}/compliance/findings/{amber.id}/disposition",
        headers=headers,
        json={"disposition": "confirmed"},
    )
    assert dismissed.status_code == 200
    assert confirmed.status_code == 200

    transition = client.post(
        f"/api/v1/applications/{APP_ID}/transitions",
        headers=headers,
        json={"action": "approve", "reason": "Decision recorded"},
    )
    assert transition.json()["accepted"] is True
    actions = db.query(AuditEvent.action).filter(AuditEvent.entity_id.in_([red.id, amber.id])).all()
    assert [action[0] for action in actions].count("finding.disposition_recorded") == 2


def test_dismissal_requires_reason_and_neutral_outcomes_cannot_be_disposed(db, client, as_user):
    red = _finding(db, outcome="FAIL", rule_key="RULE-RED")
    passed = _finding(db, outcome="PASS", rule_key="RULE-PASS")
    headers = as_user("scrutiny@demo.local")
    missing_reason = client.post(
        f"/api/v1/applications/{APP_ID}/compliance/findings/{red.id}/disposition",
        headers=headers,
        json={"disposition": "dismissed"},
    )
    neutral = client.post(
        f"/api/v1/applications/{APP_ID}/compliance/findings/{passed.id}/disposition",
        headers=headers,
        json={"disposition": "confirmed"},
    )
    assert missing_reason.status_code == 422
    assert neutral.status_code == 422
