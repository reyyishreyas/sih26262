# Technical Architecture: sih26262

Companion to `1_PRD.md`. Items marked **[BUILT]** exist in the repo today; **[NEW]** are required by the PRD and not yet built. Verify a **[BUILT]** claim in code before relying on it for anything subtle.

> **Status vocabulary** (from the technical specification): Verified · Implemented · Tested · Partial · Proposed · Unverified · Blocked · Deprecated. They are not interchangeable: "implemented" ≠ "regulatory verified"; "tested" requires a recorded run. Where this file says **[BUILT]** it means *Implemented per README/user report*, not Tested or Verified. The spec's own reported baseline (154 passed, 2 skipped for missing Tesseract) is historical; **rerun and record** the current numbers.

## 1. Stack (pinned, verified)
| Layer | Choice |
|---|---|
| Runtime | Python 3.13.9 (`.venv/`), Node 26 / npm 11 (README says Python 3.10+/Node 20+ minimum) |
| API | FastAPI 0.159.1, uvicorn[standard] 0.54.0, routes under `/api/v1`, OpenAPI at `/docs` |
| ORM / migrations | SQLAlchemy 2.1.6 (2.0 declarative, `Mapped[]`), Alembic 1.20.1 (6 migrations) |
| Config / schemas | pydantic 2.14.1, pydantic-settings 2.16.1, typed `.env` with `SIH_*` prefix |
| Auth | python-jose 3.5.0 (HS256 JWT, issuer/audience/leeway); passwords via stdlib `hashlib.pbkdf2_hmac` SHA-256, 260,000 iterations. bcrypt/passlib are installed but **never imported** |
| Uploads | python-multipart 0.0.32; signature + path checks |
| DB | SQLite (dev/tests), PostgreSQL 16 (Compose/prod), psycopg[binary] ≥3.2 |
| OCR | pypdf 6.21.2 (text layer first) → pypdfium2 5.14.0 (rasterise, scale 2.0, no Poppler) → pytesseract 0.3.13 (`image_to_data`: per-word conf + boxes); host Tesseract 5.5.3 |
| LLM | Optional Gemini, only in `services/grounded_lease_extractor.py` via `SIH_GEMINI_API_KEY`; otherwise a deterministic parser. `adapters/llm` Protocol exists but is **unwired**. **OpenRouter not integrated** |
| Metrics | prometheus-client 0.26.0, `/metrics` token-gated |
| Malware scan | ClamAV over raw clamd TCP; implemented, **off** (`malware_scan_enabled=false`), fails closed (503) |
| Notifications | Mock: JSON lines to `storage/notifications.log` |
| Frontend | React 19.3.1, Vite 7.3.7, TypeScript 5.9.3 (`tsc --noEmit` in build), plain CSS, hand-rolled hash router (`App.tsx`), native `fetch`, inline SVG icons (`Icon.tsx`). No Tailwind, react-router, axios, react-query, icon lib or UI kit |
| Quality | ruff 0.14.4 (`backend/ruff.toml`), pytest 9.1.1 + pytest-cov 7.1.0, httpx 0.28.1 TestClient |
| Infra | docker-compose (`db`, `migrate`, `api`, `worker`, `frontend`; volumes `pgdata`, `storage`), `docker-compose.prod.yml`, multi-stage non-root images, nginx prod (port 8080, `server_tokens off`) |
| CI | GitHub Actions: backend (ruff, Alembic-matches-models check, tests, coverage), postgres-isolation, frontend (typecheck + build) |

> Doc drift to fix: README says 155 tests; current count is 159.

## 2. Layered design
```
Frontend (React)  ──fetch──▶  api/ routers  ──▶  services/  ──▶  models/ (SQLAlchemy)
                                   │                │
                                   │                ├── rule engine (allowlisted grammar, no eval)
                                   │                ├── workflow guards (role, state, document, rule)
                                   │                ├── audit (SHA-256 hash chain)
                                   │                └── adapters/ (ocr, llm, notification)
                                   ▼
                          core/ (settings, clock, db paths, permissions, jwt, password)
workers/scheduler.py + deadline_jobs.py  ──▶ services/deadlines, alerts
rules/*.json (policy-as-data)  ──▶ loaded and versioned into DB
```
**Principle: AI extracts and explains; verified rules evaluate; the workflow service controls real actions; the Rehearsal Engine tests hypotheticals without touching the real application.**

