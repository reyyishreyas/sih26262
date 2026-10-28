# Deferrals and Honest Boundaries

This file exists so nothing in the repository has to pretend. Each item is either
**not implemented**, **implemented at prototype level**, or **written but not yet
exercised**.

## Not implemented

| Item | Why it is not here | What exists instead |
|---|---|---|
| **Load Factor** | No validated formula, units, edge cases or test matrix | `null` in every response; `sim_metrics` stores `NULL` with `formula_version: NULL`; the finding-level diff is the output |
| **Historical replay** | No reconstruction of past application state | Chronological audit timeline; the API note says it is not a replay |
| **Local OCR (pypdf + Tesseract)** | Real OCR implemented **on the machine only** (Phase 5, IMPL-0039+): text layers via pypdf, scans rendered and read with `image_to_data`, scanned EoA covered by integration tests (`skipif` without the binary) | No accuracy measurement, no vendor corpus, no external OCR — every value stays an unverified candidate until a person verifies it |
| **LLM evidence assistant** | Risk of ungrounded verdicts; no evaluation set | `LLMAdapter` interface + mock that refuses without context; not wired to an endpoint |
| **Real notification delivery** | No SMS/email provider, no consent or template governance | Mock adapter writing `storage/notifications.log`; alerts and attempts are real rows, marked `simulated` |
| **External LLM processing** | No external service is ever sent institution data (human gate) | `LLMAdapter` interface + mock that refuses without context; the local evidence-grounded engine (`app/services`, Deterministic AI Copilot + local OCR) does all reading on the machine |
| **Rule management UI** | Scope control | Rule versions are seeded from JSON; drafting/approval is tested at the service level. Deadlines, escalation, fee and template policies have a four-eyes admin console (Phase 9.4) |
| **Rule immutability at the database level** | ORM guard only | SQLAlchemy `before_update` guard + tests; production needs a DB trigger |
| **Duplicate-document finding** | Similarity threshold needs its own reviewed rule | Exact SHA-256 duplicate is reported on upload; perceptual hash is stored but unused |
| **Automatic case allocation** | Implemented at prototype level (Phase 6.5 `case_assignment_service`) — routing follows `assignment_policy.json`, audited | No workload/capacity policy beyond the configured counts |
| **Holiday calendar / business-day arithmetic** | Needs an authoritative calendar | Deadline offsets in calendar days; end-of-day uses `Asia/Kolkata` |
| **Document download / signed URLs** | Security surface | Files are stored under `SIH_STORAGE_DIR`; metadata is readable, bytes are not served |
| **MFA, password reset / account recovery, SSO** | Not built | PBKDF2-SHA256 hashing, HS256 JWT with issuer/audience, persisted sign-in throttling, authenticated password change that revokes old tokens |
| **SSO / government identity** | Integration out of scope | Seeded demo accounts |
| **Four-eyes / segregation of duties** | Implemented for policy editing (Phase 9.4): draft by one administrator, approve only by a different one, approved snapshots immutable, audited with content hashes | Not extended to rule versions (which stay service-level) or payment approvals; external service integration remains out of scope by design |
| **Retention, archival, partitioning** | Operational policy | None; tables grow without bound |
| **Frontend component / E2E tests** | Time | `tsc --noEmit` and a production build; the UI was exercised manually against the running stack |
| **Accessibility audit** | Time | Semantic HTML, labels, keyboard-reachable controls; no formal audit |

## Exercised, but still prototype-level

