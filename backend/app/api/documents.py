from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.malware import MalwareDetected, MalwareScannerError
from ..adapters.ocr.mock import MockOCRExtractor
from ..core.clock import get_clock
from ..core.config import get_settings
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import DOCUMENT_READ, DOCUMENT_UPLOAD, DOCUMENT_VERIFY
from ..models import Document, ExtractedField
from ..schemas.api import DocumentOut, VerifyFieldRequest
from ..services import malware_service
from ..services.audit_service import AuditService
from ..services.authorization_service import (
    EffectiveAccess,
    require_application,
    require_permission,
)
from ..services.upload_validation import (
    UnsupportedUpload,
    UploadTooLarge,
    read_upload_limited,
    safe_filename,
    validate_upload,
)
from .deps import require

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
    doc_type: str = Form(..., min_length=1, max_length=64, pattern="^[a-z0-9_]+$"),
    file: UploadFile = File(...),
    access: EffectiveAccess = Depends(require(DOCUMENT_UPLOAD)),
    db: Session = Depends(get_db),
) -> dict:
    application = require_application(db, access, application_id)
    settings = get_settings()

    try:
        content = read_upload_limited(file.file, settings.max_upload_bytes)
    except UploadTooLarge:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large"
        ) from None
    try:
        content_type = validate_upload(
            content=content,
            declared_type=file.content_type,
            allowed_types=settings.allowed_upload_types,
        )
    except UnsupportedUpload as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    filename = safe_filename(file.filename)
    sha = hashlib.sha256(content).hexdigest()
    try:
        malware_result = malware_service.scan_upload(content)
    except MalwareDetected as exc:
        AuditService(db).append(
            action="document.upload_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            reason=f"malware detected: {exc.signature}",
            after={
                "doc_type": doc_type,
                "sha256": sha,
                "scanner": exc.engine,
            },
            request_id=current_request_id(),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "upload rejected by malware scanner",
        ) from None
    except MalwareScannerError:
        AuditService(db).append(
            action="document.upload_rejected",
            entity_type="application",
            entity_id=application.id,
            outcome="rejected",
            actor_id=access.user_id,
            actor_role=access.primary_role,
            reason="malware scanner unavailable",
            after={"doc_type": doc_type, "sha256": sha},
            request_id=current_request_id(),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "malware scanner unavailable; upload was not stored",
        ) from None
    duplicate = db.scalars(
        select(Document).where(
            Document.file_sha256 == sha,
            Document.institution_id != application.institution_id,
        )
    ).first()

    storage_root = Path(settings.storage_dir).resolve()
    storage_dir = (storage_root / application.id).resolve()
    if storage_dir != storage_root and storage_root not in storage_dir.parents:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid application storage path"
        )
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_ref = storage_dir / f"{sha[:16]}-{filename}"
    temporary_ref = storage_ref.with_name(f".{storage_ref.name}.tmp")

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
        doc_type=doc_type, content=content, file_name=filename
    )

    stored = False
    try:
        temporary_ref.write_bytes(content)
        os.replace(temporary_ref, storage_ref)
        stored = True

        document = Document(
            institution_id=application.institution_id,
            application_id=application.id,
            doc_type=doc_type,
            file_name=filename,
            content_type=content_type,
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
            request_id=current_request_id(),
        )
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            storage_ref.unlink(missing_ok=True)
        temporary_ref.unlink(missing_ok=True)
        raise

    return {
        "document": DocumentOut.model_validate(document).model_dump(),
        "extraction": {
            "simulated": extraction.simulated,
            "warnings": extraction.warnings,
            "fields_extracted": len(extraction.fields),
            "note": "Mock extractor: values are canned per document type, not read from the file.",
        },
        "malware_scan": {
            "engine": malware_result.engine,
            "clean": malware_result.clean,
            "note": (
                "Scanner disabled."
                if malware_result.engine == "disabled"
                else "File passed the configured malware scanner."
            ),
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
        request_id=current_request_id(),
    )
    db.commit()
    return {"field_id": field.id, "verification_status": field.verification_status}
