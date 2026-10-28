# AICTE Approval Workflow, Compliance Monitoring & Alert Management System

A working prototype built for **Smart India Hackathon 2026 — Problem Statement 26262** by AICTE (Regulation Bureau): *Integrated AICTE Approval Workflow Automation, Compliance Monitoring and Alert Management System*.

## The problem

The AICTE problem statement describes approval applications moving through stages such as scrutiny, Expert Visit Committee (EVC), and SAC/SHC, with time-bound conditions such as undertakings, compliance submissions, and lease renewals. It identifies coordination, pendency, document validity, and reminders as problems the proposed platform should address.

This prototype brings those coordination tasks into one place: applications move through configured workflow stages, role-scoped dashboards show relevant work, and a scheduled worker checks configured deadlines and creates deduplicated alerts and escalations. The configured routes, rules and deadlines are prototype policy; they are not a determination of an institution's statutory eligibility.

## What it does

| Problem statement asks for | What the prototype provides |
|---|---|
| A. Workflow automation | Configured stage routes (scrutiny-only, scrutiny + EVC, EVC + SAC/SHC), guarded and role-authorized transitions, and officer-authorized return/revert with a recorded reason |
| B. Dashboards & pendency | Role-based dashboards (institution, scrutiny, regional, EVC, supervisor, admin), with server-side role and jurisdiction scoping; application ageing and workload views |
| C. EVC scheduling & alerts | EVC queue fed automatically after preliminary processing, scheduling/deadline tracking and reminders |
| D. Undertakings & compliance | Digital record of approvals-with-conditions, evidence submission, officer verification, deadline reminders and escalation |
| E. Lease & document validity | Validity dates tracked per document, advance expiry alerts, renewed-document submission and verification |
| F. Alerts, escalation & audit | Scheduled alert worker with dedupe, configured escalation, PDF/CSV reports, and a SHA-256 hash-chained audit trail for state-changing and rejected operations |

One deliberate idea runs through the whole system: **the analyst does not decide.** The current document-upload path uses local text extraction and Tesseract OCR to produce evidence candidates for human review. An optional OpenRouter vision adapter exists in the code but is not wired into upload extraction; it is disabled by default and guarded for trusted public or synthetic pages. Compliance evaluates evidence under configured rule versions; unverified evidence and unverified regulatory rules cannot produce an authoritative compliance decision. Only an authorized officer can take workflow actions. For a hypothetical, an officer can use the read-only rehearsal baseline and isolated results schema; rehearsal does not change a real case.

### Where the rules and the document flow come from

The prototype's workflow and policy design is informed by the **AICTE Approval Process Handbook 2024-25 to 2026-27** ([official PDF](https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf)); this does not mean the implementation has been validated by AICTE or a competent authority. Baseline rule and policy data is stored in JSON under `backend/rules/` and seeded into the application. Some policy categories also have a four-eyes admin console: approved deadline snapshots feed the live alert sweep, while route, fee, escalation and template snapshots are not yet consumed by runtime services. The seven core compliance rules still have clause mapping pending verification; unverified rules are advisory and must not be treated as official requirements. The future PDF-to-RAG-to-JSON admin ingestion workflow described below is not implemented.

## Tech stack

- **Backend:** Python 3.10+, FastAPI, SQLAlchemy 2.x, Alembic; baseline policy data in `backend/rules/*.json`, with some values still marked unverified/advisory
- **Frontend:** React 18 + TypeScript (strict) + Vite, minimal dependencies
- **Database:** PostgreSQL 16 in Docker, SQLite for quick starts and tests
- **Security:** server-side RBAC with jurisdiction scoping, PBKDF2-SHA256 sign-in, JWT with revocation on password change, four least-privilege database roles, hash-chained audit log
- Verification snapshot: **858 backend pytest tests passed** in the most recent full local run recorded in `CONTEXT.md`; GitHub Actions is configured to run lint, backend tests, migration checks, PostgreSQL isolation checks, and the frontend build. Check the latest workflow run for current CI status.

## Quick start (5 minutes)

