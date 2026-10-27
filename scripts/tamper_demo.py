#!/usr/bin/env python3
"""Demonstrate audit-chain verification in an isolated temporary SQLite DB."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sih26262-tamper-demo-") as temp_dir:
        os.environ["SIH_DATABASE_URL"] = f"sqlite:///{temp_dir}/audit.db"
        os.environ["SIH_CLOCK_MODE"] = "fixed"
        os.environ["SIH_CLOCK_FIXED_AT"] = "2026-10-27T00:00:00+00:00"
        os.environ["SIH_ENV"] = "test"
        os.environ["SIH_JWT_SECRET"] = "throwaway-demo-secret"

        from sqlalchemy import select, text

        from app.core.clock import FixedClock, set_clock
        from app.core.db import Base, SessionLocal, engine
        from app.models import AuditEvent  # noqa: F401
        from app.services.audit_service import AuditService, verify_chain

        set_clock(FixedClock(datetime(2026, 10, 27, tzinfo=UTC)))
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            audit = AuditService(db)
            audit.append(
                action="demo.first",
                entity_type="demo",
                entity_id="throwaway",
                outcome="accepted",
            )
            audit.append(
                action="demo.second",
                entity_type="demo",
                entity_id="throwaway",
                outcome="accepted",
            )
            db.commit()
            clean = verify_chain(db)
            if not clean.ok:
                print(f"FAIL: untouched chain: {clean.as_dict()}")
                return 1
            print(f"PASS: untouched chain verifies ({clean.checked} events)")

            target = db.scalar(select(AuditEvent).order_by(AuditEvent.seq))
            db.execute(
                text("UPDATE audit_events SET reason = :reason WHERE seq = :seq"),
                {"reason": "tampered in throwaway demo", "seq": target.seq},
            )
            db.commit()
            db.expire_all()
            broken = verify_chain(db)
            if broken.ok:
                print("FAIL: modified chain was not detected")
                return 1
            print(
                "PASS: tampering is detected "
                f"(broken sequence {broken.first_broken_seq})"
            )
            return 0
        finally:
            db.close()
            set_clock(None)


if __name__ == "__main__":
    raise SystemExit(main())