## 3. Three database access paths [BUILT]
| Role | Used by | `public` schema | `sim` schema |
|---|---|---|---|
| `sih_migrator` | migrate job | owns | owns |
| `app_rw` | API, worker | CRUD | none |
| `sim_prod_ro` | rehearsal baseline read | SELECT only, read-only txn | none |
| `sim_results_rw` | rehearsal results | none | CRUD |

`make verify-isolation` proves this on live PostgreSQL. The API never performs DDL. SQLite has no such enforcement; demo isolation on Postgres.

## 4. Policy as data [BUILT, extend]
`backend/rules/`: `compliance_rules.json`, `workflow_routes.json`, `deadline_policy.json`. Approved rule versions are immutable (migration 0004 adds a DB trigger); edits create draft versions. Rules carry "clause mapping pending verification" until a rule owner maps an exact APH clause. **Never invent a clause number.**

Rule outcomes are typed: `PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE` (three-valued logic). A missing input yields the rule's declared `missing_outcome`.

PRD mapping: PRD "rule registry" = this rules store. PRD says rules are "fixed, versioned code"; the repo's equivalent is **fixed, versioned, allowlisted data**. Both mean: no model opinion, no `eval()`.

## 5. Workflow engine
**[BUILT]** server-side guards for role, state, document and rule; every accepted and rejected action audited.
**[NEW]** (see PRD §6–7):
- Full Table 2.3 routing: 21 category rows → route (SD / SCR / SCR+EVC / SCR+EVC+AA) in `workflow_routes.json`, with a conformance test per row.
- Stage graph: readiness → route → scrutiny ⇄ compliance → EVC → SHC → Executive Committee → appeal → grant.
- Combined applications (union of stages, per-category outcome), Women's-before-merger sequencing, fallback-to-EoA branch, random/second EVC, return/revert with reason codes, one-time reopening, withdrawal.
- Cut-off check and blocked-application flags at intake.

Suggested state model: `Application` (1) → `ApplicationItem` (per category, own route/outcome/fallback flag) → `StageInstance` (type, owner, opened, due, closed, result). Auto-advance happens only in a service function called by an authorised user action.

## 6. Document intelligence pipeline
```
upload → signature/path check → (ClamAV if on) → classify → pypdf text layer
      → if page empty/low: rasterise (pypdfium2) → Tesseract (word, conf, bbox)
      → fields below threshold (default 0.75): optional vision model → JSON-schema validate
      → ground: value text must fuzzy-match OCR words on page, else REVIEW_REQUIRED
      → store ExtractedField (value, page, bbox, conf, engine+version, grounding)
      → rule engine on Extraction Value → findings → outcome
```
**[BUILT]** upload, text layer, Tesseract, per-field verify/reject (audited; bumps baseline version, invalidates stale rehearsal batches), grounded lease extractor.
**[NEW]** Format-2 NOC / Format-3 Resolution classification and rules (E01–E03, SITE-01, SITE-02), three-value model (Claim Value + edit reason), bounding-box storage exposed to UI, split-screen highlight, vision fallback through a provider-agnostic adapter (OpenRouter is one implementation; model name and threshold are config), external-call switch + call log.

Hard rules: vision output never counts unless grounded; temperature 0; JSON schema validated; engine and model version stored with each field; rules run on Extraction Value only.

## 7. Clocks, alerts, escalation
**[BUILT]** persistent scheduler worker, idempotent dedupe keys, retry path, alert rows + delivery attempts (mock log), undertakings with due/overdue flags, injectable clock (`SIH_CLOCK_MODE=fixed`, default `2026-10-22T09:00:00Z`).
**[NEW]** demo-clock control (advance time via an admin/demo endpoint, disabled in production), working-day + holiday calendar, escalation chain L0–L3 with per-stage limits (70/90/100/125%), 7-day appeal clock, 15-day Security Deposit clock with 31 May / 31 July penalty dates, nightly reconciliation job that recomputes every open clock and reports differences, snooze-once-with-reason.
All clocks use one server time (IST) via the injectable clock. **Never call `datetime.now()` directly.**