For `make setup` / `make dev`, you need **Python 3.10+** and **Node 20+**. Tesseract OCR is needed to read scanned PDFs locally; PDFs with a usable text layer can be read without it. Docker Compose is needed only for the full PostgreSQL stack.

```bash
git clone https://github.com/reyyishreyas/sih26262.git
cd sih26262
make setup    # creates the venv, installs packages, writes config, seeds a demo SQLite DB (~1 min)
make dev      # starts the backend (:8000) and the UI (:5173) together
```

Open **http://localhost:5173** and sign in:

| Panel | Email | Password |
|---|---|---|
| I am the College | `institution@demo.local` | `DemoPassw0rd!` |
| I am the Checker | `scrutiny@demo.local` | `DemoPassw0rd!` |

More checker roles (`regional@`, `evc@`, `supervisor@`, `admin@demo.local`) are behind **"Sign in as a different checker role"** — pick one and the form fills the email in. Every seeded credential is synthetic demo data, in the demo password above.

That's the whole loop: `make setup` once, `make dev` every time after.

## Setup guide for evaluators (step by step)

1. **Install the prerequisites.** Python 3.10 or newer, and Node.js 20 or newer. On macOS: `brew install python node`. On Ubuntu: `sudo apt install python3 nodejs npm` (check `python3 --version` ≥ 3.10).
2. **Get the code.** `git clone https://github.com/reyyishreyas/sih26262.git` and `cd sih26262`.
3. **Run setup.** `make setup` checks prerequisites, creates the virtualenv, installs Python and npm packages, writes `.env` from the example, seeds a synthetic demo database and self-checks.
4. **Start the app.** `make dev`. You'll see `[ok] API` and `[ok] UI`; the terminal streams both logs; **Ctrl-C** stops both cleanly.
5. **Walk the happy path (~10 minutes).**
   - Sign in as the College, open `app-main-0001`, upload a document, see extracted fields and their evidence region highlighted.
   - Sign in as the Checker (scrutiny), see the same case on your side: verify/reject fields, watch the rule engine produce typed outcomes (PASS / FAIL / NEEDS_REVIEW / NOT_APPLICABLE).
   - As supervisor or regional, open the dashboards — everything is scoped to your region, and the numbers reconcile with the case lists.
   - Look at the alerts and audit trail: state-changing operations and rejected requests are recorded in the hash chain.
6. **Optional but recommended checks** (from the repo root, with the Compose stack or after `make setup`):
   - `make test` — full backend suite.
   - `docker compose up -d --build && make smoke` — starts the full PostgreSQL stack and exercises the API end to end.
   - `make verify-isolation` — proves the least-privilege database roles live: the app role really cannot reach the simulation schema, the rehearsal reader really is read-only.

If anything misbehaves: `make seed` (idempotent) re-seeds demo data; `rm backend/sih26262.db && make setup` gives a brand-new demo state. Scanned-PDF OCR needs Tesseract: `brew install tesseract` or `apt install tesseract-ocr` (PDFs with a text layer work without it).

## Seeded demo cases

| ID | Situation |
|---|---|
| `app-main-0001` | New institution in scrutiny — lease valid to 2028-03-31 but ownership record says 2027-03-31, affidavit missing. Produces PASS, FAIL, NEEDS_REVIEW and NOT_APPLICABLE outcomes on one screen |
| `app-second-0002` | A different institution submitted a lease with the same file hash — duplicate-detection demo |
| `app-existing-0003` | Existing institution, complete evidence, approvable on the scrutiny-only route |
| `app-draft-0004` | Draft application used for upload demos |

Seeded demo accounts, application records, and generated fixture documents are synthetic. The repository also contains sample document files used by OCR regression coverage; treat their extracted values as unverified test evidence, not as synthetic records or an authoritative system of record.

## Architecture

![System architecture — how the pieces fit](docs/architecture.svg)

The same deterministic three-valued rule engine serves the live workflow and the read-only rehearsal sandbox. On PostgreSQL, separate roles isolate operational access, read-only rehearsal baseline access, and rehearsal-result writes. `make verify-isolation` checks that role contract against a running PostgreSQL stack; SQLite development uses a different, table-level test setup.

