from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.ocr.mock import MockOCRExtractor
from ..core.clock import get_clock
from ..core.config import get_settings
from ..core.db import get_db
from ..core.permissions import DOCUMENT_READ, DOCUMENT_UPLOAD, DOCUMENT_VERIFY
from ..models import Document, ExtractedField
from ..schemas.api import DocumentOut, VerifyFieldRequest
from ..services.audit_service import AuditService
from ..services.authorization_service import EffectiveAccess, require_application
from ..services.authorization_service import require_permission
from ..services.evidence_service import latest_document_fields
from .deps import get_access, require

router = APIRouter(prefix="/applications/{application_id}/documents", tags=["documents"])
_ocr = MockOCRExtractor()


@router.get("", response_model=list[DocumentOut])
def list_documents(
    application_id: str,
    access: EffectiveAccess = Depends(require(DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> list[Document]:
    require_application(db, access, application_id)
    return list(
        db.scalars(
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.uploaded_at)
        ).all()
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_document(
    application_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    access: EffectiveAccess = Depends(require(DOCUMENT_UPLOAD)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    settings = get_settings()

    content = file.file.read()
    if len(content) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")
    if file.content_type not in settings.allowed_upload_types:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"content type {file.content_type!r} is not allowed",
        )

    sha = hashlib.sha256(content).hexdigest()
    duplicate = db.scalars(
        select(Document).where(
            Document.file_sha256 == sha,
            Document.institution_id != application.institution_id,
        )
    ).first()

    storage_dir = Path(settings.storage_dir) / application.id
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_ref = storage_dir / f"{sha[:16]}-{file.filename}"
    storage_ref.write_bytes(content)

    version = (
        db.scalar(
            select(Document.version)
            .where(
                Document.application_id == application.id,
                Document.doc_type == doc_type,
            )
            .order_by(Document.version.desc())
        )
        or 0
    ) + 1

    extraction = _ocr.extract(
        doc_type=doc_type, content=content, file_name=file.filename or "upload"
    )

    document = Document(
        institution_id=application.institution_id,
        application_id=application.id,
        doc_type=doc_type,
        file_name=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        file_sha256=sha,
        perceptual_hash=None,
        storage_ref=str(storage_ref),
        size_bytes=len(content),
        version=version,
        uploaded_at=get_clock().now(),
    )
    db.add(document)
    db.flush()

    for candidate in extraction.fields:
        db.add(
            ExtractedField(
                document_id=document.id,
                document_version=document.version,
                field_name=candidate.field_name,
                value=candidate.value,
                source_page=candidate.source_page,
                source_span=candidate.source_span,
                method=candidate.method,
                confidence=candidate.confidence,
                verification_status="unverified",
            )
        )

    application.baseline_version += 1
    AuditService(db).append(
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        after={
            "application_id": application.id,
            "doc_type": doc_type,
            "version": version,
            "sha256": sha,
        },
    )
    db.commit()

    return {
        "document": DocumentOut.model_validate(document).model_dump(),
        "extraction": {
            "simulated": extraction.simulated,
            "warnings": extraction.warnings,
            "fields_extracted": len(extraction.fields),
            "note": "Mock extractor: values are canned per document type, not read from the file.",
        },
        "duplicate_of_another_institution": {
            "found": duplicate is not None,
            "document_id": duplicate.id if duplicate else None,
            "institution_id": duplicate.institution_id if duplicate else None,
            "note": (
                "A shared file is a discrepancy to verify, not a finding of fraud."
                if duplicate
                else None
            ),
        },
    }


@router.post("/{document_id}/fields/{field_id}/verify")
def verify_field(
    application_id: str,
    document_id: str,
    field_id: str,
    payload: VerifyFieldRequest,
    access: EffectiveAccess = Depends(require(DOCUMENT_VERIFY)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    require_permission(access, DOCUMENT_VERIFY)

    field = db.get(ExtractedField, field_id)
    if field is None or field.document_id != document_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "field not found on this document")
    document = db.get(Document, document_id)
    if document is None or document.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found on this case")

    before = {
        "field": field.field_name,
        "value": field.value,
        "status": field.verification_status,
    }
    field.verification_status = payload.verification_status
    field.verified_by = access.user_id
    field.verified_at = get_clock().now()
    application.baseline_version += 1

    AuditService(db).append(
        action="document.field_verified",
        entity_type="document",
        entity_id=document_id,
        outcome="accepted",
        actor_id=access.user_id,
        actor_role=access.primary_role,
        reason=payload.note,
        before=before,
        after={"status": payload.verification_status},
    )
    db.commit()
    return {"field_id": field.id, "verification_status": field.verification_status}
