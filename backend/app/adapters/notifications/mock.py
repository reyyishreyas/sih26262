"""Mock notification adapter.

Writes a JSON line to ``storage/notifications.log`` so the demo can show a real
delivery record. ``fail_times`` exists only so the retry path can be tested; the UI
labels every delivery as simulated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ...core.clock import get_clock, iso
from ...models import Alert


class MockNotificationAdapter:
    simulated = True

    def __init__(self, log_path: str | Path | None = None, fail_times: int = 0) -> None:
        self.log_path = Path(log_path or os.environ.get("SIH_NOTIFICATION_LOG", "storage/notifications.log"))
        self.fail_times = fail_times
        self._failures = 0

    def send(self, alert: Alert) -> str:
        if self._failures < self.fail_times:
            self._failures += 1
            raise RuntimeError("simulated provider timeout")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        reference = f"mock-{alert.id}-{len(alert.deliveries or []) + 1}"
        record = {
            "provider_ref": reference,
            "channel": "in_app",
            "simulated": True,
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "level": alert.level,
            "recipients": alert.recipients,
            "due_at": iso(alert.due_at),
            "sent_at": iso(get_clock().now()),
        }
        with self.log_path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return reference
