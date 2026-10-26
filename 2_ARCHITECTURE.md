# Technical Architecture: sih26262

Companion to `1_PRD.md`. Items marked **[BUILT]** exist in the repo today; **[NEW]** are required by the PRD and not yet built. Verify a **[BUILT]** claim in code before relying on it for anything subtle.

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

## 15. Known limits
Not security-audited or load-tested; not validated against APH by a competent authority; Rehearsal Load Factor null; LLM explanations unwired; ClamAV off; notifications mocked; no geocoding. Demo data is synthetic.
