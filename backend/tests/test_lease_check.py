"""FR-05 / RULE-LEASE-01: remaining lease years vs longest course duration.

PRD FR-05 (P0): "Compute remaining lease years vs longest course duration;
flag" (APH cl. 2.1e). PRD line 53 carries the clause note: "EoA stops once
the live lease equals the longest course duration unless extended by 30
years. Compute and flag remaining years during verification." RULE-LEASE-01
(``compliance_rules.json``) phrases the same thing as a deficiency
candidate. PRD FR-45: read the lease end date, compute years, finding if
equal or shorter; store the end date for expiry alerts.

Safety properties under test:

- **Nothing gates and nothing is decided.** The check is a pure read over
  configuration + the *persisted* output of the grounded lease extractor
  (``evidence_service.build_snapshot``); PDFs are never re-parsed and no
  model is called at read time (DEC-0003, PRD §0).
- **The duration is not invented.** No longest-course-duration figure is
  recorded anywhere in this repo and PRD §19 open question 11 still asks
  for the verified lease/expiry requirements, so the config ships
  ``longest_course_duration_years: null`` and the comparison answers
  ``needs_review`` in production while the remaining-years computation
  still runs. ``insufficient``/``sufficient`` are only reachable when a
  duration is genuinely recorded (tests inject one) or when the lease has
  provably already expired.
- **Equality means stopped unless extended** (the clause's own words) —
  not a pass, not a guess; only a recorded 30-year extension flips it.
- An *unverified* expiry date still computes years but never yields a
  confident verdict beyond the expired-lease deduction, and the
  ``verified`` flag rides along in the response so an officer sees it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models import Application
from app.services import readiness

AS_OF = date(2026, 10, 22)  # the fixed demo clock's business date (IST)

# A five-year duration, injected by tests only — production config is null.
DURATION = 5


def _policy() -> dict:
    return readiness.lease_policy()


def _check(
    valid_to: date | None,
    *,
    duration: int | None = DURATION,
    extension_on_file: bool | None = None,
    as_of: date = AS_OF,
    verified: bool = True,
) -> dict:
    cfg = {
        **_policy(),
        "longest_course_duration_years": duration,
    }
    return readiness.lease_check(
        valid_to,
        cfg=cfg,
        as_of=as_of,
        extension_on_file=extension_on_file,
        verified=verified,
    )


# ------------------------------------------------------------- the config


def test_the_lease_block_loads_unverified_and_advisory():
    policy = _policy()
    assert policy["status"] == "unverified"
    assert policy["advisory_only"] is True


def test_it_cites_fr_05_fr_45_clause_2_1e_and_the_rule_key():
    policy = _policy()
    assert policy["rule_id"] == "RULE-LEASE-01"
    assert policy["clause"] == "2.1e"
    for marker in ("FR-05", "FR-45", "2.1e", "RULE-LEASE-01"):
        assert marker in policy["source"], f"{marker} missing from the source citation"
    assert policy["source"].startswith("md/1_PRD.md")


def test_the_longest_course_duration_is_not_invented():
    """PRD §19 Q11 is open; nothing here may fabricate a duration."""
    policy = _policy()
    assert policy["longest_course_duration_years"] is None
    note = policy["duration_note"]
    assert "§19" in note or "open question" in note.lower()
    assert "Q11" in note or "11" in note


def test_the_30_year_extension_is_prd_carried_and_labelled():
    policy = _policy()
    assert policy["extension_years"] == 30
    assert "Unverified" in policy["extension_years_note"] or "unverified" in policy[
        "extension_years_note"
    ].lower()


def test_whether_an_extension_is_on_file_is_declared_not_modelled():
    entry = _policy()["extension_on_file"]
    assert entry["modelled"] is False
    assert entry["description"]


def test_the_evidence_source_is_the_persisted_extractor_output():
    """Read-time must reuse the snapshot — never re-parse PDFs, never a model."""
    note = _policy()["evidence_note"]
    assert "evidence" in note.lower()
    assert "re-parse" in note or "reparse" in note or "never" in note


# --------------------------------------------- the remaining-years maths


def test_remaining_years_is_computed_from_the_fixed_clock():
    result = readiness.lease_check(date(2028, 3, 31), cfg=_policy(), as_of=AS_OF)
    assert result["remaining_years"] == pytest.approx(1.44, abs=0.01)
    assert result["as_of"] == "2026-10-22"


def test_an_anniversary_clamps_february_29():
    """A 1-year anniversary of 29 Feb is 28 Feb, not an exception."""
    assert readiness.anniversary(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert readiness.anniversary(date(2024, 2, 29), 4) == date(2028, 2, 29)
    assert readiness.anniversary(date(2026, 10, 22), 5) == date(2031, 10, 22)


def test_the_february_29_anniversary_is_what_the_comparison_uses():
    result = _check(date(2025, 2, 28), duration=1, as_of=date(2024, 2, 29))
    assert result["comparison"] == "equals"
    assert result["evaluation"] == "needs_review"  # extension unknown


# ------------------------------------------ the three-valued evaluation


def test_no_lease_on_file_is_never_a_pass():
    result = _check(None)
    assert result["evaluation"] == "needs_review"
    assert result["comparison"] == "not_comparable"
    assert result["remaining_years"] is None
    assert "lease.valid_to" in result["missing_inputs"]


def test_the_shipped_null_duration_answers_needs_review_but_still_computes_years():
    """Production behaviour: duration unrecorded => honest 'needs review'."""
    result = _check(date(2028, 3, 31), duration=None)
    assert result["evaluation"] == "needs_review"
    assert result["remaining_years"] == pytest.approx(1.44, abs=0.01)
    assert result["comparison"] == "not_comparable"
    assert "institution.longest_course_duration_years" in result["missing_inputs"]


def test_a_live_lease_shorter_than_the_duration_is_insufficient():
    result = _check(date(2027, 10, 21), duration=DURATION)  # 1 day short of a year
    assert result["comparison"] == "shorter"
    assert result["evaluation"] == "insufficient"


def test_a_live_lease_longer_than_the_duration_is_sufficient():
    result = _check(date(2035, 1, 1), duration=DURATION)
    assert result["comparison"] == "exceeds"
    assert result["evaluation"] == "sufficient"


def test_equality_is_stopped_unless_extended():
    """The clause's own words: stops *once* the lease equals the duration."""
    ends = date(AS_OF.year + DURATION, AS_OF.month, AS_OF.day)
    assert _check(ends, duration=DURATION, extension_on_file=None)["evaluation"] == (
        "needs_review"
    )
    assert _check(ends, duration=DURATION, extension_on_file=False)["evaluation"] == (
        "insufficient"
    )
    assert _check(ends, duration=DURATION, extension_on_file=True)["evaluation"] == (
        "sufficient"
    )


