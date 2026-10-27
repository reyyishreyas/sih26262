"""Phase 4 exit check: the full deficiency → compliance → Re-Scrutiny loop.

The plan's Phase 4 exit check (line 77) reads: *"full deficiency →
compliance → Re-Scrutiny loop for one seeded case."* Each piece has its own
suite (`test_doc_check`, `test_deficiency_loop`, `test_annexure_checklist`,
`test_compliance_window`); this file proves they **compose** on one seeded
case — `app-main-0001` (new_technical, scrutiny, the only seeded route with
return/resubmit legs; BUG-0014 keeps `existing_technical` out of scope).

The narrative walked here, entirely through the public API:

1. Officer runs the RULE-DOC-01 pre-check (4.5) and stages its candidates
   as **draft** deficiencies — idempotent, audited, case does not move.
2. The institution reads the report and is answered `not_issued` with zero
   rows (drafts never leak, 4.4).
3. Officer returns for clarification (`RC-DOC-MISSING`): drafts are
   promoted to `open`, the report becomes `issued`, the placeholder window
   (§19 Q1) opens.
4. Institution uploads the corrective affidavit and resubmits; the report
   reads `received` and `awaiting_re_scrutiny` while anything is still
   outstanding.
5. Officer closes the row — `awaiting_re_scrutiny` clears — and restarts
   scrutiny (the Re-Scrutiny leg).
6. The audit trail carries every step: staging, finalisation, the return,
   addressing/close, the resubmit and the re-scrutiny start.

Advisory throughout (DEC-0003): the pre-check and the report never gate
step 3–5; nothing here invents a clause, fee or date.
"""

from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import func, select

from app.core.clock import FixedClock, set_clock
from app.models import AuditEvent, Deficiency
from app.services import demo_clock
from tests.conftest import DEMO_NOW

APP = "app-main-0001"
OFFICER = "scrutiny@demo.local"
INSTITUTION = "institution@demo.local"


@pytest.fixture(autouse=True)
def _isolated_clock():
    """The demo clock is process-wide; never leak a jump into another test."""
    set_clock(FixedClock(DEMO_NOW))
    yield
    set_clock(FixedClock(DEMO_NOW))


def _pdf(name: str = "upload.pdf") -> tuple[str, bytes, str]:
    from pdf_factory import affidavit_pdf

    return (name, affidavit_pdf(), "application/pdf")


def _report(client, headers: dict) -> dict:
    response = client.get(f"/api/v1/applications/{APP}/deficiency-report", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    return response.json()


def _deficiencies(db) -> list[Deficiency]:
    return list(
        db.scalars(
            select(Deficiency).where(Deficiency.application_id == APP)
        ).all()
    )


def _audit_actions(db, *entity_ids: str) -> list[str]:
    """Audit actions in true insertion order (`seq`); an `IN (...)` filter
    otherwise comes back in index order, which would fake the chronology."""
    return list(
        db.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.entity_id.in_(entity_ids))
            .order_by(AuditEvent.seq)
        ).all()
    )


# --------------------------------------------------------------- the loop


