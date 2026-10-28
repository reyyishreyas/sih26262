"""Phase 7 report scope and dashboard/report reconciliation acceptance checks."""

from __future__ import annotations

import csv
import io
import json


def _records(rows: list[dict[str, str]], report_name: str, record_type: str) -> list[dict]:
    return [
        json.loads(row["data_json"])
        for row in rows
        if row["report"] == report_name and row["record_type"] == record_type
    ]


def test_region_scoping_and_case_totals_reconcile_for_each_monitoring_role(client, as_user):
    for email in (
        "scrutiny@demo.local",
        "regional@demo.local",
        "supervisor@demo.local",
        "admin@demo.local",
    ):
        headers = as_user(email)
        case_ids = {
            row["id"] for row in client.get("/api/v1/applications", headers=headers).json()
        }
        report = client.get("/api/v1/reports/export?format=csv", headers=headers)
        assert report.status_code == 200, (email, report.text)
        rows = list(csv.DictReader(io.StringIO(report.content.decode("utf-8-sig"))))

        pendency = next(
            json.loads(row["data_json"])["total_cases"]
            for row in rows
            if row["report"] == "pendency"
            and "total_cases" in json.loads(row["data_json"])
        )
        assert pendency == len(case_ids), email
        region_records = _records(rows, "region_performance_by_cycle", "rows")
        assert {
            case_id for record in region_records for case_id in record["application_ids"]
        } == case_ids

        case_bearing_records = (
            _records(rows, "evc_status", "rows")
            + _records(rows, "deficiency_compliance", "deficiencies")
            + _records(rows, "deficiency_compliance", "compliance")
            + _records(rows, "appeal_hearing", "rows")
            + _records(rows, "security_deposit", "rows")
            + _records(rows, "overdue_escalation", "items")
        )
        assert {record["application_id"] for record in case_bearing_records} <= case_ids, email

        visible_region_codes = {
            region["region_code"]
            for region in client.get("/api/v1/reports/regions", headers=headers).json()["regions"]
        }
        assert {record["region_code"] for record in region_records} <= visible_region_codes, email
