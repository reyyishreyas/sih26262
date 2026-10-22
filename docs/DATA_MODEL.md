# Data Model

SQLAlchemy 2.x models, SQLite in development, PostgreSQL-ready. The Alembic
revisions are `backend/migrations/versions/075aed043fd2_initial_schema.py`,
`0002_sim_schema_and_finding_labels.py` and `0003_auth_hardening.py`;
`alembic check` reports no drift against the models on SQLite and PostgreSQL.

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
| `extracted_fields` | One field per document version: value, source page/span, method, confidence, `verification_status`, verifier |
| `committees` | EVC committees |

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
| `undertakings` | Post-approval obligations with due date, status, reminder policy |
| `alerts` | One logical alert, **unique `dedupe_key`** |
| `alert_deliveries` | Attempt per channel, status, error, provider reference; unique `(alert_id, channel, attempt)` |

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