## 8. Audit trail [BUILT, extend]
Append-only, SHA-256 chained. Records accepted *and* rejected actions. Tamper detection exists. **[NEW]**: export with hash-check, per-application single timeline, document-view logging, tamper-demo endpoint/script that mutates one row in a throwaway DB. Note: UI says "audit timeline", not "replay" (historical replay is not built).

## 9. Rehearsal (Crash-Test) Engine [BUILT]
Read-only baseline → copied snapshot → simulation-only writes in `sim` schema → finding-level diff → explicit `production_modified: false`. Rehearsal Load Factor is **deliberately null** until formula, units and test matrix are validated. Do not fill it in.

## 10. Auth, RBAC, scope [BUILT, extend]
PBKDF2 hashing; JWT issuer/audience; persisted throttling (5 failures → 429 + `Retry-After`); password change revokes old tokens; officer scope enforced server-side. **[NEW]** Region scoping everywhere, conflict-of-interest blocking, MFA for officers (P1), roles for EVC expert / SHC / Executive Committee / SAC / Regulation Bureau.

## 11. API conventions
- All routes under `/api/v1`; routers in `api/` per domain.
- Typed error envelope; `X-Request-ID` on every response; security headers; `Cache-Control: no-store` on API paths.
- List endpoints bounded: `limit`/`offset`, max 500, `X-Total-Count`.
- Health: `/health/live` (no DB), `/health/ready` (probes all three DB roles, 503 on failure), `/health`.
- JSON logs with request id, method, path, status, duration.

## 12. Data model (target)
Existing tables cover applications, documents, extracted fields, findings, rule versions, workflow, undertakings, alerts, audit, sim_* . **[NEW]** entities from PRD §10 of the source: `ApplicationItem`, `StageInstance`, `ChecklistItem`, `DeficiencyCycle`, `EVC`, `HearingDecision` (SHC/SAC/EC/Council + Speaking Order + appeal clock), `Payment` (head, amount, ref, status, refund/deduction), `SecurityDeposit`, `Escalation`, `RuleCalendar` (Public Notice, Academic Calendar, holidays, effective dates), `ExternalCallLog`. Every new table needs an Alembic migration **and** must keep the "Alembic matches models" CI check green.

## 13. Environments
| Mode | DB | Notes |
|---|---|---|
| `make setup && make dev` | SQLite | UI at :5173, API :8000; isolation not DB-enforced |
| `make up` | PostgreSQL 16 | worker + migrate + seed; `make smoke`, `make verify-isolation` |
| Prod compose | PostgreSQL | required secrets; API refuses to start on weak JWT secret, non-Postgres DB, wildcard CORS/hosts, seeding on, fixed clock, debug on, HSTS < 1 year, or reused rehearsal role |

## 14. Integrations
AICTE portal: **none, deliberately** (stub feed; "as of" timestamp on screens). Payment gateway: stub status lookup. DSC verification: stub. Email/SMS: mock → pluggable provider. SSO: not built. Video platform: store link only.

