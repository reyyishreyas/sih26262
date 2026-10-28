"""Phase 5 exit check: the change-of-site demo walk (FR-38–FR-48).

The plan's Phase 5 exit check (line 92) reads: *"auto-fill → edit → amber
badge → address mismatch + 'partial shifting' red findings → highlight →
confirm one, dismiss one."* Like ``test_phase4_exit_check.py``, this file
proves the Phase 5 pieces **compose on one seeded case**, entirely through
the public API — each piece also has its own suite
(``test_evidence_crosschecks``, ``test_site_checks``, ``test_precheck_status``,
``test_openrouter_vision``, ``test_phase5_site_move_fixtures``) and the
three-value edit contract has its own coverage in ``test_three_value``.

The narrative walked here:

1. **Auto-fill** — the institution uploads three synthetic documents (EoA
   letter, Format-2 NOC, Format-3 resolution; ``tests/pdf_factory.py``
   builders, fictional values only). The extraction pipeline reads the
   labelled fields with no manual entry, and every field arrives with its
   provenance: page, engine and a bbox it really sits on.
2. **Edit → amber badge** — the institution corrects the NOC's old address
   via the claim route: refused with 400 (nothing recorded) without a
   reason, then recorded with one. The response and the documents listing
   keep the Claim Value beside the untouched Extraction Value (the amber
   badge's data) and ``baseline_version`` does not move (an edit is never
   an evaluable fact — FR-41).
3. **Address mismatch + "partial shifting" findings** — the advisory
   pre-check flags the NOC/EoA address and survey discrepancies (RULE-E02)
   and the resolution's partial-shifting phrase plus the uncovered
   programme (RULE-SITE-01) as ``discrepancy_signal`` /
   ``potential_partial_coverage``; the aggregate label is DEFICIENCY
   CANDIDATE — advisory only, never a deficiency, gate or decision
   (PRD §8 step 5; the label arrays say so explicitly).
4. **Highlight** — the mismatched NOC field arrives with the bbox it was
   read from, so the UI can highlight the evidence it disagrees with
   (FR-48); no box is ever invented.
5. **Confirm one, dismiss one** — the operational compliance findings on
   the same case carry real amber/red rows; the officer confirms one and
   dismisses the other (dismissal requires a reason, refusal is audited).
   Advisory diagnostics are display-only and are never dispositionable —
   the real findings belong to the persisted evaluation batch (DEC-0024).

Advisory throughout: nothing here gates, rejects or decides; the EoA/NOC/
Format-3 field paths remain labelled placeholders pending the official
templates (PRD §19 Q13).
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy import select

APP = "app-main-0001"
OFFICER = "scrutiny@demo.local"
INSTITUTION = "institution@demo.local"

E2E_URL = "/api/v1/applications"


def _documents_list(client, headers) -> dict[str, dict]:
    """doc_type -> {field_name: field payload} for the uploaded documents."""
    rows = client.get(f"{E2E_URL}/{APP}/documents", headers=headers).json()
    return {
        row["doc_type"]: {f["field_name"]: f for f in row["fields"]}
        for row in rows
    }


def _upload(client, headers, doc_type: str, factory) -> dict:
    response = client.post(
        f"{E2E_URL}/{APP}/documents",
        headers=headers,
        data={"doc_type": doc_type},
        files={"file": (f"{doc_type}.pdf", factory(), "application/pdf")},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def test_phase5_demo_walk(client, as_user):
    from pdf_factory import (
        eoa_letter_pdf,
        format_2_noc_pdf,
        format_3_resolution_pdf,
    )

    ofc = as_user(OFFICER)
    inst = as_user(INSTITUTION)

    # ------------------------------------------------------------------ 1
    # Auto-fill: three labelled documents, no manual entry.
    eoa = _upload(client, inst, "eoa_letter", eoa_letter_pdf)
    noc = _upload(client, inst, "university_noc", format_2_noc_pdf)
    resolution = _upload(client, inst, "format_3_resolution", format_3_resolution_pdf)
    for body, expected in (
        (eoa, 7),
        (noc, 8),
        (resolution, 2),
    ):
        assert body["extraction"]["simulated"] is False
        assert body["extraction"]["fields_extracted"] == expected

    listed = _documents_list(client, ofc)
    eoa_fields = listed["eoa_letter"]
    noc_fields = listed["university_noc"]
    res_fields = listed["format_3_resolution"]

    assert eoa_fields["pid"]["value"] == "SYNTHETIC-PID-001"
    assert eoa_fields["approved_programmes"]["value"] == (
        "Computer Engineering, Civil Engineering"
    )
    assert noc_fields["old_address"]["value"] == "99 Changed Road, Sample City"
    assert res_fields["resolution_text"]["value"] == (
        "The move to the new site involves partial shifting of one programme "
        "while it continues at 12 Legacy Lane"
    )
    assert res_fields["programmes_covered"]["value"] == "Computer Engineering"
    for field_obj in [*eoa_fields.values(), *noc_fields.values(), *res_fields.values()]:
        # Auto-fill provenance (5.2): everything the UI needs to display a
        # highlight — an OCR-extracted field always knows its page/engine,
        # and text-layer reads carry a real box (no invented boxes).
        assert field_obj["verification_status"] == "unverified"
        assert field_obj["source_page"] >= 1
        assert field_obj["method"] == "pdf_text"
        assert field_obj["bbox"] is not None
        assert field_obj["claim_value"] is None
        assert field_obj["master_value"] is None

    # ------------------------------------------------------------------ 2
    # Edit → amber badge: claim without a reason is refused, nothing recorded.
    old_address_id = noc_fields["old_address"]["id"]
    bad = client.post(
        f"{E2E_URL}/{APP}/documents/{noc['document']['id']}"
        f"/fields/{old_address_id}/claim",
        headers=inst,
        json={"value": "10 Example Road, Sample City"},
    )
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    still = _documents_list(client, inst)["university_noc"]["old_address"]
    assert still["claim_value"] is None and still["claim_reason"] is None

    baseline_before = client.get(f"{E2E_URL}/{APP}", headers=inst).json()[
        "application"
    ]["baseline_version"]
    claim = client.post(
        f"{E2E_URL}/{APP}/documents/{noc['document']['id']}"
        f"/fields/{old_address_id}/claim",
        headers=inst,
        json={
            "value": "10 Example Road, Sample City",
            "reason": "Corrected to the address the EoA letter records.",
        },
    )
    assert claim.status_code == status.HTTP_200_OK, claim.text
    assert claim.json()["claim_value"] == "10 Example Road, Sample City"
    assert claim.json()["edited"] is True
    # No baseline bump: rules never read the claim (FR-41).
    baseline_after = client.get(f"{E2E_URL}/{APP}", headers=inst).json()[
        "application"
    ]["baseline_version"]
    assert baseline_after == baseline_before

    # The badge data is on the listing: Extraction kept, Claim beside it.
    badge = _documents_list(client, inst)["university_noc"]["old_address"]
    assert badge["value"] == "99 Changed Road, Sample City"
    assert badge["claim_value"] == "10 Example Road, Sample City"
    assert badge["claim_reason"] == "Corrected to the address the EoA letter records."
    assert badge["claimed_by"] is not None
    assert badge["master_value"] is None

    # ------------------------------------------------------------------ 3
    # Advisory findings: address/survey mismatch (E02) + partial shifting.
    report = client.get(f"{E2E_URL}/{APP}/compliance", headers=ofc).json()
    evidence = {row["rule_id"]: row for row in report["advisory_checks"]}
    site = {row["rule_id"]: row for row in report["advisory_site_checks"]}

    e02 = evidence["RULE-E02"]
    assert e02["comparison"] == "discrepancy_signal"
    pair_labels = {
        (pair["extraction_path"], pair["comparison_path"]): pair["comparison"]
        for pair in e02["comparisons"]
    }
    assert (
        pair_labels[("documents.university_noc.old_address",
                     "documents.eoa_letter.institution_address")]
        == "mismatch"
    )
    assert (
        pair_labels[("documents.university_noc.survey_number",
                     "documents.eoa_letter.survey_number")]
        == "mismatch"
    )
    # Trust/PID/type still agree — only the address pair failed (FR-42).
    assert evidence["RULE-E01"]["comparison"] == "matches_on_available_fields"
    assert evidence["RULE-E03"]["comparison"] == "matches_on_available_fields"

    site01 = site["RULE-SITE-01"]
    assert site01["diagnostic"] == "potential_partial_coverage"
    assert site01["matched_phrases"] == ["partial shifting"]
    assert site01["missing_programmes"] == ["civil engineering"]
    assert site["RULE-SITE-02"]["outcome"] == "REVIEW REQUIRED"

    precheck = report["precheck"]
    assert precheck["outcome"] == "DEFICIENCY CANDIDATE"
    assert "RULE-E02" in precheck["triggered_rules"]
    assert "RULE-SITE-01" in precheck["triggered_rules"]
    rule_statuses = sorted(set(precheck["triggered_rule_statuses"].values()))
    assert rule_statuses == ["unverified"]
    assert precheck["blocking"] is False
    assert precheck["automatic_workflow_action"] is False
    assert precheck["creates_deficiency"] is False

    # ------------------------------------------------------------------ 3b
    # The edit can never clear the rule: the claim on the NOC address did
    # not change the Extraction Value the crosschecks read (FR-41).
    current = _documents_list(client, ofc)["university_noc"]["old_address"]
    assert current["value"] == "99 Changed Road, Sample City"

    # ------------------------------------------------------------------ 4
    # Highlight: the mismatched field knows where it sits on the page.
    assert current["bbox"]["x"] is not None
    assert current["bbox"]["width"] > 0

    # ------------------------------------------------------------------ 5
    # Confirm one, dismiss one — on *operational* findings only.
    evaluate = client.post(
        f"{E2E_URL}/{APP}/compliance/evaluate", headers=ofc
    )
    assert evaluate.status_code == status.HTTP_200_OK
    listing = client.get(f"{E2E_URL}/{APP}/compliance", headers=ofc).json()
    findings = [
        row
        for row in listing["findings"]
        if row["outcome"] in ("FAIL", "NEEDS_REVIEW")
    ]
    assert len(findings) >= 2

    confirmed, dismissed = findings[0], findings[-1]
    yes = client.post(
        f"{E2E_URL}/{APP}/compliance/findings/{confirmed['finding_id']}/disposition",
        headers=ofc,
        json={"disposition": "confirmed", "reason": ""},
    )
    assert yes.status_code == status.HTTP_200_OK, yes.text
    no_reason = client.post(
        f"{E2E_URL}/{APP}/compliance/findings/{dismissed['finding_id']}/disposition",
        headers=ofc,
        json={"disposition": "dismissed", "reason": ""},
    )
    assert no_reason.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    dismissed_with = client.post(
        f"{E2E_URL}/{APP}/compliance/findings/{dismissed['finding_id']}/disposition",
        headers=ofc,
        json={
            "disposition": "dismissed",
            "reason": "Not relevant to the change-of-site pre-check.",
        },
    )
    assert dismissed_with.status_code == status.HTTP_200_OK

    dispositions = {
        row["rule_key"]: (row["disposition"], row["disposition_reason"])
        for row in client.get(f"{E2E_URL}/{APP}/compliance", headers=ofc).json()[
            "findings"
        ]
    }
    assert dispositions[confirmed["rule_key"]][0] == "confirmed"
    assert dispositions[dismissed["rule_key"]][0] == "dismissed"
    assert dispositions[dismissed["rule_key"]][1] == (
        "Not relevant to the change-of-site pre-check."
    )


def test_phase5_demo_is_audited(client, as_user, db):
    from pdf_factory import eoa_letter_pdf, format_3_resolution_pdf

    from app.models import AuditEvent

    inst = as_user(INSTITUTION)
    _upload(client, inst, "eoa_letter", eoa_letter_pdf)
    _upload(client, inst, "format_3_resolution", format_3_resolution_pdf)

    actions = {
        row.action for row in db.scalars(select(AuditEvent)).all()  # type: ignore[arg-type]
    }
    assert "document.extraction_completed" in actions
