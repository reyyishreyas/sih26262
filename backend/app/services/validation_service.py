"""Deterministic AI Copilot Engine.

Validates extracted lease agreement fields against regulatory criteria immediately post-extraction:
1. 'valid_to' (Expiry date): parses to a future date (relative to evaluation date / application cycle).
2. 'lessee_name' (Lessee): matches the applicant institution's name.

If a rule fails, automatically generates an auditable Deficiency record in 'draft' status
linked to the failed field and document, citing the verbatim source_quote.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..core.clock import get_clock
from ..core.context import current_request_id
from ..models import Application, Deficiency, Document, ExtractedField, Institution
from .audit_service import AuditService


def _get_field_val_and_quote(val_obj: Any) -> tuple[str, str]:
    """Unpack either dict format {'value': ..., 'source_quote': ...} or raw value."""
    if isinstance(val_obj, dict):
        return str(val_obj.get("value", "")), str(val_obj.get("source_quote", ""))
    return str(val_obj or ""), ""


def validate_lease_document(
    db: Session,
    *,
    application: Application,
    document: Document,
    fields: list[ExtractedField],
    actor_id: str | None = None,
    actor_role: str | None = None,
) -> list[Deficiency]:
    """Runs deterministic AI Copilot rules over lease agreement / deed fields.

    Drafts structured deficiencies for any unmet conditions without automatically
    altering application workflow state.
    """
    if document.doc_type != "lease_agreement":
        return []

    institution = db.get(Institution, application.institution_id)
    institution_name = institution.name if institution else ""

    now = get_clock().now()
    today = now.date() if hasattr(now, "date") else date.today()

    drafted_deficiencies: list[Deficiency] = []

    # Map fields by name
    by_name = {f.field_name: f for f in fields}

    # Rule 1: Expiry date parses to a future date
    if "valid_to" in by_name:
        field_row = by_name["valid_to"]
        raw_val, source_quote = _get_field_val_and_quote(field_row.value)
        parsed_date: date | None = None
        try:
            parsed_date = date.fromisoformat(raw_val[:10])
        except (ValueError, TypeError):
            pass

        quote_clause = f" (quoted: \"{source_quote}\")" if source_quote else ""

        if parsed_date is None:
            explanation = (
                f"AI Copilot Flag: Lease expiry date '{raw_val}' could not be parsed as a valid calendar date{quote_clause}. "
                "AICTE regulations require an unambiguous valid term."
            )
            action = "Upload a valid registered lease agreement clearly specifying the lease expiry date."
            d = _create_draft_deficiency(
                db,
                application_id=application.id,
                document_id=document.id,
                extracted_field_id=field_row.id,
                category=document.doc_type,
                rule_key="LEASE_VALID_FUTURE_DATE",
                field_name="valid_to",
                extracted_value=field_row.value,
                explanation=explanation,
                corrective_action=action,
                created_by=actor_id or "system_copilot",
                actor_role=actor_role or "system",
            )
            drafted_deficiencies.append(d)
        elif parsed_date <= today:
            explanation = (
                f"AI Copilot Flag: Document states expiry is '{raw_val}'{quote_clause}, which is in the past. "
                "AICTE regulations require an active lease covering the operational period."
            )
            action = "Upload an updated, registered lease agreement covering the future operational duration."
            d = _create_draft_deficiency(
                db,
                application_id=application.id,
                document_id=document.id,
                extracted_field_id=field_row.id,
                category=document.doc_type,
                rule_key="LEASE_VALID_FUTURE_DATE",
                field_name="valid_to",
                extracted_value=field_row.value,
                explanation=explanation,
                corrective_action=action,
                created_by=actor_id or "system_copilot",
                actor_role=actor_role or "system",
            )
            drafted_deficiencies.append(d)

    # Rule 2: Lessee matches the applicant institution's name
    if "lessee_name" in by_name and institution_name:
        field_row = by_name["lessee_name"]
        raw_val, source_quote = _get_field_val_and_quote(field_row.value)
        quote_clause = f" (quoted: \"{source_quote}\")" if source_quote else ""

        # Normalize comparison (case-insensitive and remove punctuation/extra whitespace)
        import re
        norm_lessee = re.sub(r"[^\w\s]", "", raw_val.lower()).strip()
        norm_inst = re.sub(r"[^\w\s]", "", institution_name.lower()).strip()

        # Check if either contains the other or matches tokens
        matches = (norm_lessee in norm_inst) or (norm_inst in norm_lessee)
        if not matches:
            explanation = (
                f"AI Copilot Flag: Lessee entity '{raw_val}'{quote_clause} does not match "
                f"applicant institution name '{institution_name}'. "
                "AICTE mandates that the lease deed must explicitly be in the name of the applicant institution."
            )
            action = f"Provide a lease deed registered specifically in the name of '{institution_name}', or submit a certified trust transfer deed."
            d = _create_draft_deficiency(
                db,
                application_id=application.id,
                document_id=document.id,
                extracted_field_id=field_row.id,
                category=document.doc_type,
                rule_key="LEASE_LESSEE_MATCH",
                field_name="lessee_name",
                extracted_value=field_row.value,
                explanation=explanation,
                corrective_action=action,
                created_by=actor_id or "system_copilot",
                actor_role=actor_role or "system",
            )
            drafted_deficiencies.append(d)

    return drafted_deficiencies


def _create_draft_deficiency(
    db: Session,
    *,
    application_id: str,
    document_id: str,
    extracted_field_id: str,
    category: str,
    rule_key: str,
    field_name: str,
    extracted_value: Any,
    explanation: str,
    corrective_action: str,
    created_by: str,
    actor_role: str,
) -> Deficiency:
    now = get_clock().now()
    deficiency = Deficiency(
        application_id=application_id,
        document_id=document_id,
        extracted_field_id=extracted_field_id,
        category=category,
        rule_key=rule_key,
        field_name=field_name,
        extracted_value=extracted_value,
        explanation=explanation,
        corrective_action=corrective_action,
        status="draft",
        created_by=created_by,
        created_at=now,
    )
    db.add(deficiency)
    db.flush()

    AuditService(db).append(
        action="deficiency.created",
        entity_type="deficiency",
        entity_id=deficiency.id,
        outcome="accepted",
        actor_id=created_by,
        actor_role=actor_role,
        reason=explanation[:255],
        after={
            "application_id": application_id,
            "category": category,
            "field_name": field_name,
            "status": "draft",
            "copilot": True,
        },
        request_id=current_request_id(),
    )
    return deficiency
