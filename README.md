# SIH26262 — AICTE Approval Workflow, Compliance Monitoring & Alert Management

Prototype for **SIH 2026 problem statement SIH26262**: *Integrated AICTE Approval
Workflow Automation, Compliance Monitoring and Alert Management System.*

The central idea is the **Approval Crash-Test**: before an officer takes a real
workflow action, they can rehearse hypothetical evidence changes against the same
immutable rule versions and get a **finding-level diff** — without the production
application being written to.

> AI extracts and explains evidence. Verified rules evaluate compliance.
> The workflow service controls real actions. The Rehearsal Engine tests
> hypothetical changes without modifying the real application.

---

## Status — what is real, what is mock

| Area | State | Notes |
|---|---|---|
| Compliance rule engine | **Implemented** | Allowlisted grammar, no `eval()`, typed outcomes, three-valued logic |
| Rule versioning | **Implemented** | Approved versions immutable; new versions are drafts |
| Workflow + guards | **Implemented** | Server-side role, state, document and rule guards |
| Audit trail | **Implemented** | SHA-256 hash chain, rejected and accepted actions, tamper detection |
| Approval Rehearsal Engine | **Implemented (prototype)** | Read-only baseline, copied snapshot, simulation-only writes, explicit `production_modified: false` |
| Rehearsal isolation in PostgreSQL | **Implemented and verified** | Four least-privilege roles; simulation tables in their own schema; proved by `make verify-isolation` |
| Rehearsal Load Factor | **Deliberately null** | Formula, units, edge cases and test matrix are not validated |
| Document upload + extraction | **Implemented with a mock adapter** | The mock does not read the file; values are canned and marked `simulated: true` |
| Evidence verification | **Implemented** | Per-field verify/reject, audited, bumps the baseline version and invalidates stale batches |
| Undertakings | **Implemented** | Submit and verify, due dates, overdue flag, feeds the alert scheduler |
| LLM evidence explanations | **Not wired** | Interface exists (`app/adapters/llm`); no model is called |
| Notification delivery | **Mock** | Real alert rows and delivery attempts; a JSON line is written to `storage/notifications.log` |
| Deadline scheduler | **Implemented** | Persistent worker, idempotent dedupe keys, retry path |
| Officer monitoring | **Implemented** | Server-enforced scope; dashboard/drill-down reconcile |
| Database | **PostgreSQL 16 in Compose, SQLite in dev/test** | Alembic migrations run on every stack start; the API never performs DDL |
| Frontend | **Implemented (review UI)** | Case list, findings, evidence, undertakings, rehearsal diff, transitions, audit, monitoring |
| Docker Compose | **Run here** | Full stack starts, migrates, seeds and serves; `make smoke` exercises it end to end |
| CI | **Written, not yet observed on GitHub** | Backend job + PostgreSQL isolation job; the repository is private and no run has been triggered |
| Historical state replay | **Not implemented** | The UI says "audit timeline", not "replay" |

All demo people, institutions, documents and outcomes are **synthetic**.
AICTE clause numbers are **not invented**: rules carry "clause mapping pending
verification" until a rule owner maps them to an exact APH clause.

---

## Quick start (the full stack, Docker)

```bash
make up            # PostgreSQL 16 + API + worker + frontend
# API    http://localhost:8000/docs
# UI     http://localhost:5173
```

`make up` builds the images, waits for PostgreSQL, runs Alembic as the schema
owner, applies the least-privilege grants, seeds the synthetic data and starts the
API and the worker. Then:

```bash
make smoke             # end-to-end API exercise against the running stack
make verify-isolation  # prove the PostgreSQL role contract
```

Sign in with any seeded demo account; password is **`DemoPassw0rd!`**.

| Email | Role | Scope |
|---|---|---|
| `institution@demo.local` | Institution representative | Own institution |
| `scrutiny@demo.local` | Scrutiny officer | Assigned cases |
| `regional@demo.local` | Regional officer | Northern Region |
| `evc@demo.local` | EVC member | Assigned committee |
| `supervisor@demo.local` | Supervisory officer | Northern Region (read-only monitoring) |
| `admin@demo.local` | Administrator | Global |

These credentials are for the synthetic demo only.

## Quick start (SQLite, no Docker)

```bash
cd backend
python3 -m venv ../.venv            # once
../.venv/bin/pip install -r requirements.txt
cp ../.env.example .env             # optional; defaults are safe for local use
../.venv/bin/python -m app.services.seed
../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the API and <http://localhost:8000/health>
for the injected clock and database status.

The demo clock is fixed by default to **2026-10-22T09:00:00Z** in `.env.example`
(`SIH_CLOCK_MODE=fixed`), so alert thresholds and ageing are reproducible.

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The API allows `http://localhost:5173` and `http://127.0.0.1:5173` by default.

> SQLite is fine for the UI walkthrough, but the rehearsal isolation is only
> **database-enforced** on PostgreSQL. Use the Compose stack to show that.

### Seeded cases

| ID | Situation |
|---|---|
| `app-main-0001` | New technical institution, in scrutiny. Lease valid to 2028-03-31; ownership record says 2027-03-31; affidavit missing |
| `app-second-0002` | Different institution, submitted. Shares a lease PDF hash with the main case; fields unverified |
| `app-existing-0003` | Existing institution in scrutiny, complete evidence, can be approved on the scrutiny-only route |
| `app-draft-0004` | Draft application, used for upload demos |

