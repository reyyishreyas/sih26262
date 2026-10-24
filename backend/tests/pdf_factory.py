"""Builds small, real PDFs for tests.

The old tests uploaded a fake ``%PDF-1.4`` byte string and relied on the mock
extractor to return canned values anyway. Now that extraction actually reads
the file, a test that wants a document to contain something has to upload a
document that really contains it. These helpers write a minimal but valid PDF
so the text layer is genuine and pypdf reads it back.
"""

from __future__ import annotations


def text_pdf(pages: list[list[str]]) -> bytes:
    """Returns a valid PDF with one Helvetica text block per given page."""
    if not pages:
        raise ValueError("a PDF needs at least one page")

    objects: list[bytes] = []
    page_ids = [3 + 2 * index for index in range(len(pages))]
    font_id = 3 + 2 * len(pages)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    )

    for index, lines in enumerate(pages):
        stream = _text_stream(lines)
        encoded = stream.encode("latin-1", "replace")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {4 + 2 * index} 0 R >>"
            ).encode()
        )
        objects.append(
            b"<< /Length "
            + str(len(encoded)).encode()
            + b" >>\nstream\n"
            + encoded
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _text_stream(lines: list[str]) -> str:
    # PDF string literals escape backslash and parentheses; the rest of the
    # content stream is fixed.
    body = " ".join(f"({_escape(line)}) Tj T*" for line in lines)
    return f"BT /F1 12 Tf 50 780 Td 14 TL {body} ET"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def lease_deed_pdf(
    *,
    lessee: str = "Example Institute of Technology",
    lessor: str = "Demo Land Holdings Private Limited",
    authority: str = "Sub-Registrar of Records, Demo District",
    valid_from: str = "01 April 2026",
    valid_to: str = "31 March 2028",
) -> bytes:
    return text_pdf(
        [
            [
                "REGISTERED LEASE DEED",
                f"Lessor: {lessor}",
                f"Lessee: {lessee}",
                f"Issuing Authority: {authority}",
                f"Valid From: {valid_from}",
                f"Valid To: {valid_to}",
            ]
        ]
    )


def affidavit_pdf(
    *,
    institution: str = "Example Institute of Technology",
    aicte_id: str = "1-12345678",
    document_id: str = "AFF-2026-0007",
    sworn_on: str = "12 April 2026",
) -> bytes:
    return text_pdf(
        [
            ["AFFIDAVIT", f"Name of Institution: {institution}"],
            [f"AICTE Identity No: {aicte_id}", f"Document ID: {document_id}"],
            [f"Sworn on {sworn_on}"],
        ]
    )
