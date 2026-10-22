"""Upload safety checks.

Content-Type is client supplied and must never be trusted on its own. We sniff the
magic bytes, enforce the configured size limit while reading (so a huge body is not
buffered first), and sanitise the client filename before it reaches a filesystem
path.
"""

from __future__ import annotations

import re
from typing import BinaryIO

_MAGIC_TYPES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_READ_CHUNK = 64 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadTooLarge(ValueError):
    pass


class UnsupportedUpload(ValueError):
    pass


def sniff_content_type(content: bytes) -> str | None:
    for prefix, content_type in _MAGIC_TYPES:
        if content.startswith(prefix):
            return content_type
    return None


def read_upload_limited(stream: BinaryIO, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UploadTooLarge(f"file exceeds the {limit} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def safe_filename(name: str | None) -> str:
    raw = (name or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _SAFE_NAME.sub("_", raw).strip("._-")
    return (cleaned or "upload")[:120]


def validate_upload(
    *,
    content: bytes,
    declared_type: str | None,
    allowed_types: tuple[str, ...],
) -> str:
    if not content:
        raise UnsupportedUpload("empty file")
    if declared_type not in allowed_types:
        raise UnsupportedUpload(
            f"content type {declared_type!r} is not allowed"
        )
    detected = sniff_content_type(content)
    if detected is None:
        raise UnsupportedUpload(
            "file signature is not a supported PDF, PNG or JPEG"
        )
    if detected != declared_type:
        raise UnsupportedUpload(
            f"file content is {detected!r} but the upload declared {declared_type!r}"
        )
    return detected
