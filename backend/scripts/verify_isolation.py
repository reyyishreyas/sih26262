"""Prove the PostgreSQL role contract against a running stack.

Run after `docker compose up -d` (or against any deployment that applied
backend/sql/roles.sql):

    ../.venv/bin/python -m scripts.verify_isolation

Every check is a negative test where it matters: the point is that the database
refuses the operation, not that application code remembers to avoid it.

Development credentials are the defaults; override with environment variables:
    SIH_PG_HOST, SIH_PG_PORT, SIH_PG_DATABASE
    SIH_APP_PASSWORD, SIH_SIM_RO_PASSWORD, SIH_SIM_RW_PASSWORD
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass

import psycopg

HOST = os.environ.get("SIH_PG_HOST", "localhost")
PORT = os.environ.get("SIH_PG_PORT", "5432")
DATABASE = os.environ.get("SIH_PG_DATABASE", "sih26262")
PASSWORDS = {
    "app_rw": os.environ.get("SIH_APP_PASSWORD", "app_rw_dev"),
    "sim_prod_ro": os.environ.get("SIH_SIM_RO_PASSWORD", "sim_prod_ro_dev"),
    "sim_results_rw": os.environ.get("SIH_SIM_RW_PASSWORD", "sim_results_rw_dev"),
    "sih_migrator": os.environ.get("SIH_MIGRATOR_PASSWORD", "sih_migrator_dev"),
}


@dataclass
class Check:
    role: str
    operation: str
    allowed: bool
    error: str = ""


def connect(role: str):
    return psycopg.connect(
        host=HOST,
        port=PORT,
        dbname=DATABASE,
        user=role,
        password=PASSWORDS[role],
        autocommit=False,
        connect_timeout=5,
    )


def expect(role: str, operation: str, sql: str, *, allowed: bool) -> Check:
    try:
        with connect(role) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    cur.fetchall()
            conn.rollback()
        return Check(role, operation, allowed)
    except Exception as exc:  # noqa: BLE001 - we are asserting on the failure
        if allowed:
            return Check(role, operation, False, str(exc).strip())
        return Check(role, operation, True, str(exc).strip().splitlines()[0])


def main() -> int:
    try:
        with connect("sih_migrator") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'sim' ORDER BY table_name"
                )
                tables = [row[0] for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot connect to PostgreSQL at {HOST}:{PORT}: {exc}")
        return 1

    required = {
        "sim_runs",
        "sim_input_snapshots",
        "sim_rule_results",
        "sim_metrics",
    }
    checks: list[Check] = []
    checks.append(
        Check(
            "sih_migrator",
            "sim schema contains all simulation tables",
            required.issubset(set(tables)),
            "" if required.issubset(set(tables)) else f"found {tables}",
        )
    )

    run_id = str(uuid.uuid4())
    checks.append(
        expect(
            "sim_prod_ro",
            "baseline reader can SELECT operational data",
            "SELECT count(*) FROM public.applications",
            allowed=True,
        )
    )
    checks.append(
        expect(
            "sim_prod_ro",
            "baseline reader cannot INSERT operational data",
            "INSERT INTO public.regions (id, code, name) VALUES "
            f"('{uuid.uuid4()}', 'XX', 'should fail')",
            allowed=False,
        )
    )
    checks.append(
        expect(
            "sim_prod_ro",
            "baseline reader cannot reach the simulation schema",
            "SELECT count(*) FROM sim.sim_runs",
            allowed=False,
        )
    )

    checks.append(
        expect(
            "sim_results_rw",
            "results writer can INSERT simulation rows",
            "INSERT INTO sim.sim_runs "
            "(id, application_id, run_by, status, baseline_version, rule_set_version, "
            "superseded, created_at) VALUES "
            f"('{run_id}', 'isolation-check', 'isolation-check', 'completed', 1, 'test', "
            "false, now())",
            allowed=True,
        )
    )
    checks.append(
        expect(
            "sim_results_rw",
            "results writer can SELECT simulation rows",
            "SELECT count(*) FROM sim.sim_runs",
            allowed=True,
        )
    )
    checks.append(
        expect(
            "sim_results_rw",
            "results writer cannot SELECT operational data",
            "SELECT count(*) FROM public.applications",
            allowed=False,
        )
    )
    checks.append(
        expect(
            "sim_results_rw",
            "results writer cannot INSERT operational data",
            "INSERT INTO public.regions (id, code, name) VALUES "
            f"('{uuid.uuid4()}', 'YY', 'should fail')",
            allowed=False,
        )
    )

    checks.append(
        expect(
            "app_rw",
            "application role can read/write operational data",
            "SELECT count(*) FROM public.applications",
            allowed=True,
        )
    )
    checks.append(
        expect(
            "app_rw",
            "application role cannot reach the simulation schema",
            "SELECT count(*) FROM sim.sim_runs",
            allowed=False,
        )
    )

    print(f"PostgreSQL isolation check against {HOST}:{PORT}/{DATABASE}\n")
    failed = 0
    for check in checks:
        ok = check.allowed
        failed += 0 if ok else 1
        mark = "PASS" if ok else "FAIL"
        detail = "" if ok and not check.error else f" ({check.error})"
        print(f"  [{mark}] {check.role}: {check.operation}{detail}")

    if failed:
        print(f"\n{failed} check(s) failed")
        return 1
    print("\nAll isolation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
