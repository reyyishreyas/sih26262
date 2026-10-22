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
| 1. Application intake | `documents.py`, `evidence_service` | uploads, extracted field candidates, verification |
| 2. Compliance | `compliance_service`, `rule_engine` | rule evaluation, typed findings, blocking set |
| 3. Workflow | `workflow_service` | transitions, guards, role/state checks |
| 4. Monitoring | `monitoring_service`, `officer_dashboard.py` | scoped pendency, ageing, escalations |
| 5. Alerts & undertakings | `deadline_service`, `alert_service` | threshold eligibility, dedupe, retries |
| 6. Audit | `audit_service` | append-only chain, timeline, integrity verification |

## Three database access paths

This is the structural part of the rehearsal promise. See
[REHEARSAL_ENGINE.md](REHEARSAL_ENGINE.md) for the behavioural contract.

| Path | Object | Purpose | Write capability |
|---|---|---|---|
| Operational | `SessionLocal` | All business writes | Full |
| Baseline reader | `open_readonly_session()` | Rehearsal reads production | **None** — `PRAGMA query_only=ON` (SQLite) or `SET TRANSACTION READ ONLY` (PostgreSQL) at the start of the session |
| Simulation writer | `open_sim_results_session()` → `SimResultsWriter` | Persists `sim_*` rows | **Only** `SimRun`, `SimInputSnapshot`, `SimRuleResult`, `SimMetric`; anything else raises `SimulationWriteViolation` |

In PostgreSQL deployments, `backend/sql/roles.sql` adds least-privilege roles:
`app_rw` (operational CRUD), `sim_prod_ro` (SELECT + `default_transaction_read_only`),
`sim_results_rw` (CRUD on `sim_*` tables only, no `public` schema usage). The
prototype runs on one SQLite file, where the connection-level read-only pragma and
the writer type guard carry the same guarantee.

## Request lifecycle

A guarded workflow transition (`POST /api/v1/applications/{id}/transitions`):

1. **Authenticate** — bearer JWT, HS256, subject is the user id.
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
recomputes the chain and reports the first broken sequence number. Deleting or
editing an event is detectable.

This is tamper-**evident**, not tamper-proof: an attacker with full database and
code access could rewrite the chain. Anchoring the head outside the database (WORM
storage or a signed external log) is a deployment hardening step, not implemented.

## Frontend

`frontend/` is a Vite React TypeScript review UI with no state-management library:

- case list filtered by the server;
- findings table with typed outcome badges, blocking state, missing/unverified
  inputs;
- crash-test panel: JSON evidence overrides, finding-level diff, workflow
  implications, explicit `production_modified: false`;
- transition controls that submit the reason and display guard refusals;
- audit timeline and chain verification badge;
- officer monitoring dashboard and alert list.

The UI checks permissions only to avoid showing dead controls. Every endpoint
re-checks permission and scope.

## Configuration

All settings use the `SIH_` prefix (`app/core/config.py`): database URLs, simulation
URLs, JWT secret, password-hash iterations, clock mode, storage directory, upload
limits, CORS origins, seed-on-startup. `.env.example` documents them.

## Known architectural limits

- SQLite in dev means no row-level locks equivalent to PostgreSQL; the writer guard
  is a code-level type check, not a database permission. The Postgres role script is
  the deployment path.
- The simulation baseline is read in a separate session, but operational writes are
  not blocked for the duration of a rehearsal. The baseline version is recorded, and
  a run can be flagged superseded if evidence changes; it is not a serialisable
  snapshot transaction.
- No message broker; the worker polls. Adequate at prototype scale, not at national
  scale.
- Audit hash chain is per database, not per region. Multi-tenant sharding is out of
  scope.
