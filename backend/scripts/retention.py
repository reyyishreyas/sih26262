"""Run the bounded retention policy.

Dry-run by default:

    ../.venv/bin/python -m scripts.retention
    ../.venv/bin/python -m scripts.retention --apply

Audit events are never pruned by this command. See docs/RETENTION.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.retention_service import apply_retention, plan_retention


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete eligible rows; without this flag the command only reports",
    )
    parser.add_argument("--login-days", type=int)
    parser.add_argument("--delivery-days", type=int)
    args = parser.parse_args()

    settings = get_settings()
    updates = {}
    if args.login_days is not None:
        updates["retention_login_attempt_days"] = args.login_days
    if args.delivery_days is not None:
        updates["retention_alert_delivery_days"] = args.delivery_days
    if updates:
        settings = settings.model_copy(update=updates)

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        if args.apply:
            result = apply_retention(db, now=now, settings=settings)
        else:
            result = {
                **plan_retention(db, now=now, settings=settings).as_dict(),
                "applied": False,
            }
    finally:
        db.close()

    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
