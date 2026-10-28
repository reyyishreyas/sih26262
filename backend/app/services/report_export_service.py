"""Dependency-free CSV and PDF rendering for the report bundle."""

from __future__ import annotations

import csv
import io
import json
import textwrap
from typing import Any


def as_csv(bundle: dict[str, Any]) -> bytes:
    """Write one portable CSV containing a row per report record."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("report", "record_type", "record_number", "data_json"))
    for report_name, report_data in bundle["reports"].items():
        if isinstance(report_data, dict):
            _write_csv_records(writer, report_name, report_data)
        else:
            writer.writerow((report_name, "summary", 1, _json(report_data)))
    return output.getvalue().encode("utf-8-sig")


def _write_csv_records(writer, report_name: str, data: dict[str, Any]) -> None:
    record_number = 0
    for key, value in data.items():
        if isinstance(value, list):
            for item in value:
                record_number += 1
                writer.writerow((report_name, key, record_number, _json(item)))
        else:
            record_number += 1
            writer.writerow((report_name, "summary", record_number, _json({key: value})))
    if record_number == 0:
        writer.writerow((report_name, "summary", 1, "{}"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def as_pdf(bundle: dict[str, Any]) -> bytes:
    """Render report data as a small, searchable PDF using the built-in fonts."""
    lines = [
        "AICTE operational reports",
        f"Generated at: {bundle['generated_at']}",
        f"Scope: {bundle['scope']['type']}",
        "",
    ]
    for report_name, report_data in bundle["reports"].items():
        lines.append(report_name.replace("_", " ").title())
        lines.extend(textwrap.wrap(_json(report_data), width=92) or ["{}"])
        lines.append("")
    for note_name, note in bundle.get("notes", {}).items():
        lines.extend(textwrap.wrap(f"Note ({note_name}): {note}", width=92))
    return _pdf_from_lines(lines)


def _pdf_from_lines(lines: list[str]) -> bytes:
    pages = [lines[offset : offset + 55] for offset in range(0, len(lines), 55)] or [[]]
    objects: list[bytes] = [b""]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append(
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
        f"/Count {len(pages)} >>".encode("ascii")
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page, page_id in zip(pages, page_ids, strict=True):
        content_id = page_id + 1
        content_lines = ["BT", "/F1 8 Tf", "40 800 Td", "11 TL"]
        for line in page:
            safe = line.encode("ascii", "replace").decode("ascii")
            escaped = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content_lines.append(f"({escaped}) Tj T* ")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode(
                "ascii"
            )
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects[1:], start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
