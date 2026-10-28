"""PDF and spreadsheet exports stay scope-filtered and contain all PRD sections."""

from __future__ import annotations

import csv
import io
import json

from pypdf import PdfReader

REPORTS = {
    "pendency",
    "evc_status",
    "deficiency_compliance",
    "appeal_hearing",
    "security_deposit",
    "overdue_escalation",
    "region_performance_by_cycle",
}


def test_csv_export_has_all_seven_report_families_and_scoped_rows(client, as_user):
    response = client.get(
        "/api/v1/reports/export?format=csv", headers=as_user("regional@demo.local")
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="aicte-reports.csv"' in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert {row["report"] for row in rows} == REPORTS
    region_rows = [
        json.loads(row["data_json"])
        for row in rows
        if row["report"] == "region_performance_by_cycle"
        and row["record_type"] == "rows"
    ]
    assert region_rows
    assert {row["region_code"] for row in region_rows} == {"NR"}


def test_pdf_export_is_readable_and_describes_advisory_values(client, as_user):
    response = client.get("/api/v1/reports/export?format=pdf", headers=as_user("admin@demo.local"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "AICTE operational reports" in text
    assert "Security Deposit" in text
    assert "advisory only" in text
    assert "Region Performance By Cycle" in text


def test_exports_require_monitoring_permission_and_valid_format(client, as_user):
    institution = as_user("institution@demo.local")
    assert client.get("/api/v1/reports/export?format=csv", headers=institution).status_code == 403
    admin = as_user("admin@demo.local")
    assert client.get("/api/v1/reports/export?format=xlsx", headers=admin).status_code == 422

