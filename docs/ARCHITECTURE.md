# Architecture

## One engine, six modules

The platform is a single FastAPI service with one policy engine shared by six
modules. The modules are not separate services; they share the rule engine, the
clock and the audit chain on purpose.

```
React + TypeScript review UI
        │  HTTPS, bearer token
        ▼
FastAPI  ── auth / RBAC + scope ──►  workflow service  ──►  operational DB (app_rw)
   │                                  ▲
   │                                  │ reads verified evidence only
   ├── compliance service ──► rule engine (approved rule versions)
   │
   ├── rehearsal service ──► read-only baseline ──► sim_results writer ──► sim_* tables
   │
   ├── deadline service ◄── persistent worker (DB is the queue)
   │        └── alert service ──► notification adapter (mock in this prototype)
   │
   └── audit service ──► hash-chained audit_events + audit_chain_head
```

| Module | Service | What it owns |
|---|---|---|
| 1. Application intake | `documents.py`, `evidence_service` | uploads, extracted field candidates with page/bbox provenance (Phase 5.2), verification |
| 2. Compliance | `compliance_service`, `rule_engine` | rule evaluation, typed findings, blocking set, advisory precheck/site/crosschecks |
| 3. Workflow | `workflow_service` | transitions, guards, role/state checks |
| 4. Monitoring | `monitoring_service`, `officer_dashboard.py` | scoped pendency, ageing, escalations |
| 5. Alerts & undertakings | `deadline_service`, `alert_service` | threshold eligibility, dedupe, retries, per-obligation ladders (`security_deposit_due`, Phase 9.2) |
| 6. Audit | `audit_service` | append-only chain, timeline, integrity verification |
| 7. Appeals | `appeals.py`, `appeal_service` (Phase 6.6) | APH Ch. II §2.24 window, SAC recommendation, Council decision — audited both ways |
| 8. Grants & EVC | `evc.py`, `grants.py` (Phase 6.2/6.8) | visits, scanned-intake rows, guard-railed grant lookup |
| 9. Policy console | `policy_config.py` (Phase 9.4) | four-eyes editable deadline/policy snapshots; approved versions feed the live sweep |

`app/main.py` mounts 23 routers under `settings.api_prefix`; reports
 (`reports.py`, Phase 7.4) and reopening (`reopening.py`, Phase 7.3) ride the
 same auth/scope/audit stack.

## Three database access paths

This is the structural part of the rehearsal promise. See
[REHEARSAL_ENGINE.md](REHEARSAL_ENGINE.md) for the behavioural contract.

| Path | Object | Purpose | Write capability |
|---|---|---|---|
| Operational | `SessionLocal` | All business writes | Full |
| Baseline reader | `open_readonly_session()` | Rehearsal reads production | **None** — `PRAGMA query_only=ON` (SQLite) or `SET TRANSACTION READ ONLY` (PostgreSQL) at the start of the session |
| Simulation writer | `open_sim_results_session()` → `SimResultsWriter` | Persists `sim_*` rows | **Only** `SimRun`, `SimInputSnapshot`, `SimRuleResult`, `SimMetric`; anything else raises `SimulationWriteViolation` |

### The PostgreSQL role contract

In PostgreSQL the three paths are three different database roles, and the database
— not the application — refuses the forbidden operation:

| Role | `public` (operational) | `sim` (simulation) | Transaction default |
|---|---|---|---|
| `app_rw` | SELECT/INSERT/UPDATE/DELETE | no access | read/write |
| `sim_prod_ro` | SELECT only | no access | **read-only** (`default_transaction_read_only=on`) |
| `sim_results_rw` | **no access** | SELECT/INSERT/UPDATE/DELETE | read/write |
| `sih_migrator` | owns the schema (Alembic) | owns the schema | read/write |

- `backend/sql/bootstrap_roles.sql` creates the four roles (dev credentials; runs
  from `/docker-entrypoint-initdb.d/` on a fresh volume).
- `backend/sql/roles.sql` applies the grants after migrations, including
  `ALTER DEFAULT PRIVILEGES` so tables created by later migrations inherit them.
- `backend/scripts/verify_isolation.py` asserts the contract against a running
  database. It is part of `make verify-isolation` and of CI.

Simulation tables live in the dedicated `sim` schema (`SIH_SIMULATION_SCHEMA=sim`,
migration `0002_sim_schema`). `sim_results_rw` has `USAGE` on `sim` and **no**
`USAGE` on `public`, so it cannot resolve an operational table name even if the
application code asks for one.

