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

## Appendix F release-readiness walk (Phase 11.7, 2026-10-28)

`md/1_PRD.md` Appendix F (line 414) lists 18 release-readiness checkboxes. **The
PRD's own boxes were deliberately not ticked** — that checklist is the release
gate a human signs. This walk verifies each item against the repo so a reviewer
can sign quickly; every box verified here cites its evidence, and anything not
satisfied is stated as a limitation.

| # | Appendix F item | Verdict | Evidence / limitation |
|---|---|---|---|
| 1 | Official source URLs, versions, clauses recorded | **Partial — limitation** | `docs/SOURCES.md` registers the APH URL and access records, and the appeal/reopening/grant clauses are source-checked by a named human reviewer (amendment 2026-10-28). Still open: the Problem Statement source is `null` anywhere in the repo (`SRC-PS-26262`), the 2026–27 addendum is unverified, and the remaining APH clauses behind the seven rules are "pending verification" |
| 2 | Unverified rules disabled or advisory | **Met** | Advisory families (precheck, site, crosschecks, doc-check, fee table) cannot block or activate anything (`docs/RULES.md`; `test_fee_engine.py::test_prd_candidate_values_are_present_but_cannot_become_due_or_block`); the seven blocking-format rules carry "clause mapping pending verification" labels on rule and finding |
| 3 | All spec sections reviewed against actual code | **Limitation — cannot be done** | The technical specification file is not in the repo (`SRC-SPEC-26262`); all row reconstructions start from the PRD (header caveat in `docs/TRACEABILITY.md`). When the spec arrives, reconcile rather than rewrite |
| 4 | Workflow states/routes match approved config | **Met for implemented routes** | Routes are versioned config consumed by the engine (`rules/workflow_routes.json`; `test_workflow.py`, `test_routes_and_revert.py`); the *official* stage/authority matrix stays Unverified (REG-002) and is labelled so |
| 5 | API schemas match frontend/backend | **Met (manual parity)** | `frontend/src/types.ts`/`api.ts` hand-synced, `tsc --noEmit` + vite build green; limitation: no automated contract/OpenAPI drift test |
| 6 | Migrations and seeds work | **Met** | 31 Alembic revisions, `alembic upgrade head && alembic check` clean on SQLite and PostgreSQL; Compose migrate job + idempotent seed (`make smoke` repeated, IMPL-0077) |
| 7 | Authorisation tests cover sensitive resources | **Met** | `test_authz_matrix.py` maps 125 (method × route) pairs / 171 allowed (route × role) pairs with routes derived from the running app (BUG-0088 corrects the summary figure); live Scenario B walk (IMPL-0083) |
| 8 | Document versioning/access verified | **Met** | Versioned uploads preserve prior versions; access is permission- and scope-gated; bytes never served (tests in `test_api.py`/hardening paths; Scenario A v1→v2, IMPL-0082) |
| 9 | OCR/AI failure paths tested | **Met** | `test_extraction_failure_is_recorded_without_storing_the_upload`; truncated PDF processes honestly with 0 fields and no PASS (Scenario C, IMPL-0084); vision fallback disabled-by-default with a mocked provider test |
| 10 | Findings link to evidence and rule versions | **Met** | `rule_evaluations` stores rule key/version + typed outcomes + evidence refs; seeded case trace: 6 of 7 findings cite named evidence or its recorded absence (IMPL-0086) |
| 11 | Audit coverage and limits documented | **Met** | Phase 8.1 closed for implemented flows (IMPL-0068); coverage *and* limits documented (ARCHITECTURE audit section, DATA_MODEL audit paragraph, `scripts/tamper_demo.py`) |
| 12 | Deadlines cite approved policy versions | **Met for mechanism; values advisory** | Console-approved immutable snapshots (content-hashed) feed the live sweep (`test_phase9_deadline_console_alerts.py`, Phase 9.4/9.5); the deposited cadence is officer-recorded with an advisory placeholder clock (DEC-0029) — official value capture stays a human input |
| 13 | Alert scheduling/delivery described accurately | **Met** | Delivery is explicitly simulated (`test_alert_delivery_is_marked_simulated`; README/PRODUCTION wording); ladder behaviour, dedupe and escalation are the tested parts |
| 14 | Tests/build rerun, results recorded | **Met** | `make test` → 858 passed/2 upstream warnings (twice on 2026-10-28); coverage 91% vs 90% baseline (IMPL-0078); frontend build green (63 modules); CI runs 40659968821/40661431548 green; BUG-0087 (one-off OCR flake) is open-but-not-reproduced and recorded |
| 15 | Synthetic demo data only | **Met** | Seed and PDF factory are synthetic; production profile refuses `SIH_SEED_ON_STARTUP` (PRODUCTION.md §1); PRD/README disclaim real data obligations |
| 16 | Deployment, backup, recovery documented | **Met, drill not run** | `docs/PRODUCTION.md` documents deploy order, secrets, TLS, backups (`pg_dump` + storage volume together), restore verification incl. `/audit/verify`, upgrade/rollback; the production-profile Compose was started and probed here (DEFERRALS "Production-shaped Compose" row). Limitation: no DR drill or tested-backup rotation has been executed against live infrastructure; no backup scheduler in-repo |
| 17 | Limitations/open questions disclosed | **Met** | `docs/DEFERRALS.md`, PRODUCTION §9/§12, PRD §19 open questions, per-phase open items (Phase 9.3 activation gate, Phase 6 exit-check Partial, DEC-0033 Open) |
| 18 | No unsupported claims about official integrations, accuracy, performance or compliance | **Met with constant vigilance** | The "claims we do not make" list; every accuracy/performance figure is labelled measured-on-this-machine; BUG-0088 shows a wrong figure was caught and corrected in the same session; nothing in the repo claims AICTE validation |

**Remaining limitations to carry into any release decision** (see also
PRODUCTION §9–§12): official clause coverage (item 1), absent spec file
(item 3), and the standing cross-cutting caveats — no security audit, no load
test, no retention policy, register-of-record values pending human verification.
