"""FR-01 stubbed portal feed: the FR-01 field set, with an "as of" stamp.

PRD FR-01 (P0, APH cl. 2.3.1): "Receive each final-submitted application
with ID, PID, category, institution type, submission time, TER status,
documents". PRD §18: portal data is not real time — a scheduled sync with
an "as of" time on every screen. The release plan makes the prototype's
version explicit: "sample data, stubbed portal feed".

What this module is: a **stub of the feed's shape**, served from recorded
case data, so the interface is real and clients can be built against it.
Every response says ``source: "stub"`` and carries ``as_of`` (the injectable
clock's instant — never ``datetime.now()``). Fields this repo does not
record (PID, institution type, TER status) are served as ``null`` with the
configuration naming what a live feed would carry — never a guessed value
(Master Prompt §2 rule 4).

What it deliberately is **not**: an ingestion path. FR-01's verb is
"receive", but accepting external records into cases would need a portal
service identity and an untrusted-write path — an external integration and
a role-authority change, both human approval gates (AGENTS.md). That half
is recorded as an open question, not built.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.clock import get_clock, iso
from ..models import Application, Document
from .authorization_service import EffectiveAccess, scope_filter
from .policy import portal_feed_policy as _load_policy


def portal_feed_policy() -> dict[str, Any]:
    """The ``rules/portal_feed.json`` configuration (copied, not shared)."""
    return dict(_load_policy())


def _record(application: Application, documents: list[Document]) -> dict[str, Any]:
    """One final-submitted case in the PRD's own FR-01 field order.

    The key order is the contract (asserted by test): ID, PID, category,
    institution type, submission time, TER status, documents. The three
    unmodelled fields are ``None`` — see ``portal_feed.json -> fields``.
    """
    return {
        "application_id": application.id,
        "pid": None,  # not modelled in this repo (portal_feed.json)
        "category": application.category,
        "institution_type": None,  # not modelled in this repo
        "submission_time": iso(application.submitted_at)
        if application.submitted_at
        else None,
        "ter_status": None,  # no payment record exists anywhere here
        "documents": [
            {
                "doc_type": document.doc_type,
                "file_name": document.file_name,
                "version": document.version,
                "status": document.status,
            }
            for document in sorted(documents, key=lambda d: (d.doc_type, d.version))
        ],
    }


def build_feed(db: Session, access: EffectiveAccess) -> dict[str, Any]:
    """The stubbed feed: every final-submitted case in the caller's scope.

    Read-only — it writes nothing, decides nothing and gates nothing beyond
    the caller's existing scope (an institution sees only its own cases, a
    Regional officer their region), enforced by the same ``scope_filter``
    the applications list uses. ``sync_cadence`` is echoed from config
    (null: no cadence is recorded, so none is invented).
    """
    policy = portal_feed_policy()
    query = (
        select(Application)
        .where(Application.submitted_at.is_not(None))
        .order_by(Application.id)
    )
    clause = scope_filter(access)
    if clause is not None:
        query = query.where(clause)
    applications = list(db.scalars(query).all())

    documents_by_app: dict[str, list[Document]] = {}
    if applications:
        rows = db.scalars(
            select(Document)
            .where(
                Document.application_id.in_([app.id for app in applications]),
                Document.status != "rejected",
            )
            .order_by(Document.uploaded_at.asc())
        ).all()
        for document in rows:
            documents_by_app.setdefault(document.application_id, []).append(document)

    return {
        "source": "stub",
        "as_of": iso(get_clock().now()),
        "status": policy.get("status", "unverified"),
        "advisory_only": bool(policy.get("advisory_only", True)),
        "sync_cadence": policy.get("sync_cadence"),
        "records": [
            _record(application, documents_by_app.get(application.id, []))
            for application in applications
        ],
    }