## 14a. Boundary, trust and transaction rules (from the specification)
- **Untrusted:** browser input, uploaded files, OCR text, model output, external providers. Validate at every boundary. **Document text is data, not instructions** (prompt-injection defence); the model gets no tools and cannot touch workflow state.
- **Atomicity:** state change + transition record + assignment change + required audit record commit in one transaction. An invalid transition writes nothing. If the required audit write fails, **fail the high-impact operation**.
- **Concurrency:** `Application.baseline_version` (or equivalent) must be *enforced*, not just present: stale writes are rejected with a reload message; test concurrent transitions. Use ETag/version checks where available.
- **Idempotency:** uploads, transitions, alert sweeps and background jobs are retry-safe (idempotency keys).
- **Partial failures** to define and test: file stored but metadata failed (compensate/clean up); metadata saved but processing failed; transition succeeded but notification failed (use outbox/retry, never corrupt state); DB outage; provider timeout. Processing failure is **never** a compliance pass.
- **Object-level authorisation on every endpoint**; scope by institution, assignment, region, committee and jurisdiction; deny by default; return **404** (not 403) for unauthorised resources where the existing policy does. Never trust client-supplied role/institution/region/assignment.
- **Request lifecycle:** authenticate → resolve role/scope server-side → load resource → verify ownership/assignment/jurisdiction/action → validate state → execute transaction → audit → return permitted fields only.
- **Documents:** upload flow = authenticate/authorise → validate scope+category → size/type + **file-signature** check → safe server-side storage key → scan if enabled → private storage → metadata + hash + uploader + time + version → queue processing → audit. All versions preserved; each extraction/finding links to an exact document version; replacement requires a reason and re-runs affected checks; no predictable public URLs; retention/deletion only after privacy/legal review.
- **Extraction runs:** reprocessing creates a new run and preserves old output. Confidence is an *uncalibrated* signal; the 0.75 threshold is **unvalidated** — calibrate on labelled samples and use it only to route review.
- **Audit limits (state honestly):** a hash chain detects some alterations; it does **not** stop a privileged actor rewriting the whole chain. Add restricted DB writes, backups and **external checkpoints** (periodically publish the latest chain hash somewhere the DB admin cannot edit). Test altered, deleted **and reordered** records. Never claim absolute immutability. Keep audit records, diagnostic logs, metrics and correlation IDs as four separate things.
- **RLS:** if Supabase RLS is used, document and test policies **separately** from API authorisation; do not claim RLS without evidence.
- **Source-backed rules only:** each rule record carries `source_id`, `clause`, `status` (Verified/Unverified/…), `effective_from`, `version`, applicability, inputs, predicate, outcomes, human-review flag. `status != Verified` ⇒ the rule is advisory-only and cannot gate any action.

## 14b. Endpoint inventory
**Reported existing:** `POST /api/v1/applications/{id}/transitions`, `POST /api/v1/alerts/sweep`, `GET /api/v1/audit/verify` (+ the rehearsal, evidence, undertakings, officer, auth routes in the README).
**Proposed (search for an existing equivalent before adding any):** `GET/POST /applications`, `GET/PATCH /applications/{id}`, `POST /applications/{id}/submit`, `GET/POST /applications/{id}/documents`, `GET /documents/{id}`, `GET /documents/{id}/content`, `POST /documents/{id}/process`, `GET/POST /applications/{id}/findings`, `POST /findings/{id}/resolve`, `POST /applications/{id}/deficiencies`, `POST /deficiencies/{id}/responses`, `GET /assignments`, `POST /applications/{id}/reassign`, `GET /deadlines`, `GET /dashboard/summary`, `GET /reports/pendency`, `GET /audit`.
Every endpoint spec records: method/path, auth, roles/scope, path/query/body schemas, validation, response schema, success/error codes, side effects, audit events, pagination, concurrency/idempotency, limits, and examples **taken from actual code/OpenAPI**.
Error shape (proposed standard): `{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [], "request_id": "..."}}`. Reconcile with the repo's existing envelope first. No stack traces, secrets or unauthorised-resource details in errors.

## 14c. Security threat list
Cross-institution leakage; forged roles/scopes; malicious or oversized uploads; parser vulnerabilities; **prompt injection in documents**; external AI leakage; SQL/command injection; XSS; CSRF/session theft; audit tampering; provider abuse; leaked secrets. Controls: deny-by-default authz, strict validation/encoding, signature/size/type checks, private storage, least-privilege DB credentials, secret management, HTTPS + CORS allowlist, rate limits, safe errors, dependency scanning, sensitive-log minimisation. Identify personal/financial/institutional data and define access, retention, export and deletion rules.

## 14d. Observability
Monitor API latency/error rate, auth failures, upload failures, OCR duration/failures, provider rate limits/timeouts, pending jobs, **alert-sweep last-run/result**, notification retries, DB pool usage, storage capacity, audit verification failures. Liveness/readiness checks must **not** call an LLM provider. A sweep endpoint alone does not prove a recurring scheduler is configured: document whether the worker's scheduler runs it.

## 15. Known limits
Not security-audited or load-tested (workload and performance targets are **not yet agreed**: do not invent numbers); no backup/restore or recovery targets tested; manual reassignment reported missing; committee COI not implemented; withdrawal/appeal/reopening unimplemented until verified; Tesseract is a host dependency (document whether required or optional); not validated against APH by a competent authority; Rehearsal Load Factor null; LLM explanations unwired; ClamAV off; notifications mocked; no geocoding. Demo data is synthetic.
