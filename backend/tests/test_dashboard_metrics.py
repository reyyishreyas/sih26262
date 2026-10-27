from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models import Application, Deficiency, EvcVisit, User, WorkflowTransition


def test_dashboard_phase7_metrics_reconcile_and_retain_scope_labels(
    client, as_user, db, clock
):
    main = db.get(Application, "app-main-0001")
    existing = db.get(Application, "app-existing-0003")
    scrutiny_user = db.scalar(select(User).where(User.email == "scrutiny@demo.local"))
    assert main is not None and existing is not None and scrutiny_user is not None

    main.current_state_since = clock.now() - timedelta(days=20)
    existing.current_state_since = clock.now() - timedelta(days=8)
    db.add_all(
        [
            WorkflowTransition(
                application_id=main.id,
                action="return_for_clarification",
                from_state="scrutiny",
                to_state="returned",
                actor_id=scrutiny_user.id,
                reason="Synthetic reporting fixture",
                reason_code="RC-DOC-MISSING",
                created_at=clock.now() - timedelta(days=20),
            ),
            WorkflowTransition(
                application_id=existing.id,
                action="return_for_clarification",
                from_state="scrutiny",
                to_state="returned",
                actor_id=scrutiny_user.id,
                reason="Synthetic reporting fixture",
                reason_code="RC-DOC-MISSING",
                created_at=clock.now() - timedelta(days=1),
            ),
            WorkflowTransition(
                application_id=main.id,
                action="start_scrutiny",
                from_state="submitted",
                to_state="scrutiny",
                actor_id=scrutiny_user.id,
                reason="Synthetic throughput fixture",
                created_at=clock.now() - timedelta(days=2),
            ),
            WorkflowTransition(
                application_id=existing.id,
                action="reject",
                from_state="scrutiny",
                to_state="rejected",
                actor_id=scrutiny_user.id,
                reason="Synthetic rejection with no configured reason-code field.",
                created_at=clock.now() - timedelta(days=3),
            ),
            EvcVisit(
                application_id=main.id,
                scheduled_date=clock.now().date() - timedelta(days=1),
                visit_mode="physical",
                venue="Synthetic delayed visit",
                status="scheduled",
                created_at=clock.now() - timedelta(days=2),
            ),
            EvcVisit(
                application_id=existing.id,
                scheduled_date=clock.now().date() - timedelta(days=3),
                visit_mode="online",
                venue="Synthetic completed visit",
                status="completed",
                completed_at=clock.now() - timedelta(days=2),
                created_at=clock.now() - timedelta(days=4),
            ),
            Deficiency(
                application_id=main.id,
                category="document_deficiency",
                explanation="Synthetic open finding",
                corrective_action="Provide synthetic evidence",
                status="open",
                created_by=scrutiny_user.id,
            ),
            Deficiency(
                application_id=existing.id,
                category="document_deficiency",
                explanation="Synthetic closed finding",
                corrective_action="Provide synthetic evidence",
                status="closed",
                created_by=scrutiny_user.id,
                resolved_by=scrutiny_user.id,
                resolved_at=clock.now(),
                resolution_note="Synthetic test resolution",
            ),
        ]
    )
    db.commit()

    response = client.get(
        "/api/v1/officer/dashboard", headers=as_user("admin@demo.local")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    metrics = body["metrics"]
    in_scope = {row["application_id"] for row in body["drilldowns"]["cases_in_scope"]}

    age_rows = [row for rows in metrics["ageing_bands"].values() for row in rows]
    assert len(age_rows) == body["cases_in_scope"]
    assert {row["application_id"] for row in age_rows} == in_scope

    throughput = metrics["throughput_by_week"]
    assert throughput["window_weeks"] == 8
    assert any(
        row["application_id"] == main.id
        for group in throughput["rows"]
        for row in group["rows"]
    )
    assert all(group["count"] == len(group["rows"]) for group in throughput["rows"])

    attention = metrics["deadline_attention"]
    assert attention["placeholder"] is True and attention["advisory_only"] is True
    assert main.id in {row["application_id"] for row in attention["overdue"]}
    assert existing.id in {row["application_id"] for row in attention["due_soon"]}
    for dimension in ("by_stage", "by_region", "by_officer"):
        for bucket in attention[dimension].values():
            assert {row["application_id"] for row in bucket["overdue"]} <= in_scope
            assert {row["application_id"] for row in bucket["due_soon"]} <= in_scope

    assert main.id in {row["application_id"] for row in metrics["evc_status"]["delayed"]}
    assert existing.id in {row["application_id"] for row in metrics["evc_status"]["completed"]}
    assert main.id in {row["application_id"] for row in metrics["evc_by_mode"]["physical"]}
    assert existing.id in {row["application_id"] for row in metrics["evc_by_mode"]["online"]}
    assert main.id in {
        row["application_id"]
        for row in metrics["outcomes_by_reason_code"]["RC-DOC-MISSING"]
    }
    assert existing.id in {
        row["application_id"]
        for row in metrics["rejections_without_reason_code"]
    }
    compliance = metrics["compliance"]
    assert compliance["placeholder"] is True and compliance["advisory_only"] is True
    assert main.id in {row["application_id"] for row in compliance["overdue"]}
    assert existing.id in {row["application_id"] for row in compliance["closed"]}
    for key in ("issued", "closed", "overdue"):
        assert {row["application_id"] for row in compliance[key]} <= in_scope