`app-main-0001` deliberately produces every typed outcome except
`NOT_APPLICABLE`-as-a-mistake:

| Rule | Outcome |
|---|---|
| `LEASE_VALID_COVERS_PERIOD` | `PASS` |
| `LEASE_ISSUING_AUTHORITY` | `PASS` |
| `REQUIRED_DOC_AFFIDAVIT` | `FAIL` (declared `missing_outcome=FAIL`) |
| `LEASE_DATE_CONSISTENCY` | `NEEDS_REVIEW` (2028-03-31 vs 2027-03-31) |
| `INSTITUTION_IDENTITY_MATCH` | `PASS` |
| `EXISTING_INSTITUTION_FACULTY_RATIO` | `NOT_APPLICABLE` |

---

## Tests

```bash
make test        # cd backend && ../.venv/bin/python -m pytest -q
# 82 passed
```

The suite covers rule semantics and immutability, workflow guards, rejected-action
auditing, hash-chain tampering, RBAC and scope, rehearsal isolation, alert dedupe
and boundaries, the evidence/institution/undertaking flows, and HTTP-level
behaviour. See [docs/ACCEPTANCE_TESTS.md](docs/ACCEPTANCE_TESTS.md) for the
claim-to-test map.

Alembic:

```bash
cd backend
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic upgrade head
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic check
```

---

## Docker Compose (PostgreSQL + API + worker + frontend)

```bash
make up            # or: docker compose up -d --build
make reset         # stop, delete the volumes and start fresh
```

**The API does not connect as the Postgres superuser.** The stack uses four
least-privilege roles:

| Role | Used by | Operational (`public`) | Simulation (`sim`) |
|---|---|---|---|
| `sih_migrator` | the `migrate` job | owns the schema (Alembic) | owns the schema |
| `app_rw` | API, worker | SELECT/INSERT/UPDATE/DELETE | no access |
| `sim_prod_ro` | API (rehearsal baseline) | SELECT only, read-only by default | no access |
| `sim_results_rw` | API (rehearsal results) | **no access** | SELECT/INSERT/UPDATE/DELETE |

Roles are created by [`backend/sql/bootstrap_roles.sql`](backend/sql/bootstrap_roles.sql)
and granted by [`backend/sql/roles.sql`](backend/sql/roles.sql); the migration job
applies both in order. `make verify-isolation` asserts the contract against the live
database:

```
  [PASS] sim_prod_ro: baseline reader cannot INSERT operational data (cannot execute INSERT in a read-only transaction)
  [PASS] sim_results_rw: results writer cannot SELECT operational data (permission denied for schema public)
  [PASS] app_rw: application role cannot reach the simulation schema (permission denied for schema sim)
```

The stack uses development credentials and mock adapters; this is not a production
deployment. See [Deferrals](docs/DEFERRALS.md) for the rest of the boundaries.

---

## Repository map

```
backend/
  app/
    api/          FastAPI routers (auth, applications, documents, compliance,
                  rehearsals, workflow, undertakings, alerts, audit, officer, admin,
                  institutions)
    core/         settings, injectable clock, three DB access paths, permissions,
                  PBKDF2 password hashing, JWT
    models/       SQLAlchemy models, including sim_* tables
    services/     rule engine, compliance, evidence, workflow, rehearsal, deadlines,
                  alerts, monitoring, authorisation, audit, policy, seed
    adapters/     OCR, LLM and notification interfaces + mock implementations
    workers/      persistent deadline/alert scheduler
  rules/          policy-as-data: compliance_rules.json, workflow_routes.json,
                  deadline_policy.json
  migrations/     Alembic environment and revisions
  scripts/        verify_isolation.py (live PostgreSQL role proof)
  sql/            bootstrap_roles.sql, roles.sql (least-privilege grants)
  tests/          82 tests
frontend/         React + TypeScript + Vite review UI
scripts/          smoke.sh (end-to-end API exercise)
docs/             architecture, rules, rehearsal, roles, data model, tests, demo
Makefile          up / down / reset / test / build / smoke / verify-isolation
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — three levels, request flow, isolation
- [User journey](docs/USER_JOURNEY.md) — the demo narrative end to end
- [Rules](docs/RULES.md) — grammar, three-valued logic, typed outcomes, immutability
- [Rehearsal engine](docs/REHEARSAL_ENGINE.md) — what isolation means and does not mean
- [Role model](docs/ROLE_MODEL.md) — permissions, scopes, backend enforcement
- [Data model](docs/DATA_MODEL.md) — tables, invariants, audit chain
- [Acceptance tests](docs/ACCEPTANCE_TESTS.md) — claims mapped to tests
- [Demo script](docs/DEMO_SCRIPT.md) — reproducible 10-minute walkthrough
- [Evidence intelligence](docs/EVIDENCE_INTELLIGENCE.md) — extract and explain, never decide
- [Deferrals](docs/DEFERRALS.md) — what is not built, and why

## Scope disclaimer

This is a working prototype, not a production system. It has not been security
audited, load-tested, or validated against the AICTE Approval Process Handbook by a
competent authority. Automated findings are decision support; the competent
authority decides.
