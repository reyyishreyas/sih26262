# Data Model

SQLAlchemy 2.x models, SQLite in development, PostgreSQL-ready. The Alembic
revisions start at `backend/migrations/versions/075aed043fd2_initial_schema.py`
and now number 31 heads-walked revisions (transition/deficiency/EVC/SHC tables,
finding dispositions, conflict-of-interest, the four-eyes policy-config history,
the verified-appeal workflow, one-time reopening, consolidated grant batches,
extracted-field claim/grounding/provenance-bbox-engine columns, regulatory
status and the Phase 9.2 undertaking notice/evidence columns);
`alembic check` reports no drift against the models on SQLite and PostgreSQL
(verified 2026-10-28 in CI and on the Compose stack, IMPL-0077).

Identifiers are strings (UUID-shaped), timestamps are stored in UTC (`DateTime
(timezone=True)`; SQLite returns naive values, normalised by `to_utc`).

## Schemas

| Schema | Contents | PostgreSQL role that may write |
|---|---|---|
| `public` | Every operational table | `app_rw` |
| `sim` | `sim_*` tables only | `sim_results_rw` |

`sim` is created by migration `0002_sim_schema` when `SIH_SIMULATION_SCHEMA=sim`
(the Compose stack sets it). SQLite has no schemas, so in development and tests the
simulation tables sit in `public` and isolation is enforced by the read-only
baseline connection plus the `SimResultsWriter` type guard instead of by database
permissions.

Operational tables reference each other only. No foreign key points from an
operational table to a simulation table, so a rehearsal failure cannot strand an
application, and the simulation role never has to resolve an operational table.

## Identity and access

| Table | Purpose | Invariants |
|---|---|---|
| `users` | Accounts, PBKDF2 password hash, active flag, `password_changed_at` token marker | Email unique |
| `login_attempts` | Hashed account/address and address keys, timestamp, success flag | Indexed by `(key_hash, attempted_at)`; pruned on write |
| `roles` | Six role names | Name unique |
| `permissions` | Permission catalogue | Code unique |
| `role_permissions` | Role → permission | DB copy of the policy matrix |
| `user_role_assignments` | Role with scope (`global`/`region`/`institution`/`committee`/`assigned`), `revoked_at` | Active = not revoked or `revoked_at > now` |
| `jurisdiction_assignments` | Extra regional authority | Unique per user + region |
| `case_assignments` | Case to officer or committee, `revoked_at` | Active assignments grant scope |

Permissions and scope are resolved on every request from these rows. Nothing is
cached in the token beyond the user id.

## Institution, application, evidence

| Table | Purpose |
|---|---|
| `regions` | Region code/name |
| `institutions` | AICTE id, name, region |
| `applications` | Category, route, cycle, `current_state`, `status`, assigned officer, **`baseline_version`**, state-since, submitted-at |
| `documents` | Document type, file name, SHA-256, perceptual hash, storage ref, version |
| `extracted_fields` | One field per document version: value, source page/span, method, confidence, `verification_status`, verifier; claim/grounding/provenance columns (Phase 5.x): candidate `bbox` JSON (origin/level), `grounded_*` fields and `engine`/`engine_version` for how a value was read (pypdf, Tesseract, Gemini, mock, grounded lease) |
| `committees` | EVC committees |
| `grant_batches` / `grant_entries` (Phase 6.8) | Consolidated grant lookup: batch + guarded per-establishment entries, immutable published versions |

`applications.baseline_version` is bumped on document upload, field verification,
undertaking changes and accepted transitions. A rehearsal records the version it
read; if it changed during the run, the run is marked `superseded`.

`extracted_fields` is deliberately not authoritative. Rules see the field value and
its verification status; an unverified value cannot produce a `PASS`.

`documents.file_sha256` is indexed so exact duplicates can be detected. The seeded
`app-second-0002` shares a lease hash with `app-main-0001`. Perceptual-hash similarity
is stored but **not** used for decisions yet — there is no duplicate-document finding
rule in the prototype.

## Rules

| Table | Purpose |
|---|---|
| `rules` | Stable rule key, title, description, regulatory reference |
| `rule_versions` | Immutable approved versions: applicability, condition, three outcomes, blocking, severity, effective dates, content hash, approval metadata |
| `rule_tests` | Named input/expected-output cases per version (schema only in this prototype) |

`rule_versions` is unique on `(rule_id, version)`. The ORM guard rejects updates to
an approved/retired version; drafting v2 is the only path. See [RULES.md](RULES.md).

## Workflow

| Table | Purpose |
|---|---|
| `workflow_transition_defs` | Route + action + from/to state, required permission, allowed roles, required rules/documents, reason flag |
| `workflow_transitions` | Append-only record of attempted transitions with outcome and actor |

Definitions are seeded from `backend/rules/workflow_routes.json`. Route tables are
configuration: changing a stage SLA or guard is a data change.

