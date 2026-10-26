"""Reconcile every clock-derived date against a fresh recomputation.

Nightly job (Plan 3.9). Read-only: it recomputes each deadline the same way
the deadline sweep and the per-stage reader compute it, then diffs that against
what the system reports and prints the result as JSON. A clean run shows
``"zero_differences": true``, which is the demo's evidence that nothing stores
a stale "due" flag.

    ../.venv/bin/python -m scripts.reconcile_clocks
    ../.venv/bin/python -m scripts.reconcile_clocks --fail-on-diff   # exit 1 if any

Exit status is 0 on a clean run (and by default even with differences, so a
cron that only logs will not page); pass ``--fail-on-diff`` to make a drift
fail the job, which is what a monitoring cron should use.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.db import SessionLocal
from app.services.reconcile import reconcile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="exit 1 when any clock-derived date has drifted",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = reconcile(db)
    finally:
        db.close()

    payload = report.as_dict()
    print(json.dumps(payload, default=str, indent=2, sort_keys=True))
    if args.fail_on_diff and not report.zero_differences:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