def test_the_full_deficiency_compliance_rescrutiny_loop(client, as_user, db, access_for):
    officer = as_user(OFFICER)
    institution = as_user(INSTITUTION)

    # ---- 1. Pre-check (4.5): one candidate on this case, read-only.
    check = client.get(f"/api/v1/applications/{APP}/doc-check", headers=officer)
    assert check.status_code == status.HTTP_200_OK
    check_body = check.json()
    assert check_body["outcome"] == "one_or_more_required_documents_missing"
    assert check_body["needs_review"] is True
    assert {row["field_name"] for row in check_body["missing_items"]} == {
        "affidavit_2"
    }

    staged = client.post(
        f"/api/v1/applications/{APP}/doc-check/drafts", headers=officer
    )
    assert staged.status_code == status.HTTP_200_OK
    created = staged.json()["created"]
    assert [row["field_name"] for row in created] == ["affidavit_2"]
    def_id = created[0]["deficiency_id"]

    # Idempotent: re-staging changes nothing while the live row covers the line.
    again = client.post(
        f"/api/v1/applications/{APP}/doc-check/drafts", headers=officer
    )
    assert again.status_code == status.HTTP_200_OK
    assert again.json()["created"] == []
    assert len(_deficiencies(db)) == 1

    # Staging moved nothing: the case is still in scrutiny.
    state = client.get(f"/api/v1/applications/{APP}", headers=officer)
    assert state.json()["application"]["current_state"] == "scrutiny"

    # ---- 2. The draft is invisible to the institution (4.4, 4.6 visibility).
    report = _report(client, institution)
    assert report["status"] == "not_issued"
    assert report["deficiencies"] == []
    assert report["counts"]["draft"] == 0

    # ---- 3. Officer returns for clarification: drafts are promoted.
    ret = client.post(
        f"/api/v1/applications/{APP}/transitions",
        headers=officer,
        json={
            "action": "return_for_clarification",
            "reason": "Affidavit 2 required by the document pre-check is not on file.",
            "reason_code": "RC-DOC-MISSING",
        },
    )
    assert ret.status_code == status.HTTP_200_OK
    assert ret.json()["accepted"] is True
    assert ret.json()["to_state"] == "returned"
    assert db.get(Deficiency, def_id).status == "open"

    report = _report(client, institution)
    assert report["status"] == "issued"
    assert report["window_status"] == "open"
    assert report["window_days"] > 0  # labelled placeholder, §19 Q1
    assert [row["id"] for row in report["deficiencies"]] == [def_id]

    # ---- 4. Institution corrects: upload the affidavit, then resubmit.
    upload = client.post(
        f"/api/v1/applications/{APP}/documents",
        headers=institution,
        data={"doc_type": "affidavit"},
        files={"file": _pdf("affidavit-2.pdf")},
    )
    assert upload.status_code == status.HTTP_201_CREATED

    # Composition observation (verified, not assumed): the upload→addressed
    # matcher in documents.py only considers rows whose document_id is not
    # the new document — SQL excludes NULL — and matches on category or
    # rule_key, while a RULE-DOC-01 draft carries document_id=None and
    # category="document_deficiency". So the staged row does NOT flip to
    # "addressed" automatically; the officer's explicit close (step 5) is
    # the designed path for pre-check rows.
    addressed_by_upload = db.get(Deficiency, def_id).status == "addressed"

    # Correction takes time: move the demo clock one day through the real
    # Phase 3.8 service (audited, admin-scoped) before the reply lands.
    # `_resubmitted_at` requires the reply to be strictly *after* the issue
    # instant — same-instant transitions are correctly not a reply
    # (BUG-0016: the test compressed the whole loop into one clock instant).
    demo_clock.advance(db, access_for("admin@demo.local"), 1.0)

    resubmit = client.post(
        f"/api/v1/applications/{APP}/transitions",
        headers=institution,
        json={
            "action": "resubmit",
            "reason": "Uploaded the missing affidavit.",
        },
    )
    assert resubmit.status_code == status.HTTP_200_OK
    assert resubmit.json()["accepted"] is True
    assert resubmit.json()["to_state"] == "submitted"

    # ---- 5. Compliance: received, awaiting Re-Scrutiny while outstanding.
    report = _report(client, institution)
    assert report["window_status"] == "received"
    assert report["resubmitted_at"] is not None
    outstanding = report["counts"]["open"] + report["counts"]["addressed"]
    assert outstanding > 0  # the pre-check row is still live after resubmit
    assert report["awaiting_re_scrutiny"] is True

    # ---- 6. Officer closes the row: awaiting clears, no state change.
    close = client.post(
        f"/api/v1/applications/{APP}/deficiencies/{def_id}/close",
        headers=officer,
        json={"resolution_note": "Affidavit 2 verified on file."},
    )
    assert close.status_code == status.HTTP_200_OK
    assert close.json()["status"] == "closed"

    report = _report(client, institution)
    assert report["awaiting_re_scrutiny"] is False
    assert report["counts"] == {
        "draft": 0,
        "open": 0,
        "addressed": 0 if not addressed_by_upload else 1,
        "closed": 1,
    }

    # ---- 7. Re-Scrutiny leg: the case goes back to scrutiny.
    restart = client.post(
        f"/api/v1/applications/{APP}/transitions",
        headers=officer,
        json={
            "action": "start_scrutiny",
            "reason": "Re-Scrutiny after corrected submission.",
        },
    )
    assert restart.status_code == status.HTTP_200_OK
    assert restart.json()["accepted"] is True
    assert restart.json()["to_state"] == "scrutiny"

    # ---- 8. The audit trail carries every step, in order.
    # The promotion is audited against the deficiency row, everything else
    # against the case; within the return the promotion lands first
    # (workflow_service promotes drafts, then appends workflow.<action>).
    actions = _audit_actions(db, APP, def_id)
    expected = [
        "deficiency.doc_check_staged",  # 4.5 staging (officer, audited)
        "deficiency.finalized",  # draft -> open, one per draft
        "workflow.return_for_clarification",  # report issued, window opens
        "workflow.resubmit",  # institution's corrected submission
        "workflow.start_scrutiny",  # Re-Scrutiny leg
    ]
    last_index = -1
    for action in expected:
        positions = [
            i for i, seen in enumerate(actions) if seen == action and i > last_index
        ]
        assert positions, f"missing audit action {action!r} in {actions}"
        last_index = positions[0]

    # The close is audited too (against the deficiency, not the case).
    close_events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "deficiency.closed",
            AuditEvent.entity_id == def_id,
        )
    ).all()
    assert len(close_events) == 1
    assert close_events[0].outcome == "accepted"


def test_the_report_and_pre_check_stay_read_only_through_the_loop(client, as_user, db):
    """The advisory reads never store anything — a row-count snapshot."""
    officer = as_user(OFFICER)

    def counts() -> tuple[int, int]:
        return (
            db.scalar(select(func.count()).select_from(Deficiency)),
            db.scalar(select(func.count()).select_from(AuditEvent)),
        )

    before = counts()
    client.get(f"/api/v1/applications/{APP}/doc-check", headers=officer)
    client.get(f"/api/v1/applications/{APP}/deficiency-report", headers=officer)
    client.get(f"/api/v1/applications/{APP}/doc-check", headers=officer)
    assert counts() == before
