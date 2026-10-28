"""Fee configuration stays nonblocking until source-backed verification."""

from copy import deepcopy

import pytest

from app.services import fee_engine


def test_prd_candidate_values_are_present_but_cannot_become_due_or_block():
    assert fee_engine.config()["status"] == "unverified"
    assert fee_engine.config()["placeholder"] is True

    online = fee_engine.evaluate(
        "additional_evc", institution_class="other", visit_mode="online"
    )
    physical = fee_engine.evaluate(
        "additional_evc", institution_class="government", visit_mode="physical"
    )
    scrutiny = fee_engine.evaluate(
        "additional_scrutiny_shc_sac", institution_class="other"
    )

    assert online["candidate_amount_inr"] == 125000
    assert physical["candidate_amount_inr"] == 50000
    assert scrutiny["candidate_amount_inr"] == 60000
    for result in (online, physical, scrutiny):
        assert result["amount_inr"] is None
        assert result["payment_required"] is False
        assert result["blocking"] is False
        assert result["may_proceed"] is True
        assert result["advisory_only"] is True


def test_missing_institution_type_or_evc_mode_stays_unresolved():
    no_class = fee_engine.evaluate("additional_evc", institution_class=None, visit_mode="online")
    no_mode = fee_engine.evaluate("additional_evc", institution_class="other")
    assert no_class["candidate_amount_inr"] is None
    assert no_mode["candidate_amount_inr"] is None
    assert no_class["blocking"] is False


def test_verified_fee_requires_payment_only_with_complete_source_review(monkeypatch):
    verified_table = deepcopy(fee_engine.config())
    verified_table.update(status="verified", placeholder=False, advisory_only=False)
    verified_table["verification"] = {
        "source_id": "SRC-APH-2024-27",
        "reviewer": "named reviewer",
        "edition": "verified handbook edition",
        "clause": "verified clause",
        "verified_at": "2026-10-28",
    }
    monkeypatch.setattr(fee_engine, "fee_table_policy", lambda: verified_table)

    unpaid = fee_engine.evaluate(
        "additional_evc", institution_class="other", visit_mode="online"
    )
    paid = fee_engine.evaluate(
        "additional_evc", institution_class="other", visit_mode="online", payment_verified=True
    )
    assert unpaid["amount_inr"] == 125000
    assert unpaid["payment_required"] is True
    assert unpaid["blocking"] is True
    assert unpaid["may_proceed"] is False
    assert paid["blocking"] is False
    assert paid["may_proceed"] is True


def test_verified_status_without_source_fields_does_not_activate_gate(monkeypatch):
    table = deepcopy(fee_engine.config())
    table.update(status="verified", placeholder=False)
    table["verification"] = {
        "source_id": "SRC-APH-2024-27", "reviewer": "reviewer"
    }
    monkeypatch.setattr(fee_engine, "fee_table_policy", lambda: table)
    result = fee_engine.evaluate(
        "additional_scrutiny_shc_sac", institution_class="government"
    )
    assert result["status"] == "unverified"
    assert result["amount_inr"] is None
    assert result["blocking"] is False


def test_unknown_fee_event_is_rejected():
    with pytest.raises(ValueError, match="unknown fee event"):
        fee_engine.evaluate("invented", institution_class="other")