| Item | State |
|---|---|
| `docker compose up` (PostgreSQL + API + worker + frontend) | **Run here.** Stack starts, migrates, seeds and serves; `scripts/smoke.sh` exercises the API end to end against it |
| PostgreSQL role isolation (`backend/sql/roles.sql`) | **Applied and verified here** by `backend/scripts/verify_isolation.py`: the baseline reader cannot write, the results writer cannot read operational tables, and neither can reach the other's schema |
| Dedicated `sim` schema | **Implemented for PostgreSQL** (`SIH_SIMULATION_SCHEMA=sim`, migration `0002_sim_schema`). SQLite has no schemas, so development and tests fall back to table-level grants |
| Alembic against PostgreSQL | **Applied here** — 31 revisions including the appeal, reopening, grant, policy-console and undertaking-notice/evidence migrations; `alembic check` is clean on SQLite and PostgreSQL, and the Compose migration job runs on every start |
| `.github/workflows/ci.yml` | Ruff, SQLite Alembic check, 858 tests with coverage, PostgreSQL role isolation and frontend production build. Verified run: [40659968821](https://github.com/reyyishreyas/sih26262/actions/runs/40659968821), green on 2026-10-28 on `2dac70b`; coverage 91% vs the 90% baseline recorded at `9945e6a` (IMPL-0078) |
| Production-shaped Compose | **Run here** — `docker-compose.prod.yml` rendered with URL-safe secrets; bootstrap, Alembic, API, worker and nginx frontend started under `SIH_ENV=production`; readiness showed `app_rw`, `sim_prod_ro` and `sim_results_rw`; HSTS and docs-disabled behaviour checked |
| Upload safety | **Tested** — streaming size limit, magic-byte signature, declared-type match, filename sanitisation and atomic write; no malware scanner |
| Sign-in protection | **Tested** — database-backed account/address and address-only throttling with `Retry-After`, generic 401, accepted/rejected login audit, password-change token invalidation; a success clears only its account/address counter |
| Observability | **Implemented** — JSON logs, request ids, security headers, live/readiness probes, database pool timeouts; no metrics endpoint or log shipper |
| Load / concurrency behaviour | Single-process tests only; no load test, no soak test, no multi-worker behaviour measured |

## Prototype-level implementations

| Area | What is real | What is limited |
|---|---|---|
| Approval Rehearsal | Read-only baseline session (database-enforced in PostgreSQL), deep-copied snapshot, simulation-only writer in a separate schema, diff, assumptions, supersede check, `production_modified: false` | The baseline and results still live in the same *database* on PostgreSQL — only the schema and the role differ; a separate database instance would be stronger |
| Audit chain | SHA-256 chain, head lock, verification endpoint, tamper tests | Tamper-evident, not tamper-proof against full DB access; no external anchor |
| Deadlines | Deterministic clock, idempotent sweep, dedupe keys, retries, escalation ladder; per-obligation ladders (Phase 9.2 deposit cadence) and console-approved deadline snapshots feeding the sweep (Phase 9.5) | Worker polls; no broker; no back-pressure; PRD/placeholder offsets without named source verification stay advisory |
| Appeals, grants, reopening | Appeal window/SAC/Council flow audited both ways (Phase 6.6); one-time reopening with verified payment gate (Phase 7.3); guarded, immutable grant batches (Phase 6.8) | Appeal figures/cadences labelled; grant and fee values stay guarded/non-blocking until a named source register exists |
| Policy console | Four-eyes JSON drafting/approval with hashes and audit; deadline snapshots consumed by the live sweep (Phase 9.4/9.5) | Route/fee/escalation/template snapshots versioned but not consumed at runtime; no fee activation |
| Monitoring | Server-enforced scope shared with drill-downs, live counts | No scheduler-driven SLA forecasting; no capacity model |
| Evidence | Source page/span, confidence, verification status, audited verification, versioned uploads | Real pypdf/Tesseract extraction with per-label provenance, but a narrow label grammar — unlabelled values are not read; confidence does not decide anything |
| Rules | Allowlisted grammar, three-valued logic, immutable approved versions, seven rules | Clause mapping pending; no full APH coverage |
| Security | Server-side RBAC + scope, 404 for out-of-scope, PBKDF2 passwords, JWT issuer/audience, persisted login throttling, password-change token invalidation, least-privilege database roles, upload signature checks, security headers | No MFA/SSO, no password reset, no penetration test, no malware scan, no external secret manager integration; the development secret must be replaced |

## Claims we deliberately do not make

- "AI approves applications." It does not; officers decide.
- "The system is fraud-proof." It surfaces discrepancies; it does not detect fraud.
- "100% compliance coverage." Seven illustrative rules cover the demo, not the APH.
- "Production-ready." No security audit, no load test, no retention policy.
- "Load Factor of X." No formula exists yet.
- "Historical replay." Not built.
- "External OCR accuracy." All OCR runs locally; no accuracy claim is recorded.
- "Validated against AICTE." Clause mapping is pending verification by a rule owner.
- "Simulations run on a separate database." They run in a separate schema with
  separate roles, in the same PostgreSQL instance.