## Running the full stack (PostgreSQL)

`make up` builds four containers, runs Alembic as the schema owner, applies least-privilege grants, seeds and serves. `make reset` stops and clears everything. For a deployment-shaped stack (required secrets, non-root images, no fixed clock, fail-fast production config), see [docs/PRODUCTION.md](docs/PRODUCTION.md) and use `docker-compose.prod.yml`.

The rehearsal isolation above is **database-enforced only on PostgreSQL** — one reason to demonstrate on `make up`, not just `make dev`.

## Repository map

```
backend/
  app/api/        FastAPI routers: auth, applications, documents, compliance,
                  workflow, undertakings, alerts, audit, dashboards, admin, reports
  app/services/   rule engine, workflow, deadlines/alerts, evidence, rehearsal,
                  reports, audit — business logic lives here, routers stay thin
  app/adapters/   OCR / LLM / notification interfaces + mock implementations
  app/workers/    persistent deadline & alert scheduler
  rules/          compliance_rules.json, workflow_routes.json, deadline_policy.json
  migrations/     Alembic revisions
  tests/          858 tests
frontend/         React + TypeScript review UI ("I am the College" / role dashboards)
scripts/          setup.sh, dev.sh, smoke.sh
docs/             architecture, rules, roles, data model, production
Makefile          setup / dev / up / reset / lint / test / smoke / verify-isolation
```

Further reading: [architecture](docs/ARCHITECTURE.md) · [compliance rules](docs/RULES.md) · [role model](docs/ROLE_MODEL.md) · [data model](docs/DATA_MODEL.md) · [user journey](docs/USER_JOURNEY.md) · [rehearsal engine](docs/REHEARSAL_ENGINE.md) · [demo script](docs/DEMO_SCRIPT.md) · [acceptance tests](docs/ACCEPTANCE_TESTS.md) · [what is deliberately not built](docs/DEFERRALS.md)

## Roadmap — future scope

To be plain about it: this is an unfinished prototype, built under hackathon deadlines. Within that scope we chose depth over breadth — the end-to-end pipeline today is exercised on a small set of prescribed documents (EoA letter, lease agreement, affidavit, ownership record) evaluated against a starter subset of the APH rules. The next stages of work:

- **Full APH coverage.** Extend the rule set from this starter subset to the complete rule catalogue of the Approval Process Handbook — every document type, every applicable condition.
- **An admin rules panel with PDF-to-configuration ingestion.** Planned workflow: an administrator uploads the complete, newly published rules/handbook PDF; the system extracts and chunks its text, indexes those chunks for retrieval (RAG), and uses the retrieved passages to draft the corresponding rules in the existing versioned JSON format. Each draft must retain its source page/chunk and clause reference, and remain inactive until an authorized human verifies it and a second administrator approves it under the existing four-eyes process. Once approved, the JSON rule version becomes the active configuration without editing application code or reconfiguring/redeploying the application. This assisted ingestion and automatic activation path is future work; the current prototype does not ingest a PDF or generate/activate JSON rules automatically, and AI must not make regulatory decisions or approve its own drafts.
- **A better crash-test for the college.** The rehearsal engine currently serves the checking side; we want to build the college-facing version into a richer pre-flight experience — so an institution can test its own submissions against the current rules before AICTE ever sees them.
- **Real delivery channels and integration.** Notifications currently end in a file (mock adapter); wire real email/SMS, and integrate with existing AICTE systems as the problem statement allows.
- **Production maturity.** Security audit, load testing, records-retention policy, and accessibility review before anything beyond a demonstration.

## What this is not

A prototype, not a certified government system. It has not been security-audited or load-tested. OCR and rules provide evidence and advisory outcomes; they do not perform statutory scrutiny or make approval decisions. The API enforces role-authorized workflow actions and audit logging, but authorized officials remain responsible for reviewing evidence and making regulatory decisions.

## Team

**Parikshit** — Team Leader · Reyyi Shreyas · Srisha Prajwal · Kushal Sharma · Pranav · Deepal Jain 
