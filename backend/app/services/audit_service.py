"""Hash-chained audit log.

Every event commits with the business change it describes. Rejected attempts are
committed on their own, after the business transaction has been rolled back, so a
rejection can never be lost and a success can never be claimed without its event.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..models import AuditChainHead, AuditEvent, canonical_json


@dataclass
class ChainVerification:
    ok: bool
    checked: int
    first_broken_seq: int | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "first_broken_seq": self.first_broken_seq,
            "reason": self.reason,
        }


def _event_hash(event: AuditEvent, prev_hash: str) -> str:
    body = canonical_json(
        {
            "at": iso(event.at),
            "actor_id": event.actor_id,
            "actor_role": event.actor_role,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "outcome": event.outcome,
            "reason": event.reason,
            "before": event.before or {},
            "after": event.after or {},
            "request_id": event.request_id,
        }
    )
    return hashlib.sha256(f"{prev_hash}{body}".encode()).hexdigest()


def _head(db: Session) -> AuditChainHead:
    head = db.get(AuditChainHead, 1, with_for_update=True)
    if head is None:
        head = AuditChainHead(id=1, last_seq=0, last_hash="0" * 64)
        db.add(head)
        db.flush()
    return head


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        outcome: str,
        actor_id: str | None = None,
        actor_role: str | None = None,
        reason: str = "",
        before: dict | None = None,
        after: dict | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        head = _head(self.db)
        event = AuditEvent(
            at=get_clock().now(),
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            reason=reason,
            before=before or {},
            after=after or {},
            request_id=request_id,
            prev_hash=head.last_hash,
        )
        event.hash = _event_hash(event, head.last_hash)
        head.last_hash = event.hash
        head.last_seq = (head.last_seq or 0) + 1
        self.db.add(event)
        self.db.flush()
        return event


def append_in_new_transaction(**kwargs: Any) -> AuditEvent:
    """Durable path for rejected attempts, after the business transaction rolled back."""
    from ..core.db import SessionLocal

    db = SessionLocal()
    try:
        event = AuditService(db).append(**kwargs)
        db.commit()
        return event
    finally:
        db.close()


def verify_chain(db: Session) -> ChainVerification:
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).all()
    prev_hash = "0" * 64
    for event in events:
        if event.prev_hash != prev_hash:
            return ChainVerification(
                ok=False,
                checked=len(events),
                first_broken_seq=event.seq,
                reason="prev_hash does not match the previous event",
            )
        expected = _event_hash(event, prev_hash)
        if event.hash != expected:
            return ChainVerification(
                ok=False,
                checked=len(events),
                first_broken_seq=event.seq,
                reason="event content does not match its recorded hash",
            )
        prev_hash = event.hash
    head = db.get(AuditChainHead, 1)
    if head and head.last_seq != len(events):
        return ChainVerification(
            ok=False,
            checked=len(events),
            reason="chain head does not match the event count",
        )
    return ChainVerification(ok=True, checked=len(events))


def timeline(db: Session, application_id: str, limit: int = 500) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(
                (AuditEvent.entity_id == application_id)
                | (
                    (AuditEvent.entity_type == "application")
                    & (AuditEvent.entity_id == application_id)
                )
            )
            .order_by(AuditEvent.seq)
            .limit(limit)
        ).all()
    )


def count_events(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AuditEvent)) or 0
