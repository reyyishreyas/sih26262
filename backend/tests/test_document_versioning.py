"""Document versioning: immutable replacements, version links, storage atomicity (H.4).

Three properties the plan asks for, each proved by reading the state back:

* a replacement upload adds a **new** version with its own reason — the
  earlier row, its bytes and its extracted values are never rewritten;
* every extracted field stays linked to the version it was read from, and
  verifying a field changes the verdict, never the extraction;
* the upload is all-or-nothing across the two stores: if the database write
  fails after the file is stored, or the file never lands, neither the row
  nor a leftover temp file survives (Essentials: no half-written evidence).

The file-signature rules (magic bytes must match the declared content type)
are asserted here for the two branches `test_hardening` does not reach:
a *lying* declared type and an empty body.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pdf_factory import lease_deed_pdf, text_pdf
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuditEvent, Document, ExtractedField

APPLICATION = "app-draft-0004"


def _upload(client, headers, content: bytes, *, reason: str | None = None):
    data = {"doc_type": "lease_deed"}
    if reason is not None:
        data["reason"] = reason
    return client.post(
        f"/api/v1/applications/{APPLICATION}/documents",
        headers=headers,
        data=data,
        files={"file": ("lease.pdf", content, "application/pdf")},
    )


def _documents(db) -> list[Document]:
    # The API commits in its own session; drop this session's snapshot first.
    db.expire_all()
    return list(
        db.scalars(
            select(Document)
            .where(Document.application_id == APPLICATION)
            .order_by(Document.uploaded_at, Document.version)
        ).all()
    )


def _storage_dir() -> Path:
    return Path(get_settings().storage_dir).resolve() / APPLICATION


def _stored_files() -> dict[str, bytes]:
    directory = _storage_dir()
    if not directory.exists():
        return {}
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _snapshot(document: Document, fields: list[ExtractedField]) -> dict:
    return {
        "id": document.id,
        "sha": document.file_sha256,
        "storage_ref": document.storage_ref,
        "version": document.version,
        "uploaded_at": document.uploaded_at,
        "size": document.size_bytes,
        "fields": sorted(
            (f.id, f.field_name, f.value, f.document_version, f.verification_status)
            for f in fields
        ),
    }


# ---------------------------------------------------------------------------
# Replacement: a new immutable version, with the reason it exists
# ---------------------------------------------------------------------------


def test_a_replacement_adds_a_new_version_and_never_rewrites_the_old_one(
    client, as_user, db
):
    headers = as_user("institution@demo.local")
    first = lease_deed_pdf()
    replacement = text_pdf([["Second issue: seal corrected on page 1."]])

    v1 = _upload(client, headers, first, reason="Initial upload by the college")
    assert v1.status_code == 201
    db.expire_all()
    document_v1 = db.get(Document, v1.json()["document"]["id"])
    before = _snapshot(
        document_v1, list(document_v1.fields)
    )
    files_before = _stored_files()

    v2 = _upload(
        client,
        headers,
        replacement,
        reason="Replaced after scrutiny asked for the corrected seal",
    )
    assert v2.status_code == 201
    assert v2.json()["document"]["version"] == document_v1.version + 1
    assert v2.json()["document"]["upload_reason"] == (
        "Replaced after scrutiny asked for the corrected seal"
    )

    rows = _documents(db)
    assert len(rows) == 2, "a replacement is a second row, not an update"
    assert len({row.version for row in rows}) == 2, "two rows share one version"
    assert rows[1].version == rows[0].version + 1

    refreshed = db.get(Document, document_v1.id)
    assert _snapshot(refreshed, list(refreshed.fields)) == before, (
        "the superseded version was rewritten by the replacement"
    )

    # Both versions keep their own bytes, and each downloads as what it was.
    files_after = _stored_files()
    assert set(files_after) == set(files_before) | {Path(rows[-1].storage_ref).name}
    v1_bytes = client.get(
        f"/api/v1/applications/{APPLICATION}/documents/{document_v1.id}/content",
        headers=headers,
    )
    assert v1_bytes.status_code == 200
    assert hashlib.sha256(v1_bytes.content).hexdigest() == document_v1.file_sha256
    v2_bytes = client.get(
        f"/api/v1/applications/{APPLICATION}/documents/{rows[-1].id}/content",
        headers=headers,
    )
    assert hashlib.sha256(v2_bytes.content).hexdigest() == rows[-1].file_sha256
    assert rows[-1].file_sha256 != document_v1.file_sha256

    # Each version's extraction belongs to that version.
    for row in rows:
        for field in row.fields:
            assert field.document_id == row.id
            assert field.document_version == row.version

    # Both uploads are in the audit chain, each with the reason given.
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "document.uploaded",
            AuditEvent.entity_id.in_([row.id for row in rows]),
        )
    ).all()
    assert len(events) == 2
    assert {event.reason for event in events} == {
        "Initial upload by the college",
        "Replaced after scrutiny asked for the corrected seal",
    }

    # The list endpoint shows the reason, so the version history is readable.
    listed = client.get(
        f"/api/v1/applications/{APPLICATION}/documents", headers=headers
    ).json()
    assert {row["upload_reason"] for row in listed} == {
        "Initial upload by the college",
        "Replaced after scrutiny asked for the corrected seal",
    }


def test_upload_without_a_reason_keeps_the_version_readable(client, as_user, db):
    """The reason is optional: a plain first upload is not refused."""
    headers = as_user("institution@demo.local")
    response = _upload(client, headers, lease_deed_pdf())
    assert response.status_code == 201
    assert response.json()["document"]["upload_reason"] in ("", None)


# ---------------------------------------------------------------------------
# Extraction and findings stay linked to the version they came from
# ---------------------------------------------------------------------------


def test_every_extracted_field_points_at_the_version_it_was_read_from(
    client, as_user, db
):
    headers = as_user("institution@demo.local")
    _upload(client, headers, lease_deed_pdf())
    _upload(client, headers, text_pdf([["Replacement text for the same case."]]))

    fields = list(db.scalars(select(ExtractedField)))
    assert fields, "the uploads should have produced extracted fields"
    for field in fields:
        document = db.get(Document, field.document_id)
        assert document is not None
        assert field.document_version == document.version, (
            f"field {field.id} claims version {field.document_version} "
            f"but its document is version {document.version}"
        )


def test_verifying_a_field_changes_the_verdict_never_the_extraction(
    client, as_user, db
):
    """Immutability of what was read: officers confirm, they do not edit."""
    college = as_user("institution@demo.local")
    # Admin, because app-draft-0004 has no case assignment and the reviewer's
    # scope is assigned cases only — a scope refusal, not a permission one.
    officer = as_user("admin@demo.local")
    upload = _upload(client, college, lease_deed_pdf())
    document_id = upload.json()["document"]["id"]
    fields = upload.json()["document"]["fields"]
    assert fields
    target = fields[0]
    value_before = target["value"]

    verified = client.post(
        f"/api/v1/applications/{APPLICATION}/documents/{document_id}"
        f"/fields/{target['id']}/verify",
        headers=officer,
        json={"verification_status": "verified", "note": "checked against the deed"},
    )
    assert verified.status_code == 200

    db.expire_all()
    field = db.get(ExtractedField, target["id"])
    assert field.verification_status == "verified"
    assert field.value == value_before, "verification must not rewrite the extraction"
    assert db.get(Document, document_id).version == 1


# ---------------------------------------------------------------------------
# Partial storage failure: row and file appear together or not at all
# ---------------------------------------------------------------------------


def test_a_database_failure_after_the_file_is_stored_leaves_no_row_and_no_file(
    client, as_user, db, monkeypatch
):
    """The file is already on disk when the commit fails: it must be removed."""
    headers = as_user("institution@demo.local")
    assert _upload(client, headers, lease_deed_pdf()).status_code == 201
    files_before = _stored_files()
    documents_before = len(_documents(db))

    def _explode(*_args, **_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr("app.api.documents.AuditService.append", _explode)

    failed = _upload(client, headers, text_pdf([["Never persisted."]]))
    assert failed.status_code == 500

    assert len(_documents(db)) == documents_before, "a half-written row survived"
    assert _stored_files() == files_before, "the stored file was not cleaned up"
    assert not any(name.endswith(".tmp") for name in _stored_files()), (
        "a temporary upload file was left behind"
    )


def test_a_failure_while_storing_the_file_leaves_no_row_and_no_temp_file(
    client, as_user, db, monkeypatch
):
    """The other half: the file never lands, so no row may be written either."""
    headers = as_user("institution@demo.local")
    assert _upload(client, headers, lease_deed_pdf()).status_code == 201
    files_before = _stored_files()
    documents_before = len(_documents(db))

    class _ReplaceFails:
        """Only `os.replace` in documents.py, and only for this test."""

        def __getattr__(self, name):
            return getattr(os, name)

        @staticmethod
        def replace(*_args, **_kwargs):
            raise OSError("simulated disk failure")

    monkeypatch.setattr("app.api.documents.os", _ReplaceFails)

    failed = _upload(client, headers, text_pdf([["Never stored."]]))
    assert failed.status_code == 500

    assert len(_documents(db)) == documents_before, "a row was written without a file"
    assert _stored_files() == files_before, "a temp file survived the failure"
    assert not any(name.endswith(".tmp") for name in _stored_files())


# ---------------------------------------------------------------------------
# File-signature checks (the two branches test_hardening does not reach)
# ---------------------------------------------------------------------------


def test_a_declared_type_that_contradicts_the_file_signature_is_refused(
    client, as_user, db
):
    headers = as_user("institution@demo.local")
    files_before = _stored_files()

    lying = client.post(
        f"/api/v1/applications/{APPLICATION}/documents",
        headers=headers,
        data={"doc_type": "lease_deed"},
        files={
            "file": (
                "not-a-really.png",
                b"\x89PNG\r\n\x1a\n" + b"demo image bytes",
                "application/pdf",
            )
        },
    )
    assert lying.status_code == 415
    assert "file content is" in lying.json()["detail"]
    assert "declared" in lying.json()["detail"]

    empty = client.post(
        f"/api/v1/applications/{APPLICATION}/documents",
        headers=headers,
        data={"doc_type": "lease_deed"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 415
    assert "empty" in empty.json()["detail"]

    assert _documents(db) == [], "a refused upload must not create a version"
    assert _stored_files() == files_before, "a refused upload must store nothing"
