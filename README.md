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

**New here, or handing this to an AI agent? Read [`CONTEXT.md`](CONTEXT.md)
first** — the full map of what is built, what is deliberately missing, the demo
logins, the conventions, and the current build order. The next feature lives in
[`things.md`](things.md).

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
| Document upload + extraction | **Implemented** | Real reader: pypdf text layer, Tesseract OCR for scans and photos. Values are unverified until a human confirms them; a mock reader stays selectable for tests |
| Evidence verification | **Implemented** | Per-field verify/reject, audited, bumps the baseline version and invalidates stale batches |
| Undertakings | **Implemented** | Submit and verify, due dates, overdue flag, feeds the alert scheduler |
| LLM evidence explanations | **Interface not wired** | `app/adapters/llm` (Protocol + mock) is built but unused; the one live model call is `services/grounded_lease_extractor.py` for `lease_agreement` documents — Gemini when `SIH_GEMINI_API_KEY` is set, otherwise a deterministic parser that cites the document verbatim |
| Notification delivery | **Mock** | Real alert rows and delivery attempts; a JSON line is written to `storage/notifications.log` |
| Deadline scheduler | **Implemented** | Persistent worker, idempotent dedupe keys, retry path |
| Officer monitoring | **Implemented** | Server-enforced scope; dashboard/drill-down reconcile |
| Database | **PostgreSQL 16 in Compose, SQLite in dev/test** | Alembic migrations run on every stack start; the API never performs DDL |
| Frontend | **Implemented (review UI)** | Case list, findings, evidence, undertakings, rehearsal diff, transitions, audit, monitoring |
| Docker Compose | **Run here** | Full stack starts, migrates, seeds and serves; `make smoke` exercises it end to end |
| Production-shaped deployment | **Implemented** | Multi-stage non-root images, `docker-compose.prod.yml`, nginx prod build, required secrets, fail-fast production config |
| API hardening | **Implemented** | JSON logs, request ids, security headers, bounded pagination, upload signature checks, typed error envelope |
| Sign-in protection | **Implemented** | PBKDF2-SHA256, JWT issuer/audience, persisted account/address throttling, password change revokes old tokens |
| Sign-in channel | **UI only** | `POST /auth/login` returns 403 to anything that does not carry the sign-in screen's origin (curl, an API explorer); `/docs` and `/openapi.json` are off unless `SIH_DOCS_ENABLED=true` |
| Health and readiness | **Implemented** | `/health/live`, `/health/ready`, database probes for all three roles |
| CI | **Implemented and green** | GitHub Actions: Ruff, SQLite Alembic check, the full test suite, PostgreSQL role isolation, frontend production build ([verified run](https://github.com/reyyishreyas/sih26262/actions)) |
| Historical state replay | **Not implemented** | The UI says "audit timeline", not "replay" |

All demo people, institutions, documents and outcomes are **synthetic**.
AICTE clause numbers are **not invented**: rules carry "clause mapping pending
verification" until a rule owner maps them to an exact APH clause.

---

## Quick start — 5 minutes

You need **Python 3.10+** and **Node 20+**. Nothing else — no Docker, no
database server, no configuration to write.

```bash
git clone https://github.com/reyyishreyas/sih26262.git
cd sih26262
make setup    # ~1 min: packages, config, demo database (safe to re-run)
make dev      # starts the API and the UI together
```

Then open **<http://localhost:5173>** and sign in. Both logins are printed
on the sign-in panels — type the email and password shown there (they are
the demo accounts below) and press **Sign in**.

`make dev` prints `[ok] API` and `[ok] UI` when both are up, streams both
logs in one terminal, and stops everything on **Ctrl-C**. If a port is
already in use it says so instead of failing halfway.

That is the whole loop: **setup once, `make dev` after that.**

### Demo logins

| Panel | Email | Password |
|---|---|---|
| I am the College | `institution@demo.local` | `DemoPassw0rd!` |
| I am the Checker | `scrutiny@demo.local` | `DemoPassw0rd!` |

Other checker roles (`regional@`, `evc@`, `supervisor@`, `admin@demo.local`)
are behind **“Sign in as a different checker role”** — pick one, the form
fills in its email, type the same password. These credentials are for the
synthetic demo only.

### If something is wrong

| Symptom | Fix |
|---|---|
| `make: No rule to make target 'setup'` | You are in the wrong directory, or on an old checkout — `git pull` |
| `Port 8000/5173 already in use` | A previous run is still up: `lsof -ti:8000 \| xargs kill` (same for 5173) |
| Empty case list / stale data | Re-seed: `make seed` (idempotent, keeps nothing you would miss) |
| Want a brand-new demo state | `rm backend/sih26262.db && make setup` |
| `make dev` says setup is missing | Run `make setup` first |
| Scanned PDFs are not OCR'd | Optional: `brew install tesseract` (macOS) / `apt install tesseract-ocr`. PDFs with a text layer work without it |
| Tests fail after pulling | Re-run `make setup` — dependencies may have changed |

### Other ways to run

**Docker (full stack, PostgreSQL 16):**

```bash
make up            # PostgreSQL + API + worker + frontend
# API    http://localhost:8000  (explorer /docs is off unless SIH_DOCS_ENABLED=true)
# UI     http://localhost:5173
```

`make up` builds the images, waits for PostgreSQL, runs Alembic as the schema
owner, applies the least-privilege grants, seeds the synthetic data and starts the
API and the worker. Then:

```bash
make smoke             # end-to-end API exercise against the running stack
make verify-isolation  # prove the PostgreSQL role contract
```

Sign in with any seeded demo account; password is **`DemoPassw0rd!`** (table above).

The API allows `http://localhost:5173` and `http://127.0.0.1:5173` by default.

The demo clock is fixed by default to **2026-10-22T09:00:00Z** in `.env.example`
(`SIH_CLOCK_MODE=fixed`), so alert thresholds and ageing are reproducible.

> SQLite (what `make setup` uses) is fine for the UI walkthrough, but the
> rehearsal isolation is only **database-enforced** on PostgreSQL. Use the
> Compose stack to show that.

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
make lint        # ruff check app tests migrations scripts
make test        # cd backend && ../.venv/bin/python -m pytest -q
# 492 passed
```

The suite covers rule semantics and immutability, workflow guards, rejected-action
auditing, hash-chain tampering, RBAC and scope, rehearsal isolation, alert dedupe
and boundaries, the evidence/institution/undertaking flows, HTTP-level behaviour,
password-change invalidation, persisted sign-in throttling, the UI-only sign-in
channel, upload signature and
path checks, bounded pagination, structured errors and production-config
validation. See [docs/ACCEPTANCE_TESTS.md](docs/ACCEPTANCE_TESTS.md) for the
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

On the demo stack, [`backend/sql/bootstrap_roles.sql`](backend/sql/bootstrap_roles.sql)
runs from the PostgreSQL init directory on a fresh volume; the `migrate` job then
runs Alembic and applies [`backend/sql/roles.sql`](backend/sql/roles.sql). The
production Compose file runs bootstrap as a one-shot job with passwords injected
from the environment instead of the committed development defaults.
`make verify-isolation` asserts the contract against the live database:

```
  [PASS] sim_prod_ro: baseline reader cannot INSERT operational data (cannot execute INSERT in a read-only transaction)
  [PASS] sim_results_rw: results writer cannot SELECT operational data (permission denied for schema public)
  [PASS] app_rw: application role cannot reach the simulation schema (permission denied for schema sim)
```

The demo stack uses development credentials and mock adapters on purpose. For a
deployment-shaped stack with required secrets, non-root images, no fixed clock and
no startup seeding:

```bash
cp .env.production.example .env.production
# replace every placeholder, then:
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

The API refuses to start with `SIH_ENV=production` if the JWT secret is weak, the
database is not PostgreSQL, the isolated rehearsal URLs or schema are missing, a
rehearsal connection reuses the API's database role, CORS or allowed hosts are
wildcards, seeding is enabled, the clock is fixed, debug is on, or HSTS is shorter
than one year. Read
[docs/PRODUCTION.md](docs/PRODUCTION.md) before deploying: it covers secrets, TLS,
backups, monitoring, scaling and the boundaries that remain.

---

## Production operations

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | process liveness; no database dependency |
| `GET /health/ready` | readiness; probes the operational, rehearsal-reader and rehearsal-writer roles, returns 503 when any fail |
| `GET /health` | human-readable status, clock, environment, database role and component probes |

Every response carries `X-Request-ID` (a safe client value is echoed, otherwise one
is generated), security headers and `Cache-Control: no-store` for API/health paths.
Logs are JSON by default with the request id, method, path, status and duration.
List endpoints are bounded (`limit`/`offset`, maximum 500) and report
`X-Total-Count`.

Failed sign-ins are counted per account/address and per address in the database;
five failures return `429` with `Retry-After`. `POST /api/v1/auth/change-password`
enforces a 12-character letter-and-digit policy and invalidates previously issued
tokens. `POST /api/v1/auth/login` writes accepted and rejected attempts to the
hash-chained audit log, and only answers requests that carry the sign-in screen's
origin (`SIH_CORS_ORIGINS`, or the API's own host in a same-origin deployment) —
anything else gets `403 "Sign-in is only available from the application's
sign-in screen."` and is refused *before* the throttle, so a script cannot spend
a real account's lockout budget. That is a channel rule, not a security
boundary: an HTTP client can copy an `Origin` header, which is why the password
check, the persisted throttling and the signed token remain the defences that
matter.

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
  tests/          704 tests
frontend/         React + TypeScript + Vite review UI; Dockerfile.prod + nginx.conf
scripts/          setup.sh (one-time setup), dev.sh (start both servers), smoke.sh
docs/             architecture, rules, rehearsal, roles, data model, tests, production
Makefile          setup / dev / up / down / reset / lint / test / build / smoke / verify-isolation
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
- [Production](docs/PRODUCTION.md) — deployment, secrets, TLS, backups, monitoring
- [Deferrals](docs/DEFERRALS.md) — what is not built, and why

## Scope disclaimer

This is a working prototype, not a production system. It has not been security
audited, load-tested, or validated against the AICTE Approval Process Handbook by a
competent authority. Automated findings are decision support; the competent
authority decides.