def test_an_expired_lease_is_insufficient_even_without_a_duration():
    """A proof, not a guess: no live lease can cover any course."""
    result = _check(date(2026, 1, 1), duration=None)
    assert result["evaluation"] == "insufficient"
    assert result["comparison"] == "shorter"
    assert result["remaining_years"] < 0
    assert "institution.longest_course_duration_years" not in result["missing_inputs"]


def test_an_unverified_expiry_never_yields_sufficient():
    result = _check(date(2035, 1, 1), duration=DURATION, verified=False)
    assert result["verified"] is False
    assert result["evaluation"] != "sufficient"
    assert "not verified" in result["reason"]


def test_the_evaluation_vocabulary_has_no_pass_fail_or_reject():
    result = _check(date(2028, 3, 31), duration=DURATION)
    assert result["evaluation"] in {"sufficient", "insufficient", "needs_review"}
    assert result["evaluation"] not in {"pass", "fail", "rejected", "blocked"}
    assert result["advisory_only"] is True
    assert result["status"] == "unverified"
    assert result["clause"] == "2.1e"


def test_the_check_is_pure_and_writes_nothing(db):
    application = db.get(Application, "app-main-0001")
    before = application.baseline_version
    first = readiness.lease_check(date(2028, 3, 31), cfg=_policy(), as_of=AS_OF)
    second = readiness.lease_check(date(2028, 3, 31), cfg=_policy(), as_of=AS_OF)
    assert first == second
    db.expire_all()
    assert db.get(Application, application.id).baseline_version == before


# ------------------------------------------------------------ the endpoint


def test_the_regional_officer_sees_the_computed_years_and_an_honest_answer(
    client, as_user
):
    regional = as_user("regional@demo.local")
    res = client.get(
        "/api/v1/applications/app-main-0001/lease-check", headers=regional
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid_to"] == "2028-03-31"  # the seeded verified lease
    assert body["verified"] is True
    assert body["remaining_years"] == pytest.approx(1.44, abs=0.01)
    assert body["evaluation"] == "needs_review"  # duration is null in config
    assert body["longest_course_duration_years"] is None
    assert "institution.longest_course_duration_years" in body["missing_inputs"]


def test_a_case_without_a_lease_needs_review(client, as_user):
    regional = as_user("regional@demo.local")
    res = client.get(
        "/api/v1/applications/app-draft-0004/lease-check", headers=regional
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid_to"] is None
    assert body["evaluation"] == "needs_review"
    assert body["remaining_years"] is None


def test_an_uploaded_lease_is_read_from_the_grounded_extractors_output(client, as_user):
    """Reuses the persisted extractor result; no re-parse, no model at read time."""
    from pdf_factory import text_pdf

    college = as_user("institution@demo.local")
    regional = as_user("regional@demo.local")
    pdf = text_pdf(
        [
            [
                "COMMERCIAL LEASE AGREEMENT",
                "Lessor: Demo Land Holdings Private Limited",
                "Lessee: Example Institute of Technology",
                "Expiry date: 30 June 2031",
            ]
        ]
    )
    upload = client.post(
        "/api/v1/applications/app-draft-0004/documents",
        headers=college,
        data={"doc_type": "lease_agreement"},
        files={"file": ("lease.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 201

    res = client.get(
        "/api/v1/applications/app-draft-0004/lease-check", headers=regional
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid_to"] == "2031-06-30"
    assert body["verified"] is False  # freshly extracted, human not yet verified
    assert "not verified" in body["reason"]
    assert body["remaining_years"] > 4


def test_reading_the_check_needs_no_officer_rights(client, as_user):
    college = as_user("institution@demo.local")
    res = client.get(
        "/api/v1/applications/app-main-0001/lease-check", headers=college
    )
    assert res.status_code == 200


def test_an_out_of_scope_case_is_404_not_403(client, as_user):
    regional = as_user("regional@demo.local")
    res = client.get(
        "/api/v1/applications/app-second-0002/lease-check", headers=regional
    )
    assert res.status_code == 404
