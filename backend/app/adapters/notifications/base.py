"""Notification adapter contract.

Only the interface and a mock exist. The prototype logs delivery; it does not claim
to send email or SMS.
"""

from __future__ import annotations

from typing import Protocol

from ...models import Alert


class NotificationAdapter(Protocol):
    def send(self, alert: Alert) -> str:
        """Return a provider reference, or raise on failure."""