## Compliance and monitoring

| Table | Purpose |
|---|---|
| `rule_evaluations` | Persisted operational finding: rule key/version, batch id, outcome, explanation, evidence refs, missing inputs, unverified inputs, denormalised rule title/severity/regulatory reference, baseline version, timestamp |
| `undertakings` | Post-approval obligations with due date, status, reminder policy; Phase 9.2 adds `obligation_key`, the officer-recorded `source_received_on` notice date, `source_document_id` and linked `evidence_document_ids` |
| `alerts` | One logical alert, **unique `dedupe_key`**; `security_deposit_due` rides the same table with its own PRD-sourced ladder (Phase 9.2) |
| `alert_deliveries` | Attempt per channel, status, error, provider reference; unique `(alert_id, channel, attempt)` |
| `deficiencies` (Phase 4) | Deficiency records with draft→open lifecycle and dispositions |
| `evc_visits`, SHC/SAC hearing rows (Phases 6.2–6.4) | Scheduled visits/hearings with mode, confirmation, reports |
| `conflict_of_interest` (Phase 6.3) | Member COI declarations per case |
| `appeals` (Phase 6.6) | One per decided case: window (7-working-day), hearing, SAC recommendation, Council decision, decision document, all with timestamps |
| `reopening_requests` (Phase 7.3) | One-time opening of a rejected/auto-eligible case with re-verification envelope |
| `policy_config_versions` (Phase 9.4) | Four-eyes editable policy JSON: draft → approved, content hash, proposer/approver ids, immutable approved snapshots |

`rule_evaluations` deliberately stores the rule key and version rather than a foreign
key to a mutable rule row, so historical findings remain interpretable after a rule
is retired. It also stores a copy of the rule's **title, severity and regulatory
reference** as they were at evaluation time, so the review UI can explain a stored
finding without re-reading a rule version that may since have been superseded. The
version number remains the authoritative link.

A stored batch is a snapshot: it records the application baseline version it was
computed from. If evidence or workflow state changed since then, the compliance
endpoint recomputes instead of returning stale findings.

## Audit

| Table | Purpose |
|---|---|
| `audit_events` | Append-only: seq, at, actor, role, action, entity, outcome, reason, before/after JSON, request id, `prev_hash`, `hash` |
| `audit_chain_head` | Singleton (`id=1`) with `last_seq` and `last_hash`; locked during append |

The hash covers the previous hash plus a canonical JSON body. Editing or deleting an
event breaks verification at that sequence number. This is tamper-evident, not
tamper-proof against someone with full database and code access.

Document-content access, extraction outcomes, case assignment, finding-batch
evaluation, explicit chain verification, case-audit export, appeal steps
(submit/rejection/hearing/SAC/Council — accepted and refused; Phase 6.6),
reopening decisions, report exports and the four-eyes policy-config
draft/approve lifecycle all have named event actions (verified across the
committed test files; Phase 8.1 closed for implemented flows, IMPL-0068).
The case export still contains only scoped events and a server-side
verification result; it cannot independently verify the global chain without
revealing other cases' events.

## Simulation storage

| Table | Schema | Purpose |
|---|---|---|
| `sim_runs` | `sim` | Run id, application, actor, status, baseline version, rule set version, superseded |
| `sim_input_snapshots` | `sim` | Baseline snapshot, overrides and assumptions actually used |
| `sim_rule_results` | `sim` | Before/after outcome per rule with change classification |
| `sim_metrics` | `sim` | Metric name, nullable value, formula version, inputs. `load_factor` is stored as `NULL` with `formula_version=NULL` |

These tables are written only through `SimResultsWriter`, which connects as
`sim_results_rw` in PostgreSQL. That role has `USAGE` on `sim` and no `USAGE` on
`public`.

## Relationship sketch

```
regions ─┬─ institutions ─── applications ─┬─ documents ─── extracted_fields
         └─ committees                      ├─ undertakings
                                            ├─ rule_evaluations
                                            ├─ workflow_transitions
                                            └─ alerts ─── alert_deliveries

users ─┬─ user_role_assignments ── roles ── role_permissions ── permissions
       ├─ jurisdiction_assignments
       ├─ case_assignments ─────────┘
       └─ audit_events (actor_id)

applications ── sim_runs ─┬─ sim_input_snapshots
                          ├─ sim_rule_results
                          └─ sim_metrics
```

## Retention and lifecycle

Not implemented, and called out so it is not assumed:

- no archival or retention policy; audit and evaluation rows grow without bound;
- no soft-delete for applications or documents;
- no partition or index strategy for national-scale volumes;
- no field-level encryption at rest (deployment responsibility);
- no database trigger enforcing rule immutability (ORM guard only);
- uploaded file bytes are written under `SIH_STORAGE_DIR` with no malware scan and no
  signed-URL download endpoint.
