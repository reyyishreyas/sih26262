"""FR-01 stubbed portal feed: the FR-01 field set with an "as of" timestamp.

PRD FR-01 (P0, APH cl. 2.3.1): "Receive each final-submitted application
with ID, PID, category, institution type, submission time, TER status,
documents". PRD §18 risk row: "Portal data not real-time | Scheduled sync
with 'as of' time on every screen". PRD line 341: the prototype uses a
**stubbed portal feed**; live portal integration is Release 1.

Safety properties under test:

- **It is a stub, and it says so.** Every response carries
  ``source: "stub"`` and an ``as_of`` timestamp (the sync/serve moment),
  so nothing built against it can mistake it for live portal data.
- **Nothing is invented.** PID, institution type and TER status are not
  modelled anywhere in this repo, so records carry ``null`` for them —
  never a guessed PID, never a claimed "TER paid". The config declares
  each FR-01 field with its modelling state, exactly like 2.3/2.4.
- **Read-only, scope-respected.** The feed is a GET over recorded
  final-submitted applications filtered by the caller's scope (an
  institution sees only its own cases; a Regional officer their region).
  It writes nothing and decides nothing — ingesting feed records into
  cases would need a portal service identity, which is a human approval
  gate, and is deliberately not implemented (open question).
"""

from __future__ import annotations

from app.models import Application
from app.services import portal_feed

# The seven FR-01 fields, in the PRD's own order (id, PID, category,
# institution type, submission time, TER status, documents).
FR01_FIELDS = [
    "application_id",
    "pid",
    "category",
    "institution_type",
    "submission_time",
    "ter_status",
    "documents",
]

# Submitted in the seed: app-main-0001, app-second-0002, app-existing-0003.
# app-draft-0004 is a draft (no submitted_at) and must never appear.
SUBMITTED = {"app-main-0001", "app-second-0002", "app-existing-0003"}


def _policy() -> dict:
    return portal_feed.portal_feed_policy()


# ------------------------------------------------------------- the config


def test_the_feed_config_loads_unverified_and_advisory():
    policy = _policy()
    assert policy["status"] == "unverified"
    assert policy["advisory_only"] is True


def test_it_cites_fr_01_clause_2_3_1_and_the_as_of_risk_row():
    policy = _policy()
    source = policy["source"]
    assert "FR-01" in source
    assert "2.3.1" in source
    assert "as of" in source or "as-of" in source
    assert source.startswith("md/1_PRD.md")


def test_it_declares_exactly_the_seven_fr_01_fields():
    declared = [entry["field"] for entry in _policy()["fields"]]
    assert declared == FR01_FIELDS


def test_the_unmodelled_fields_admit_what_is_missing():
    """PID, institution type and TER status are not recorded anywhere."""
    by_field = {entry["field"]: entry for entry in _policy()["fields"]}
    for field in ("pid", "institution_type", "ter_status"):
        assert by_field[field]["modelled"] is False, field
        assert by_field[field]["description"]
    for field in ("application_id", "category", "submission_time", "documents"):
        assert by_field[field]["modelled"] is True, field


def test_the_sync_cadence_is_not_invented():
    policy = _policy()
    assert policy["sync_cadence"] is None
    assert "placeholder" in policy["sync_cadence_note"].lower() or "not recorded" in (
        policy["sync_cadence_note"].lower()
    )


def test_the_note_admits_it_is_a_stub_and_names_the_ingestion_gap():
    note = _policy()["note"]
    assert "stub" in note.lower()
    assert "ingest" in note.lower() or "receive" in note.lower()


# --------------------------------------------- the feed (service level)


def _feed(db):
    """A globally-scoped caller, so the service tests see every case."""
    return portal_feed.build_feed(db, _GlobalAccess())


def test_the_feed_is_marked_as_a_stub_and_carries_the_as_of_time(db):
    body = _feed(db)
    assert body["source"] == "stub"
    # The fixed demo clock (conftest): 2026-10-22T09:00:00Z.
    assert body["as_of"].startswith("2026-10-22T09:00:00")
    assert body["status"] == "unverified"
    assert body["advisory_only"] is True


def test_only_final_submitted_appear_and_a_draft_never_does(db):
    body = _feed(db)
    ids = {record["application_id"] for record in body["records"]}
    assert ids == SUBMITTED


def test_every_record_carries_all_seven_fr_01_fields(db):
    body = _feed(db)
    assert body["records"], "the feed is empty — the seeded cases were not read"
    for record in body["records"]:
        assert list(record) == FR01_FIELDS


def test_unmodelled_fields_are_null_never_guessed(db):
    body = _feed(db)
    for record in body["records"]:
        assert record["pid"] is None
        assert record["institution_type"] is None
        assert record["ter_status"] is None  # never a claimed "paid"


def test_the_modelled_fields_carry_recorded_values(db):
    body = _feed(db)
    main = next(r for r in body["records"] if r["application_id"] == "app-main-0001")
    assert main["category"] == "new_technical"
    assert main["submission_time"].startswith("2026-10-")
    doc_types = {document["doc_type"] for document in main["documents"]}
    assert "lease_deed" in doc_types
    for document in main["documents"]:
        assert set(document) == {"doc_type", "file_name", "version", "status"}


def test_the_records_are_in_a_deterministic_order(db):
    ids = [r["application_id"] for r in _feed(db)["records"]]
    assert ids == sorted(ids)


def test_the_feed_writes_nothing(db):
    before = db.get(Application, "app-main-0001").baseline_version
    _feed(db)
    db.expire_all()
    assert db.get(Application, "app-main-0001").baseline_version == before


# ------------------------------------------------------------ the endpoint


def test_the_feed_endpoint_serves_the_stub_with_as_of(client, as_user):
    scrutiny = as_user("scrutiny@demo.local")
    res = client.get("/api/v1/portal/feed", headers=scrutiny)
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "stub"
    assert body["as_of"].startswith("2026-10-22T09:00:00")
    # Scrutiny's seeded scope is 'assigned' cases only, so the feed is
    # scoped, not global: app-second-0002 (a different institution, not
    # assigned to this officer) never appears.
    ids = {r["application_id"] for r in body["records"]}
    assert ids == {"app-main-0001", "app-existing-0003"}


def test_an_institution_sees_only_its_own_cases(client, as_user):
    college = as_user("institution@demo.local")
    body = client.get("/api/v1/portal/feed", headers=college).json()
    ids = {r["application_id"] for r in body["records"]}
    # The seeded demo institution owns app-main-0001 and app-existing-0003;
    # app-second-0002 belongs to a different institution and must not leak.
    assert ids == {"app-main-0001", "app-existing-0003"}
    assert "app-second-0002" not in ids


def test_a_regional_officer_sees_their_region_only(client, as_user):
    regional = as_user("regional@demo.local")
    body = client.get("/api/v1/portal/feed", headers=regional).json()
    ids = {r["application_id"] for r in body["records"]}
    assert ids and ids <= SUBMITTED
    assert ids != SUBMITTED  # the seeded cases span more than one region/scope


def test_the_feed_requires_authentication(client):
    res = client.get("/api/v1/portal/feed")
    assert res.status_code == 401


class _GlobalAccess:
    """A tiny stand-in for EffectiveAccess with global scope (service tests)."""

    def __init__(self):
        self.global_scope = True
        self.regions = set()
        self.institutions = set()
        self.committees = set()
        self.assigned_cases_only = False
        self.user_id = "test-user"
        self.permissions = set()

    def has(self, permission: str) -> bool:
        return False
