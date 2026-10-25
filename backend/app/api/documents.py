from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.malware import MalwareDetected, MalwareScannerError
from ..core.clock import get_clock
from ..core.config import get_settings
from ..core.context import current_request_id
from ..core.db import get_db
from ..core.permissions import DOCUMENT_READ, DOCUMENT_UPLOAD, DOCUMENT_VERIFY
from ..models import Deficiency, Document, ExtractedField
from ..schemas.api import DocumentOut, VerifyFieldRequest
from ..services import malware_service, ocr_service
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

    extraction = ocr_service.get_ocr_extractor().extract(
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

        created_fields: list[ExtractedField] = []
        for candidate in extraction.fields:
            field_obj = ExtractedField(
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
            db.add(field_obj)
            created_fields.append(field_obj)
        db.flush()

        # Connect corrected document version to open/draft deficiencies for PRIOR versions of this doc_type
        # Mark as 'addressed' (requires subsequent officer review to close).
        open_deficiencies = db.scalars(
            select(Deficiency).where(
                Deficiency.application_id == application.id,
                Deficiency.status.in_(("open", "draft")),
                Deficiency.document_id != document.id,
            )
        ).all()
        addressed_count = 0
        for def_item in open_deficiencies:
            match = False
            if def_item.document_id:
                old_doc = db.get(Document, def_item.document_id)
                if old_doc and old_doc.doc_type == doc_type:
                    match = True
            elif def_item.category == doc_type or doc_type in (def_item.rule_key or ""):
                match = True

            if match:
                def_item.status = "addressed"
                def_item.corrective_document_id = document.id
                addressed_count += 1
                AuditService(db).append(
                    action="deficiency.addressed",
                    entity_type="deficiency",
                    entity_id=def_item.id,
                    outcome="accepted",
                    actor_id=access.user_id,
                    actor_role=access.primary_role,
                    after={
                        "application_id": application.id,
                        "status": "addressed",
                        "corrective_document_id": document.id,
                        "doc_type": doc_type,
                        "version": version,
                    },
                    request_id=current_request_id(),
                )

        # Run Deterministic AI Copilot Engine on lease agreements for the current document
        from ..services.validation_service import validate_lease_document
        validate_lease_document(
            db,
            application=application,
            document=document,
            fields=created_fields,
            actor_id=access.user_id,
            actor_role=access.primary_role,
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
                "deficiencies_addressed": addressed_count,
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
            "note": (
                "Demo reader: values are canned per document type, not read "
                "from the file."
                if extraction.simulated
                else (
                    "Values were read from the uploaded file. Every one is "
                    "unverified until a checker confirms it."
                    if extraction.fields
                    else "Nothing readable was found in this file."
                )
            ),
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


@router.get("/{document_id}/content")
def download_document(
    application_id: str,
    document_id: str,
    access: EffectiveAccess = Depends(require(DOCUMENT_READ)),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the stored bytes for a document the caller is authorised to see.

    Seeded demo rows point at ``seed://`` refs with no file on disk; for those a
    one-page placeholder PDF is generated on the fly so the UI can always open
    something real.
    """
    require_application(db, access, application_id)
    document = db.get(Document, document_id)
    if document is None or document.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found on this case")

    storage_root = Path(get_settings().storage_dir).resolve()

    if document.storage_ref.startswith("seed://"):
        content = _placeholder_pdf(document)
    else:
        path = Path(document.storage_ref).resolve()
        if storage_root not in path.parents:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid storage reference")
        if not path.is_file():
            raise HTTPException(
                status.HTTP_410_GONE,
                "the stored file is no longer available (retention may have removed it)",
            )
        content = path.read_bytes()

    return Response(
        content=content,
        media_type=document.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{document.file_name}"',
            "Content-Length": str(len(content)),
            "X-Content-SHA256": document.file_sha256,
        },
    )


def _placeholder_pdf(document: Document) -> bytes:
    """A minimal valid single-page PDF used for seeded (non-file) demo documents."""
    lines = [
        "AICTE Approvals - demo document",
        f"File: {document.file_name}",
        f"Type: {document.doc_type}",
        f"Version: {document.version}",
        "This is placeholder evidence generated for the demo dataset.",
        "Upload a real file on this case to replace it.",
    ]
    stream_lines = "BT /F1 12 Tf 50 780 Td 16 TL " + " ".join(
        f"({line}) Tj T*" for line in lines
    ) + " ET"
    stream = stream_lines.encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


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