In the default **SQLite** development configuration all three paths point at one
file and isolation rests on the read-only pragma plus the writer type guard. Use
the Compose stack for database-enforced isolation.

### Who connects as what

| Process | Database identity |
|---|---|
| `migrate` job | `sih_migrator` for Alembic, then the superuser for the grants (a role cannot grant what it does not own) |
| `api` | `app_rw`, plus `sim_prod_ro` and `sim_results_rw` for the rehearsal paths |
| `worker` | `app_rw` |

The API never performs DDL. `create_all()` is SQLite-only by design: starting a
production-shaped deployment must not mutate the schema as a side effect of a web
process starting.

## Request lifecycle

A guarded workflow transition (`POST /api/v1/applications/{id}/transitions`):

1. **Authenticate** — bearer JWT, HS256, issuer/audience/nbf checked, subject is
   the user id, and a `pwd` marker binds the token to the current password hash.
2. **Authorise** — the required permission (e.g. `case.transition`) is checked
   server-side; the UI hiding a button is irrelevant.
3. **Scope** — `require_application` evaluates a SQL scope filter (global, region,
   institution, committee, or assigned cases only). Out-of-scope records return
   **404**, not 403, so the API does not confirm that a case exists.
4. **Resolve the transition definition** — route key + action + current state.
5. **Evaluate guards** — role, state, required documents, required rules. Rule
   outcomes other than `PASS`/`NOT_APPLICABLE` block and are named in the refusal.
6. **Apply or reject**
   - accepted: state change + audit event in one transaction, then commit;
   - rejected: the business transaction is rolled back and the refusal is written
     and committed on its own, so a rejected action is never lost.
7. **Return** HTTP 200 with `accepted: false` for a guard refusal. 404 is reserved
   for out-of-scope cases; 422 for rejected rehearsal overrides; 400 for an invalid
   rule definition.

### HTTP hardening layer

Before routing, middleware assigns or validates `X-Request-ID` (client value must
match a safe pattern, otherwise a generated id replaces it) and binds it to the
request context. It emits `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, HSTS in production, and `Cache-Control: no-store` for API and
health paths. The access log is one JSON object per request with the request id,
method, path, status, duration and client address; application logs inherit the
same id. Unhandled exceptions return a typed error envelope without a traceback;
validation errors return `code: validation_error` with the request id.

`TrustedHostMiddleware` and an explicit CORS allowlist are configured from
settings. Production validation rejects wildcards. List endpoints accept
`limit`/`offset` (maximum 500) and return `X-Total-Count`. `/health/live` is a
process check; `/health/ready` executes probe queries on the operational,
rehearsal-reader and rehearsal-writer roles and returns `503` if any fail.

Sign-in throttling is persisted in `login_attempts`, keyed by a hash of
account+address and separately by address. It therefore survives restarts and is
shared across API replicas; it is not an in-process counter.

## Deterministic time

Nothing stores a "due" flag. Deadlines are always `f(now, entered_at, policy)` via
`app/core/clock.py`. The clock is configuration (`system`, `fixed`, `offset`); tests
and the recorded demo use `fixed`. Consequences:

- a sweep can be re-run at any point without double-firing (dedupe keys);
- threshold boundaries can be tested exactly;
- the demo does not depend on the calendar.

The scheduler is a separate process (`python -m app.workers.scheduler`) that
re-queries the database every tick. There is no in-process timer and no broker: the
database is the queue, and restarting the worker loses nothing.

Reminder ladders live in `rules/deadline_policy.json` (offsets relative to each
obligation's due date, never absolute dates). Since Phase 9.4/9.5 an approved
policy-config snapshot can replace the file-derived thresholds at runtime: an
admin edits a ladder, a *different* administrator approves the immutable version,
and the live sweep picks it up — a fixed-clock integration test proves the same
due date moves from "no reminder yet" to firing after approval.

## Rule evaluation

`app/services/rule_engine.py` compiles each stored condition into an internal
operator. Stored expressions are data, not Python; there is no `eval()` and no
attribute access. Operators are allowlisted (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`,
`in`, `between`, `contains`, `exists`, `missing`, `and`, `or`, `not`, `always`).

Evaluation is three-valued: true, false, or `unknown`. Missing evidence and
unverified evidence are tracked separately and produce typed outcomes according to
the rule's declared `missing_outcome`, `unverified_outcome` and `failure_outcome`.
The grammar and semantics are in [RULES.md](RULES.md).

## Audit

`AuditEvent` rows are chained: each hash covers the previous hash plus a canonical
JSON body. `AuditChainHead` is locked during append. `GET /api/v1/audit/verify`
recomputes the chain without a write; `POST /api/v1/audit/verify` records an
explicit check and reports the first broken sequence number. Deleting or editing
an event is detectable. Case-scoped exports are available at
`GET /api/v1/applications/{id}/audit/export`; the server verifies the complete
chain before and after recording the export event. The export includes only the
authorized case's events, so it is not independently verifiable without other
cases' events.

Successful document-content reads and extraction outcomes are recorded without
document contents. Compliance batch evaluations and automatic case hand-offs are
also audited in the same transaction as their associated write. The timeline
remains a scoped event list, not a historical state replay. Every appeal step
(submit, rejection, hearing, representatives, SAC recommendation, Council
decision — accepted and refused) is audited (Phase 6.6), as are grants decisions,
reopening decisions and report exports (Phase 7). Policy-config drafts and
approvals under the four-eyes console are audited with content hashes (Phase
9.4); the Security-Deposit proof undertaking records who provisioned it, who
submitted the evidence and who verified it (Phase 9.2).

This is tamper-**evident**, not tamper-proof: an attacker with full database and
code access could rewrite the chain. Anchoring the head outside the database (WORM
storage or a signed external log) is a deployment hardening step, not implemented.

## Frontend

`frontend/` is a Vite React TypeScript review UI with no state-management library:

- case list filtered by the server;
- findings table with typed outcome badges, blocking state, missing/unverified
  inputs, and the rule title/severity/regulatory reference captured when the
  finding was stored;
- evidence panel: upload a new version, review extracted candidates with page,
  method, confidence and highlight boxes (Phase 5.2/5.5+), verify or reject each
  field; every verification bumps the baseline version and triggers a
  recomputation; demo exit-check flows (EoA/NOC/resolution) show amber
  mismatch badges and deficiency-candidate labels with confirm/dismiss;
- undertakings panel: submit an undertaking with evidence notes linked to
  same-case documents (Phase 9.2), verify it (officer), overdue items flagged;
  the Security-Deposit proof undertaking carries the officer-recorded notice
  date and linked document;
- draft-application form for roles that may open a case;
- crash-test panel: JSON evidence overrides, finding-level diff, workflow
  implications, explicit `production_modified: false`;
- transition controls that submit the reason and display guard refusals; actions
  the caller lacks the permission for are shown as unavailable with the reason;
- appeal panel and committee workspaces (Phase 6.6/6.7): window display,
  hearing scheduling, recommendation and decision recording with refusal
  reasons surfaced;
- grant panels (Phase 6.8) and reports view (Phase 7.4) with export formats;
- admin policy console (Phase 9.4): four-eyes JSON drafts — one administrator
  proposes, a different one approves — with version history and hashes;
- audit timeline and chain verification badge;
- officer monitoring dashboard and alert list.

The UI checks permissions only to avoid showing dead controls. Every endpoint
re-checks permission and scope.

## Configuration

All settings use the `SIH_` prefix (`app/core/config.py`): database and simulation
URLs, pool/timeouts, JWT secret/issuer/audience, password policy and iteration
count, sign-in throttling, clock mode, storage directory, upload limits, CORS
origins, allowed hosts, HSTS, docs toggle, log level/format, seed-on-startup.
`.env.example` documents them. `Settings` runs production-only validation at
startup: weak JWT secrets, SQLite, wildcard CORS/hosts, seeding, fixed clock,
debug, short HSTS and low PBKDF2 iterations are fatal when `SIH_ENV=production`.

## Known architectural limits

- SQLite in dev means no row-level locks equivalent to PostgreSQL; there the writer
  guard is a code-level type check, not a database permission. The PostgreSQL role
  script is the deployment path and is exercised by `make verify-isolation`.
- The baseline and the simulation results share one PostgreSQL **instance**; they
  are separated by schema and by role. A separate instance would be a stronger
  boundary.
- The simulation baseline is read in a separate session, but operational writes are
  not blocked for the duration of a rehearsal. The baseline version is recorded, and
  a run can be flagged superseded if evidence changes; it is not a serialisable
  snapshot transaction.
- No message broker; the worker polls. Adequate at prototype scale, not at national
  scale.
- Audit hash chain is per database, not per region. Multi-tenant sharding is out of
  scope.
