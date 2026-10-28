# CONTEXT.md — read this first

Everything an AI (or a new teammate) needs to work on this repository without
re-discovering it. Last verified against a running stack and a green test
suite on **27 Oct 2026**.

Deep dives live in `docs/` (index at the bottom). This file is the map and the
honest status; `things.md` is the working backlog for the next feature.

---

## 1. What this is

**SIH 2026 problem statement SIH26262** — *Integrated AICTE Approval Workflow
Automation, Compliance Monitoring and Alert Management System.*

A dual-user prototype (institution vs. reviewing officer) that walks an AICTE
approval case from draft to decision, with deterministic compliance rules,
evidence extraction from real documents, alerts, an audit trail, and a
**Approval Crash-Test (rehearsal) engine** that lets an officer rehearse
hypothetical evidence changes and see a finding-level diff without writing to
the real application.

- Repo: `https://github.com/reyyishreyas/sih26262.git`, branch **`master`**
  (only branch; everything is merged and pushed).
- Local path: `~/Desktop/sih26262`
- Working doc / backlog: **`things.md`** (NOC research, P0–P3 backlog, build order)

### The idea in one paragraph

> AI extracts and explains evidence. Verified rules evaluate compliance. The
> workflow service controls real actions. The Rehearsal Engine tests
> hypothetical changes without modifying the real application.

---

## 2. Run it

```bash
make setup     # once, ~5 min: venv, deps, node_modules, tesseract, DB, seed
make dev       # API on http://localhost:8000, UI on http://localhost:5173
make lint      # ruff (backend/app backend/tests migrations scripts)
make test      # pytest — 838 passing (2026-10-28 verification)
make build     # frontend typecheck + vite build
make down      # stop the docker stack (only if you used make up)
```

Other targets: `help up logs ps reset migrate seed smoke verify-isolation
migrate-sqlite`. `make reset` is docker-compose only; for a clean **sqlite**
demo database use:

```bash
rm -f backend/sih26262.db backend/sih26262.db-shm backend/sih26262.db-wal
make seed && make dev
```

Startup calls `create_all()` and seeds **only** if `SIH_SEED_ON_STARTUP=true`
(default false), so an empty database stays empty — always `make seed`.

### Demo logins

Password for all: **`DemoPassw0rd!`**

| Email | Persona | Role | Scope |
|---|---|---|---|
| `institution@demo.local` | College (institution rep) | `institution_representative` | one institution |
| `scrutiny@demo.local` | Checker (review officer) | `scrutiny_officer` | assigned cases |
| `regional@demo.local` | Regional officer | `regional_officer` | Northern Region |
| `supervisor@demo.local` | Supervisory officer | `supervisory_officer` | region |
| `evc@demo.local` | EVC member | `evc_member` | committee |
| `sac@demo.local` | SAC member | `sac_member` | Northern Region |
| `council@demo.local` | Council member | `council_member` | appeal decisions |
| `competent-authority@demo.local` | Competent Authority | `competent_authority` | Northern Region |
| `admin@demo.local` | Administrator | `administrator` | global |

Sign-in is a **typed email/password form** (no one-tap), and `POST /auth/login`
**only answers the sign-in screen's origin** — curl, the API explorer or another
site get `403` (refused before the throttle, so they cannot lock anyone out).
The `Login.tsx` component exports `DEMO_PASSWORD`.

### Ports and health

- API `http://localhost:8000` (explorer `/docs` off unless `SIH_DOCS_ENABLED=true`),
  UI `http://localhost:5173`
- `GET /health` (JSON, includes the simulated clock), `/health/live`,
  `/health/ready`, `/metrics` (token-gated)
- Frontend calls the API directly at `http://localhost:8000/api/v1`
  (`VITE_API_BASE` overrides); CORS allows `http://localhost:5173`.

---

## 3. Architecture

```
React SPA (Vite + TS, hash routing)          frontend/src
   │  fetch + Bearer JWT, 401 → session-expired event
   ▼
FastAPI  /api/v1                             backend/app/api
   ├─ deps: require(permission) / require_any(...)  → authorization_service
   ├─ services: workflow · compliance · evidence · rule_engine · rehearsal
   │            audit · alerts · deadlines · monitoring · reports · seed
   ├─ adapters: ocr (real|mock) · llm (mock, unwired) · malware (clamav) · notifications (mock)
   └─ models: SQLAlchemy 2 declarative       backend/app/models
        ▼
   SQLite (dev/tests) or PostgreSQL (prod)   Alembic: backend/migrations/versions (6)
   Files: backend/storage                    Rules: backend/rules/*.json
```

**Languages/deps:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, pydantic-settings,
pypdf + pypdfium2, pytesseract (host `tesseract` binary), python-multipart,
python-dotenv. Frontend: React 18, TypeScript, Vite — **no UI kit**; custom CSS
in `styles.css`, icons are **inline SVG** in `components/Icon.tsx`.

---

## 4. What is built (verified working)

### 4.1 Authentication and authorisation
- JWT (HS256, issuer/audience/leeway configured), PBKDF2-HMAC-SHA256 at 260k
  iterations, dummy-hash on unknown email to avoid user enumeration.
- **Sign-in throttling** (`services/login_throttle.py`): two keys —
  `(account, client-IP)` and client-IP alone. 5 failures/account, 25/IP,
  900 s window, 900 s lockout, persisted in `login_attempts` so it survives
  restarts. **Runs on `wall_now()` (real time), never the demo clock** — see
  §8, bug fixed 26 Oct.
- **Sign-in channel** (`api/auth.py::_sign_in_comes_from_the_screen`): a
  request without the sign-in screen's origin is `403` before any throttle
  row or audit row is written. A channel rule, not a security boundary — a
  client can copy `Origin`; the password check and throttling do the real
  work.
- RBAC + scope: role permission ("may act") and scope (global / region /
  institution / committee / assigned cases) resolved from
  `user_role_assignments` — never from query parameters. The same scope
  function produces dashboard/report SQL, so numbers reconcile by construction.
- 6 roles × permissions in `core/permissions.py` (`ROLE_PERMISSIONS`).
- `POST /auth/change-password` revokes previously issued tokens (via the `pwd`
  claim = password hash marker).

### 4.2 Applications and workflow
- `Application` carries `category`, **`route_key`**, `cycle`, `current_state`,
  `status`, `assigned_officer_id`, `baseline_version`, `current_state_since`.
- **4 routes** in `backend/rules/workflow_routes.json`, each a state machine
  with per-stage SLA days:
  | route_key | path |
  |---|---|
  | `new_technical` | draft → submitted → scrutiny → (returned) → evc_scheduled → evc_completed → approved / rejected |
  | `existing_technical` | draft → submitted → scrutiny → approved / rejected |
  | `evc_only` | draft → submitted → (returned) → evc_scheduled → evc_completed → approved / rejected |
  | `evc_sac_shc` | draft → submitted → scrutiny → evc_scheduled → evc_completed → sac_review → approved / rejected |
- Transition guard order is fixed (8 steps, audited on rejection):
  **scope → permission → role → route → state → reason → documents → rules**.
- Actions can require a reason, specific uploaded documents, and specific rules
  to pass — all declared in JSON, not code.
- **Undo**: `POST /applications/{id}/revert` restores the previous state with an
  audit entry (`revert_last_transition`).
- `GET /workflow/routes` publishes the catalogue the UI renders.
- Automatic case hand-off: `case_assignment_service` assigns the case to
  whoever may act next (the role allowed on the outgoing transition).
- **Optimistic concurrency (H.1):** `POST .../transitions` and `.../revert`
  accept an optional `expected_baseline_version`; a mismatch is rejected with
  the standard `{accepted: false, reasons:[...]}` envelope, an audit event and
  no partial write. Omitting the field keeps last-write-wins (UI adopts it in
  AGENT-11). See `IMPL-0002`.

### 4.3 Documents and evidence
- Upload: `POST /applications/{id}/documents` with `doc_type`. Safety chain:
  **magic-byte sniffing** (never trusts Content-Type) → streaming size limit
  (10 MB) → filename sanitisation → optional ClamAV (off by default, fails
  closed with 503) → **SHA-256** + cross-institution duplicate detection →
  extraction → audit. Allowed types: `application/pdf`, `image/png`,
  `image/jpeg` (**DOCX returns 415 — see §6**).
- Extraction produces `ExtractedField` rows: `value` (JSON), `source_page`,
  `source_span`, **`method`** (which engine produced it), **`confidence`**,
  **`verification_status`** (`unverified` → `verified`/`rejected`), `verified_by/at`.
- Per-field officer verification: `POST .../fields/{field_id}/verify` — and
  `baseline_version` bumps when verification changes, which feeds the
  rehearsal diff.
- **Rule input contract:** a field that is extracted but *unverified* degrades
  to `NEEDS_REVIEW`; a field that does not exist degrades to `NOT_EVALUATED`.
  Nothing silently passes.
- Parsers (`adapters/ocr/real.py::_PARSERS`): `lease_deed`, `ownership_record`,
  `affidavit`, `faculty_list`, `fire_safety_certificate`. PDF text layer is used
  when present; otherwise pages are rasterised with **pypdfium2** (`scale=2.0`)
  and read with Tesseract `image_to_data` (per-word confidence).
  Unknown `doc_type` → warning "manual field entry required" (returns **0 fields**).
- Mock OCR (`adapters/ocr/mock.py`) is selectable (`SIH_OCR_ENGINE=mock`) and
  emits `simulated=True`; production validation rejects a non-`real` engine.

### 4.4 Compliance rule engine (the determinism core)
- `services/rule_engine.py`: **no `eval`**, allow-listed operator grammar,
  three-valued logic (true/false/unknown), outcomes
  `PASS · NEEDS_REVIEW · NOT_EVALUATED · FAIL · NOT_APPLICABLE`.
- Rules are **data** (`backend/rules/compliance_rules.json`, version `2026.1`)
  with `applicability`, `condition`, severity, `blocking`, and per-outcome
  mapping (`missing_outcome`, `unverified_outcome`, `failure_outcome`), plus a
  `regulatory_reference` string carried onto every finding.
- **7 rules today:** `LEASE_VALID_COVERS_PERIOD`, `LEASE_ISSUING_AUTHORITY`,
  `REQUIRED_DOC_AFFIDAVIT`, `LEASE_DATE_CONSISTENCY`,
  `INSTITUTION_IDENTITY_MATCH`, `EXISTING_INSTITUTION_FACULTY_RATIO`,
  `UNDERTAKING_NO_OVERDUE`.
  Every `regulatory_reference` still reads *"clause mapping pending
  verification"* — see `things.md` P0-2/4.
- Rule **versions are immutable once approved** (`rule_versions.status`,
  migration `0004_rule_immutability_trigger`), with `content_hash`,
  approver and effective dates; `rule_tests` store golden inputs per version.
- Regulatory verification is tracked separately from approval lifecycle (`rule_versions.regulatory_status`, migration `e3a8c2b1d740`); the current clause-pending rules are Unverified, so their findings stay visible but cannot block workflow or require a disposition. The finding API and UI show this status.
- `services/evidence_service.py::build_snapshot` builds the plain-value
  snapshot the rules read (values + `verified` map + `source` map) — no ORM
  objects cross into the engine.
- Evaluation persists a `RuleEvaluation` batch (`POST /applications/{id}/compliance/evaluate`,
  `GET .../compliance`), each row carrying rule key, version, outcome,
  explanation, evidence refs, missing/unverified inputs, severity, blocking.
- **The gate:** `workflow_service` blocks a transition when any required rule
  result is not `PASS`/`NOT_APPLICABLE`, returning an audited rejection.

### 4.5 Deficiency loop (merged 25 Oct, branch `feat/document-verification`)
- `Deficiency` model: `draft → open → addressed → closed`, linked to
  application, document, extracted field and corrective document; carries
  `rule_key`, `field_name`, `extracted_value`, `explanation`, `corrective_action`,
  resolver + resolution note.
- API `/applications/{id}/deficiencies`: list · create · patch · close.
- `return_for_clarification` **promotes `draft` deficiencies to `open`**, so
  they become visible to the institution at the moment the officer sends the
  case back.
- `services/validation_service.py` ("deterministic AI copilot") checks two
  lease rules (`LEASE_VALID_FUTURE_DATE`, `LEASE_LESSEE_MATCH`) and auto-creates
  a `draft` deficiency quoting the verbatim `source_quote`.
- UI: `StatusTracker` shows a Deficiency Notice to the College; `EvidencePanel`
  gains "mark field wrong" and "add manual deficiency" (448 new lines).

### 4.6 LLM usage today
- **Only one live call site:** `services/grounded_lease_extractor.py` for
  `lease_agreement` documents — raw `urllib` to **Gemini** when
  `SIH_GEMINI_API_KEY`/`GEMINI_API_KEY` is set, otherwise a deterministic
  parser that cites the document verbatim. Extracts Lessor, Lessee, property
  address, Expiry with `value` + `source_quote` + `ai_reasoning`.
  Wired in via `ocr_service.DispatchingExtractor`.
- `adapters/llm/` (`base.py` Protocol with `Citation`, `GroundedAnswer`, and a
  refusal-to-invent contract) + `mock.py` — **implemented but not wired to any
  endpoint**; it exists so the interface is real and UI can be built against it.
- Known weaknesses of the current call site: hardcoded `confidence=0.98`,
  `print()` logging, no retry/model fallback, Gemini-only.
  **Planned: replace with an OpenRouter adapter** (`models:[...]` native
  fallback, `json_object` + Pydantic validation, PDF → image via the existing
  pypdfium2 renderer) — see §6 and `things.md`.

### 4.7 Undertakings, deadlines and alerts
- `Undertaking` rows (obligation, condition text, evidence required, `due_at`,
  `status`) that an officer can create, waive, or verify; a College submits
  evidence against them.
- **A late undertaking blocks approval** (rule `UNDERTAKING_NO_OVERDUE`).
- `deadline_service`: idempotent sweep, threshold crossings → alerts with a
  `dedupe_key` so the same nag never fires twice; `alert_service` resolves
  recipients and delivers through the (mock) notification adapter, with
  deliberate failure modes so retries are testable.
- `backend/rules/deadline_policy.json`: 4 profiles (`undertaking`,
  `document_expiry`, `stage_ageing`, `evc_visit`) with offset/severity ladders.
- Alerts: list, acknowledge, close-with-reason — all audited.

### 4.8 EVC (field visit) scheduling
- `EvcVisit` model (committee, `scheduled_date`, `venue`, `status`, `notes`,
  `completed_at`), `Committee` model.
- Endpoints: list committees · list visits · **schedule visit** (auto-advances
  the case via `schedule_evc`, rejects if the route has no EVC stage) ·
  **`GET /evc/queue`** — reports cases at an EVC stage, cases holding a live
  booking, **and (Phase 6.1, FR-18) cases their own route says are due for an
  EVC now** (`schedule_evc` defined from the current state, no visit booked —
  `awaiting_scheduling` flag); all derived on read.
- UI: "Committee visit" tab (`EvcPanel`) + queue in `ReportsView`.
- **Gap:** completing a visit only flips status/timestamps
  (`_complete_evc_visits`) — there is no structured visit report, no named
  field officer, no geotag. See `things.md` §4b.

### 4.9 Audit trail
- Hash-chained `audit_events` (`prev_hash` → `hash`, SHA-256 over canonical
  JSON), `audit_chain_head` for the tip, `GET /audit/verify` re-walks the chain.
- Every business change commits with its audit row; rejections are committed
  after rollback so neither can be lost. `retention_service` deliberately never
  deletes audit events.
- UI: `AuditTimeline` renders the case history in plain language.

### 4.10 Rehearsal ("Approval Crash-Test")
- Separate simulation schema (`sim_runs`, `sim_input_snapshots`,
  `sim_rule_results`, `sim_metrics`) with a read-only baseline connection and a
  sim-only writer; `production_modified: false` is asserted by tests.
- Officer picks plain-language hypothetical overrides (`RehearsalPanel`) →
  before/after diff per rule (`resolved | remaining | new | regressed | unchanged`),
  plus metrics (one deliberately null: Load Factor).

### 4.11 Monitoring, dashboard, reports
- `officer_dashboard`: dashboard, pendency, ageing, escalations, assignments —
  all scope-filtered.
- `reports`: pendency, regions, evc, undertakings, documents, overdue,
  workload (+ a consolidated payload) — computed through the caller's scope,
  never cached or synthetic.

### 4.12 Frontend (18 components)
- `App.tsx` shell: auth gate, sidebar, **hash routing** `#/cases`,
  `#/monitoring`, `#/reports`, `#/cases/<id>` (back/forward honoured),
  session-expiry event handling, case list + search.
- `Login.tsx` typed credentials · `CaseView.tsx` (694 lines) role-split
  workspace (College journey vs Checker workstation) · `StatusTracker` plain
  journey + deficiency notice · `EvidencePanel` (803 lines) upload/preview/
  verify/mark-wrong/manual deficiency · `FindingsTable` + `OutcomeBadge` ·
  `UndertakingList` · `AlertList` · `AuditTimeline` · `DashboardView` ·
  `ReportsView` · `EvcPanel` · `RehearsalPanel` · `NewApplicationForm` ·
  `RouteScoreboard` (Table 2.3 scoreboard, `#/routing`) ·
  `Icon.tsx` inline SVG set (279 lines).
- `labels.ts` is the **plain-language dictionary**: every backend code (state,
  action, outcome, rule key, doc type, alert, role, verification) maps to a
  human label + icon + tone, plus `formatDate/formatDateTime/isOverdue/daysUntil`.
  `types.ts` mirrors the API shapes; `api.ts` is the single transport layer.
- Helpers: `uploadCheck.ts` (mirrors backend upload rules), `useDraft.ts`
  (localStorage form drafts), `useFileCheck.ts`, `useRefreshOnFocus.ts`.

---

## 5. Data model (28 tables)

`regions · institutions · applications · documents · extracted_fields ·
committees · evc_visits · deficiencies · readiness_flags · stage_instances ·
users · roles · permissions ·
role_permissions · user_role_assignments · jurisdiction_assignments ·
case_assignments · login_attempts · undertakings · rule_evaluations · alerts ·
alert_deliveries · audit_events · audit_chain_head · workflow_transition_defs ·
workflow_transitions · rules · rule_versions · rule_tests ·
sim_runs · sim_input_snapshots · sim_rule_results · sim_metrics`

Migrations: `backend/migrations/versions/` — `075aed043fd2_initial_schema`,
`0002_sim_schema_and_finding_labels`, `0003_auth_hardening`,
`0004_rule_immutability_trigger`, `0005_alert_lifecycle`, `0006_revert_support`,
`0007_document_upload_reason`, `0008_deficiencies_and_evc_visits`,
`0009_application_items`, `0010_readiness_flags`, `0011_stage_instances`,
`0012_workflow_reason_code`.

---

## 6. What is NOT built (the honest gap list)

This is the part most likely to be wrong if you assume the repo is finished.
Detail and ordering: **`things.md`**.

| Gap | Status | Where it belongs |
|---|---|---|
| **`university_noc` document type** — no parser, no UI type, no rules. A readable NOC uploads as 201 with `fields_extracted: 0` | not started | `things.md` P0-1 |
| **NOC / Change-of-Site rules with real APH citations** (7 lease rules exist; **0 NOC rules**) | not started | P0-2, P0-4 |
| **`change_of_location` category + route** (Scrutiny → EVC per Table 2.3) | not started | P0-3 |
| **DOCX acceptance** — `allowed_upload_types` is PDF/PNG/JPEG only → HTTP 415 | not started | P0-5 |
| **Address data anywhere** — `Application` has no address field, `Institution` has only `aicte_id/name/region_id`, zero hits for `geocode\|latitude\|pincode`; the lease parser extracts **no address** (except the grounded extractor's property address) | not started | `things.md` §4b |
| **Three-value model** (`extraction_value` / `claim_value` / `application_value` + `edited`) — only one `value` column exists | not started | Layer 2 of the build plan |
| **Bounding boxes / reviewer document viewer** — `source_span` is a string, no bbox column, no DPI stored, no viewer | not started | P1-8, Layer 6 |
| **Findings relabel in the UI** (`PASS → Pre-check passed`, `NEEDS_REVIEW → Review required`, `FAIL → Deficiency candidate`) — codes are right, wording is not | not started | P1-7 |
| **Verification report export** (JSON/PDF with rule version + APH base) | not started | P1-9 |
| **OpenRouter LLM adapter** (model fallback, structured-output validation, RAG reviewer assistant) | not started; Gemini-only call exists | build plan Layers 1b/7 |
| **`other` doc type generic labelled-field fallback** — returns nothing today | not started | P0-1 |
| **Structured EVC visit report, named field officer, geotag** | not started | §4b |
| **Virus scan, object storage, async OCR** | ClamAV implemented but off; OCR is synchronous in the request; local filesystem storage | acceptable for the prototype |

**Never build / never claim** (product rules that override any future plan):
never output "Approved" or "Rejected" as a machine verdict — only
*Pre-check passed · Review required · Deficiency candidate*; signature/seal
detection is a risk indicator, never proof of authenticity; no invented NOC
expiry rule; content-equivalent document formats must pass; every finding
carries an APH citation; no scraping of, or writes to, the AICTE portal;
blockchain is explicitly not wanted (the hash chain already provides
tamper-evidence).

---

## 7. Tests, gates and CI

- `make test` → **725 passing** (~500 test functions; some parametrised).
- Test harness (`backend/tests/conftest.py`): temp SQLite, **fixed clock
  `2026-10-22T09:00:00Z`**, test JWT secret, low PBKDF2 iterations,
  drop-create-seed per test, `as_user()` helper.
- `backend/tests/pdf_factory.py` builds **real minimal PDFs** so extraction
  tests read genuine bytes (including Tesseract OCR paths).
- Suites: `test_api` (15) · `test_audit` (5) · `test_rbac` (10) ·
  `test_workflow` (7) · `test_routes_and_revert` (10) · `test_rule_engine` (13) ·
  `test_rules_service` (5) · `test_document_extraction` (10) ·
  `test_evidence_flow` (8) · `test_undertakings_and_gate` (11) ·
  `test_deficiency_loop` (1) · `test_alerts` (12) · `test_rehearsal` (8) ·
  `test_reports` (6) · `test_case_assignment` (5) · `test_hardening` (27) ·
  `test_ai_copilot` (1) · `test_concurrency` (7 — Phase 0.5 H.1: stale
  `expected_baseline_version` rejected and audited on transition/revert) ·
  `test_transaction_boundary` (8 — Phase 0.5 H.2: one commit per workflow
  action; audit/visit-update failure rolls the whole action back) ·
  `test_authz_matrix` (21 — Phase 0.5 H.3: every permission-gated route
  × six demo roles × in-scope/out-of-scope case, plus the coverage guard
  that keeps the matrix in step with the routes the app actually declares) ·
  `test_document_versioning` (7 — Phase 0.5 H.4: replacement uploads create
  an immutable new version with a reason, extraction stays linked to its
  version, partial storage failure leaves no row or file, file-signature
  mismatch refused) ·
  `test_table_2_3_data` (5 — Phase 1.1: the 21 Table 2.3 routing rows in
  `workflow_routes.json` keep their shape, vocabulary, EVC-n/a flag and
  unverified/advisory status) ·
  `test_routing` (10 — Phase 1.2: category → ordered stage list for the
  four PRD §6 patterns, conditional shc/appeal stages, unknown
  category/pattern fails loudly) ·
  `test_routing_table_2_3` (24 — Phase 1.3: one parametrised test per
  Table 2.3 row checking route, window and stage order against an
  independent transcription of the PRD table) ·
  `test_combined_applications` (8 — Phase 1.4: combined cases run the
  ordered union of their categories' stages and keep one outcome per
  category; duplicate category refused; cascade delete) ·
  `test_sequencing` (7 — Phase 1.5: the merger category reports itself
  blocked until the Women's conversion clears; rule cites cl. 2.13.1m) ·
  `test_additional_evc` (9 — Phase 1.6: random EVC for SD (2.3.5) and a
  second EVC after a site shift (2.17e) as advisory configuration; no
  authority guessed) ·
  `test_aa_gate` (8 — Phase 1.7: the "AA" gate opens SHC/SAC only on a
  deficiency or negative scrutiny result (FR-10); undecided or unknown
  results answer `needs_review`, never a guessed open/closed) ·
  `test_fallback_eoa` (9 — Phase 1.8: the fallback-to-EoA branch is
  eligible after "not approved" on three categories (FR-11) but never
  auto-issued; "requirements are met" is an unevaluated placeholder) ·
  `test_route_scoreboard` (8 — Phase 1.9: `GET /workflow/table-2-3-scoreboard`
  returns all 21 rows with coverage `21/21`, auth-gated, read-only) ·
  `test_working_calendar` (24 — Phase 2.1: IST/working-day/holiday maths and
  Public Notice + Academic Calendar lookups (FR-37); no date invented — an
  unconfigured year answers `None`, never a guessed window) ·
  `test_readiness_cutoff` (14 — Phase 2.2: cut-off check tags next AY and
  never rejects (FR-02); no date/time → `needs_review`, never a guessed
  pass; status vocabulary provably has no rejected/blocked) ·
  `test_blocked_flags` (31 — Phase 2.3: the five FR-03 flags evaluate
  three-valued from config (`flagged`/`clear`/`needs_review`; unrecorded
  input is never read as false), officer clear/hold persists one audited
  row, `rejected` is a 422, scope miss is 404) ·
  `test_lease_check` (23 — Phase 2.4: FR-05/RULE-LEASE-01 remaining
  lease-years vs longest course duration; duration ships null (nothing
  invented) so production answers `needs_review` with the computed
  years; equality = "stopped unless extended"; reads the persisted
  grounded-extractor output, never re-parses PDFs at read time) ·
  `test_portal_feed` (17 — Phase 2.5: FR-01 stubbed portal feed; the
  seven PRD fields in order, PID/institution-type/TER-status served
  null (never guessed), `as_of` from the clock, scope-filtered so an
  other-institution case never leaks) ·
  `test_stage_graph` (18 — Phase 3.1: FR-09 stage graph; per-route
  ordered PRD §7 stages, `active_states` cross-checked against each
  route's real transitions, authorised completion auto-advances
  (re-entry reactivates one row), a terminal decision completes only
  entered stages, a refused transition changes nothing, a revert
  rewinds the graph; derived rows never gate or move a case) ·
  `test_reason_codes` (21 — Phase 3.2: FR-28 reason code + free text
  mandatory on return/revert; placeholder vocabulary in config
  (`reason_codes.json`, unverified), unknown/out-of-scope codes and
  codeless returns refused with the valid list named, code persisted
  on the transition row and in the audit `after`, `reject` keeps
  free-text-only, `GET /workflow/reason-codes` serves the vocabulary) ·
  `test_stage_limits` (15 — Phase 3.3: stage limits as labelled
  placeholder day counts (§19 Q1), moved unchanged out of
  workflow_routes.json (cross-config: stage sets match the stage
  graph; all 14 old values pinned), per-stage due dates computed on
  read from active stint + configured days, nothing stored) ·
  `test_escalation` (35 — Phase 3.4: escalation chain as labelled
  placeholder (§11 line 12 project proposals; §19 Q5 open → roles not
  names), L0–L3 roles with L2 a labelled placeholder and L3 unmapped
  (resolves to nobody, never an invented authority), the 70/90/100/125%
  ladder and 1-/3-working-day unassigned rules as pure lookups,
  working-day maths from calendars.json, recipient resolution reusing
   regional/supervisory officers, advisory read-only snapshot + endpoint,
   sweep payload carries the level additively) ·
   `test_appeal_clock` (23 — Phase 3.5: FR-27 appeal clock as labelled
   placeholder (REG-APPEAL-001 unverified), 7-day window + one-appeal
   limit + day-3/day-6 reminders all in `appeal_policy.json`, window
   anchored on `current_state_since` and end-of-day in the business tz,
   one-appeal count from `WorkflowTransition` rows by a configured action
   (0 until 6.6 defines `file_appeal`), advisory read-only snapshot +
   `GET .../appeal-window` (no gate/audit/migration), sweep raises the two
   reminders idempotently via the existing `dedupe_key`; no new workflow
   states — `file_appeal` and the Speaking-Order-upload trigger are the
   approval-gated 6.5/6.6 tasks) ·
   `test_security_deposit` (21 — Phase 3.6: FR-33 security-deposit penalty
   schedule as labelled placeholder (APH cl. 2.25f / PRD §7 line 244), 15-day
   proof window + 10%/20% penalties + 31-May/31-Jul fixed dates all in
   `security_deposit_policy.json`, penalty band from calendar-anchored date
   maths (inclusive boundaries; a date past 31 Jul reports the withdrawal
   marker with no penalty percent), the 15-day proof obligation rides the
   existing Undertaking model so day-1/10/14 come free from the
   `undertaking_due` ladder, advisory read-only snapshot +
   `GET .../security-deposit` (no gate/audit/migration, never withdraws —
    the withdrawal marker is advisory, an actual withdrawal is the rule-15
    gate) ·
   `test_alert_snooze` (5 — Phase 3.7: PRD §11 line 293 one snooze with a
   reason, no second; `Alert` gains `snoozed_until`/`snooze_reason`/
   `snoozed_by` (migration 0013), `POST /alerts/{id}/snooze` with a mandatory
   reason and a caller-bounded 1–30-day hold, "no second" enforced by data
   (`snoozed_until` set ⇒ the handler answers with the current state, never
   extends); a snooze is a temporary hold, not a terminal — `status` is left
   alone so an expired snooze makes the alert deliverable again, unlike
   ack/close; writes an `alert.snoozed` audit event; suppressed while
   unexpired).
   `test_demo_clock.py` (12 — Phase 3.8: admin-only demo clock.
   `demo_clock.py` service (`status_view`/`advance`/`set_to`/`reset`) with a
   **hard production refusal** (403 before anything runs, even for an
   administrator) and a refusal to pretend when no `FixedClock` is installed
   (409 on a live `SystemClock`); every move audited with before/after instants;
   `reset` re-reads the `SIH_CLOCK_FIXED_AT` baseline and refuses loudly if
   none; `GET/POST /admin/demo-clock/*` all gated `ADMIN_USERS` (4 matrix rows);
   the required prod-refuses test monkeypatches a production-shaped `Settings`;
   `DemoClock.tsx` admin panel (Jump 1/3/7 days + Reset) wired into `App.tsx`
   as a `demo` hash view gated on `admin.users`, rendering a switched-off
   message when the API reports `enabled:false`).
   `test_reconcile.py` (9 — Phase 3.9: clock reconciliation.
   `services/reconcile.py` recomputes every clock-derived date (stage-ageing
   SLA, per-stage due, undertaking `due_at`, scheduled EVC visit) from the
   current clock + config via the *same* readers the sweep uses, then diffs
   against what the live reader reports; **read-only**, never repairs.
   Frozen `Alert.due_at` snapshots are surfaced in `frozen_alerts` with an
   explanatory note but never counted as drift (an alert describes the cycle
   it fired in, so a live recompute legitimately differs after a transition).
   `GET /internal/reconcile-clocks` (`ADMIN_USERS`, matrix row) +
   `scripts/reconcile_clocks.py` nightly job (`--fail-on-diff` for a
   monitoring cron). The exit-check property holds: reconciliation stays 0
   after a 30-day demo-clock jump).
  `test_phase3_exit_check.py` (7 — Phase 3 exit check: the demo narrative
  composed end to end on one seeded case — silence before the first lead
  time, `due_soon`→L0 at 80%, `overdue`→L1 at 100% (regional officer in
  recipients), `escalated`→L2 at 150% (supervisory officer), each payload
  carrying `escalation_level` on the sweep's own clock; time moves through
  the real audited `demo_clock.advance` service; re-sweep creates nothing
  new; `reconcile` reports 0 drift at every stop and the
  `/internal/reconcile-clocks` endpoint confirms it after the jumps;
  process-wide clock reset after every test).
  `test_annexure_checklist.py` (18 — Phase 4.2: the Annexure-2 checklist
  beside the documents (FR-13). `annexure_2.json` carries all 21 Table 2.3
  categories; only t23-13 (Change of Site) is transcribed (Format-2 NOC,
  Format-3 resolution, new-site lease/ownership, sourced from `things.md`
  §1), every other category ships an empty list + a "needs review, list
  not transcribed" note (§19 Q8); the checklist is computed on read and
  stored nowhere; a case with no recorded category answers `needs_review`
  with a note, an unrecognised/untranscribed category answers per-category
  `needs_review` (never a 500, never an empty all-clear); presence is not
  validity; rejected documents do not satisfy a line; the blurriest
  category wins; endpoint is `require_any(CASE_READ, APPLICATION_READ)`
  and scope-filtered).
  `test_scrutiny_results.py` (24 — Phase 4.3: the scrutiny result per
  checklist line and overall (FR-14). `scrutiny_results.py` records the
  officer's verdict with remarks; the vocabulary is read from
  `aa_gate.scrutiny_results` (the PRD's own wording via the FR-10 gate,
  never invented); a result only attaches to a real line — category
  recorded on the case AND item in the configured list; an untranscribed
  list is refused as needs-review, never accepted as empty; overall
  `nil_deficiency` is refused while any item result is `deficiency`
  (self-consistency one way only — `deficiency` overall with clean items
  is allowed because a deficiency may live outside the checklist);
  re-recording updates the single row (audit keeps both); `results_view`
  joins checklist+results, keeps+flags orphaned results (a rule edit
  never erases a judgement), `derived_overall` stays None until every
  line is decided, and composes the FR-10 `aa_gate` answer;
  `ScrutinyItemResult`/`ScrutinyOverallResult` + migration
  `0015_scrutiny_results`; `GET/POST .../scrutiny-results` +
  `POST .../scrutiny-results/overall` gated `CASE_TRANSITION`, audited,
  422 on refusal; 3 matrix rows; EvidencePanel result-recording UI
  (per-line remarks + Nil/Deficiency buttons + overall form, gated
  `case.transition`; 422 shown as the server's own words)).
  `test_compliance_report.py` (25 — Phase 4.4: the deficiency report and
  the compliance window (FR-15). `compliance.py` computes the report on
  read: issue instant = the accepted `return_for_clarification`
  transition, close = end-of-day in the business timezone at issue +
  `window_days − 1`; before issue the institution is *always* answered
  `not_issued` (the status value alone must not leak that a draft
  exists); window open → overdue → received, with
  `resubmitted_at`/`awaiting_re_scrutiny` surfacing the Re-Scrutiny leg;
  overdue never blocks a resubmission (proven) and the report stores
  nothing (row counts + baseline_version unchanged across reads);
  `compliance_policy.json` placeholder window (10 days, §19 Q1 open) +
  `deadline_policy.json` `compliance` ladder = the PRD §11 "7d, 2d, due
  date" cadence as offsets from the close; the sweep raises
  `compliance_7d`/`compliance_2d`/`compliance_due` idempotently, stops
  on resubmit, and re-keys `compliance:{issue_date}` on a re-return;
  `GET .../deficiency-report` (`READ_ANY`, institution ⇒ drafts hidden,
  scope-filtered 404); EvidencePanel report/window summary; 1 matrix
  row; BUG-0014 open — `existing_technical` defines no return/resubmit
  route, so the loop is driven on `new_technical`).
  `test_doc_check.py` (24 — Phase 4.5: the RULE-DOC-01 document
  pre-check (FR-06). `doc_check.py` evaluates three legs on read — the
  Annexure-2 inventory (untranscribed ⇒ needs review, never an empty
  all-clear), Affidavit 2 (absent ⇒ candidate; present ⇒ satisfied but
  `confirmed:false` — the upload vocabulary cannot number the affidavit),
  and the DSC signature (a stub ⇒ **always needs review**, never
  passed/failed); the outcome vocabulary is `md/rules.json`'s own, pinned
  to the spec file by a test, with the precedence labelled prototype
  policy; `needs_review` rides every response including `PRE-CHECK
  PASSED`; `POST .../doc-check/drafts` stages uncovered candidates as
  audited `draft` rows keyed by line (idempotent while a live row covers
  the line; a `closed` row does not cover it), never moves the case and
  never leaks to the institution in 4.4's report; `GET` is a read-only
  `READ_ANY` route; EvidencePanel pre-check panel; 2 matrix rows;
  BUG-0015 fixed — a wrong test expectation, not service behaviour).
  `test_phase4_exit_check.py` (2 — Phase 4 exit check: the full
  deficiency → compliance → Re-Scrutiny loop composed on `app-main-0001`
  through the public API — pre-check → stage (idempotent, case
  unmoved) → drafts invisible (`not_issued`, zero rows) →
  `return_for_clarification` promotes + issues the report → corrective
  upload (observed: staged pre-check rows do **not** auto-address; the
  officer closes them) → audited one-day `demo_clock.advance` →
  `resubmit` → `received` + `awaiting_re_scrutiny` → close →
  `start_scrutiny`; audit chronology asserted on `AuditEvent.seq`;
  a row-count snapshot proves the reads store nothing; BUG-0016 +
  BUG-0017 fixed — both test-side, no product code changed).
  `test_doc_classifier.py` (19 — Phase 5.1: `doc_classifier.py`
  classifies an upload into the PRD's five ingest classes (EoA letter,
  Format-2 NOC, Format-3 Resolution, lease, affidavit) plus the "other"
  fallback, from `doc_classifier.json` phrase lists
  (proposed_unverified placeholder, class list pinned to the PRD §8
  sentence by a test) and `ExtractionResult.page_texts`; honest
  `no_text`/`unclassified`/`ambiguous`, a file name alone never labels,
  an equal tie refuses to decide, a declaration mismatch is flagged in
  the upload's warnings on a 201 and the recorded doc_type is never
  touched; BUG-0018 fixed — the note now composes the filename and
  mismatch caveats).
  `test_field_provenance.py` (10 — Phase 5.2: `ExtractedField` + candidate
  gain `bbox` (JSON, normalised `origin: top_left`/`level: line` line box),
  `engine` (pypdf/tesseract/mock/grounded_lease/gemini) and `engine_version`
  (read at runtime, cached); line geometry from pypdf `visitor_text`
  baselines (widths **estimated** — a highlight aid) and Tesseract
  `image_to_data` pixel unions; `_locate` value → parser label → honest
  `None` (no match ⇒ no highlight); mock/grounded/seeded rows keep NULL
  provenance; officer verification never rewrites it; migration
  `f7e6eed3fa19`; BUG-0019 fixed — run `ruff --fix` right after
  `alembic revision`).
  `test_fuzzy_grounding.py` (13 — Phase 5.3: `fuzzy_grounding.py` grounds
  a model value against the page's OCR words or marks it
  `REVIEW_REQUIRED` (FR-40); fuzzy token match with thresholds declared
  as labelled placeholders in `rules/fuzzy_grounding.json`; honest
  failures (no page text / empty / too short) all ⇒ review, never a
  pass; only config's `model_methods` are grounded; warnings ride
  `extraction.warnings` on a 201 with value/status/doc_type untouched;
  `ExtractedField.grounding` column, migration `b2fade9a8767`, NULL for
  OCR/mock/seeded rows and immutable under verify; BUG-0020 fixed —
  `case_sensitive` polarity was inverted at the read site; BUG-0021 +
  BUG-0022 test-side fixes).
  `test_three_value.py` (15 — Phase 5.4: FR-41 three-value model — the
  institution's Claim Value stored beside the extraction (4 nullable
  columns, migration `70f34e02fce5`), an edit needs a reason (400 with
  nothing recorded otherwise), master slot honestly `None` (no source
  integrated), RULE-EDIT-01 answers `continue`/`REVIEW REQUIRED` only
  about provenance, snapshot equality before/after a claim proves an
  edit can never clear a failed rule; claim endpoint 200/400/403/404 +
  audit; BUG-0023/0032 work-in-progress failures root-caused; BUG-0033
  one-off non-reproducible matrix failure).
  `test_evc_queue.py` (11 — Phase 6.1: FR-18 the EVC queue entry after
  scrutiny when the route needs it; "route needs EVC" read from the
  route's own `schedule_evc` transition definitions (never the
  category), unscheduled awaiting rows flagged `awaiting_scheduling`,
  derived on read (read-only snapshot), booking keeps the appointment
  whether or not the statutory gate opens, `evc_only` submit → queue →
  gated-advance walk, `MONITORING_READ` 403 / 401, regional scope,
  config-honesty of queued states).
- Gates to run before you push: **`make lint && make test && make build`**.
  CI (`.github/workflows/ci.yml`) runs the same. Keep all three green — the
  repo is currently green at `da23713` (**836 passed**, two upstream
  Starlette deprecation warnings, zero skips) after Phase 5 exit check
  (`da23713`, IMPL-0067), the programmed Phase 6 wave and Phase 7
  (Codex, IMPL-0060–0065), and the cross-review of the Phase 5+6 body
  (IMPL-0066, no violations found). Phase 5 line 90 stays Partial: the
  public EoA letter as master record is not copied into the repo until a
  human supplies it (IMPL-0049/DEC-0013). Next per plan: Phase 6 exit
  check (line 103), Phase 7 exit check (line 110), Phase 8 exit check
  (line 116).
- **28 Oct 2026 — Phase 8 exit checks (FR-50):** the tamper demo proves both sides on a temporary DB (untouched chain verifies, altered chain detected) and the Phase 8 targeted tests pass (15). Audit coverage now matches every implemented mutation route — appeals (Phase 6.6) emit all eight audited actions; the only open source is rule-configuration editing, which lands with the Phase 9.4 console (IMPL-0068; Phase 6 exit stays Partial per human decision on the deposit-intimation seam).
- **28 Oct 2026 — Phase 9.1 lease thin slice (FR-45):** integrated proof that a verified lease expiry drives the configured document_expiry ladder — advance reminders on a near expiry, all four levels with regional escalation on a far-past expiry, dedupe per lease on repeat sweeps; unverified dates still raise nothing. No product change; the ladder stays in `rules/deadline_policy.json`. `make test` **838 passed** (IMPL-0069).
- **28 Oct 2026 — Phase 5 exit check (FR-38–FR-48):** the change-of-site demo walk now runs through the real upload pipeline: labelled extraction parsers for the EoA letter, Format-2 NOC and Format-3 resolution (fictional values; provenance page/engine/bbox on every auto-filled field), a reason-gated claim edit that never touches the Extraction Value, E02 address/survey mismatch and SITE-01 partial-shifting advisory findings carrying the DEFICIENCY CANDIDATE label (advisory flags confirmed non-actionable), a real bbox for the evidence highlight, and confirm-one/dismiss-one on the operational findings (refusals audited). `make test` **836 passed**, ruff clean (IMPL-0067; BUG-0075).
- **27 Oct 2026 — Phase 5.5 (FR-42):** E01–E03 advisory cross-checks compare configured latest-document Extraction Values only. Their field paths are labelled placeholders; the rules remain Unverified and every formal result is `REVIEW REQUIRED`. Claim Value edits do not affect the diagnostic. Verification: `make lint` clean, `make test` **758 passed**, frontend build clean (IMPL-0044 / DEC-0008); Phase 5 continues at 5.6.
- **27 Oct 2026 — Phase 5.6 (FR-43/FR-44):** SITE-01 phrase/programme-list and SITE-02 jurisdiction diagnostics added with labelled placeholders and a synthetic-only jurisdiction fixture; neither can conclude compliance or jurisdiction. All formal outcomes remain `REVIEW REQUIRED`. `make lint` clean, `make test` **764 passed**, frontend build clean (IMPL-0045 / DEC-0009); Phase 5 continues at 5.7.
- **27 Oct 2026 — Phase 5.7 (FR-46):** compliance response now includes an advisory aggregate label. Unverified/missing checks require review; a discrepancy may be marked candidate but never creates a deficiency or changes workflow. A pass requires every mapping Verified. `blocking`, `creates_deficiency`, and `automatic_workflow_action` are always false. `make lint` clean, `make test` **769 passed**, frontend build clean (IMPL-0046 / DEC-0010); Phase 5 continues at 5.8.
- **27 Oct 2026 — Phase 5.8 (FR-47):** persisted operational red (`FAIL`) and amber (`NEEDS_REVIEW`) findings now expose stable IDs and support audited human dispositions; every transition leaving scrutiny is rejected and audited until all current-baseline findings have one. Dismissal requires a reason; neutral findings cannot be disposed. Unverified Phase 5 prototype diagnostics stay outside the gate. `make lint` clean; `make test` **771 passed, 1 upstream warning, 0 skipped**; SQLite migration upgrade/check clean (IMPL-0047 / DEC-0011). Phase 5 continues at 5.9; UI controls remain in 5.11.
- **27 Oct 2026 — Phase 5.9 (FR-39/FR-51):** optional OpenRouter vision adapter accepts only low-confidence pages whose trusted server-side source is explicitly public/synthetic; default switch stays off, including with an API key configured. Strict JSON-schema output is locally validated and every field is grounded against OCR text. `ExternalCallLog` records request metadata only; images, text, responses and keys are excluded. The key was placed in ignored local `.env` (permissions 600); `.env.example` keeps it blank. The upload API does not mark sources trusted, so no ordinary uploaded documents can be sent externally. `make lint` clean; `make test` **776 passed, 1 warning, 0 skipped**; migration upgrade/check clean (IMPL-0048 / DEC-0012); Phase 5 continues at 5.10.
- **27 Oct 2026 — Phase 5.10 (FR-38/FR-42/FR-44):** added a clearly synthetic EoA-shaped master-record test fixture plus labelled Format-2-style and Format-3-style JSON fixtures. A public EoA document is registered as a source pointer only; the real institution PDF/data are not copied into the repo. Regression coverage drives existing classifier, E01–E03 comparison and SITE-01/02 services; results remain advisory and `REVIEW REQUIRED`. The public EoA master-record part is not integrated, so plan item 5.10 remains partial (IMPL-0049 / DEC-0013).
- **27 Oct 2026 — Phase 5.11 (FR-41/FR-47/FR-48):** added the split review, evidence highlight, and “Edited after extraction” badge, claim editing and audited officer disposition controls. `npm run build` clean; `make lint` clean; `make test` **777 passed, 1 upstream warning, 0 skipped**. An isolated synthetic browser smoke confirmed claim edit and officer confirm/dismiss UI. The broader Phase 5 exit check remains open: no public EoA master data or site-move upload autofill is integrated, and the seeded one-page placeholder PDF points one field at page 2 (IMPL-0050 / DEC-0014; BUG-0044–0046).
- **27 Oct 2026 — Phase 8 audit work:** document content access and extraction
  lifecycle, finding-batch evaluation, automatic assignment, and explicit
  verification/export events are covered; a scoped JSON export checks the
  global chain and records the export. `scripts/tamper_demo.py` uses a
  throwaway SQLite DB and proves clean/tampered outcomes. The timeline UI
  describes the hash chain as tamper-evident and has explicit verify/export
  actions. Phase 8 is **Partial**: audit sources for rule/configuration edits
  and appeals do not exist until their planned capabilities are built (Phase
  6/9); see IMPL-0042 and plan 8.1.
- **27 Oct 2026 (this machine):** the local clone had no `.venv`, so I ran
  `make setup` under **Python 3.14.3** (the repo targets 3.13; 3.14 not
  previously recorded). Backend deps installed and the suite is green on
  3.14. **Correction (5.2):** an earlier version of this note said
  "Tesseract is not installed here, so the 2 OCR tests skip" — that was
  wrong: Tesseract **5.5.3** is present at `/opt/homebrew/bin/tesseract`
  (symlink dated 24 Oct 2026, i.e. installed before that note was written),
  so the suite runs **0 skipped** and every `requires_ocr` test executes
  for real (3 of them now: 2 in `test_document_extraction.py` + 1 in
  `test_field_provenance.py`). BUG-0001 stays `Workaround` — the skip path
  remains the honest degradation for hosts *without* the binary.

---

## 8. Recent history (what changed lately)

```
eb4d051 fix: two bugs that made the demo impossible to sign in to
906d3dc chore: ruff clean after the deficiency-loop merge
889c026 feat: structured deficiency loop and grounded AI copilot   (branch merged)
9694ad3 Fix document visibility for authorized officers            (branch merged)
a01f8f5 chore: ruff clean across the merged feature branches
af33989 fix: the failed-session notice must not follow you into the app
25f3b17 docs: quick start is now make setup + make dev (~5 min)
1685f05 feat: five-minute setup — make setup and make dev
```

**All feature branches are deleted; `master` is the only branch.**

### The two sign-in bugs (fixed in `eb4d051`) — do not reintroduce
1. **Throttling ran on the frozen demo clock.** `login_throttle` was stamped
   with `get_clock().now()`, which is a `FixedClock` at `2026-10-22T09:00:00Z`.
   Every attempt got the same instant, so the 15-minute window never aged out,
   the retention purge never fired, and `unlock_at - now` stayed pinned — five
   wrong passwords locked an account **permanently** while promising "try again
   later" (reproduced: `Retry-After: 901` twice, six seconds apart).
   Throttling now uses `login_throttle.wall_now()`; the 429 message states the
   real wait. Regression test:
   `test_hardening.py::test_lockout_window_uses_wall_clock_not_the_frozen_demo_clock`
   (verified to fail on the old code).
2. **`scripts/dev.sh` matched any socket on the port**, not just listeners, so
   an open browser tab holding a `CLOSE_WAIT` socket to a dead backend made
   `make dev` refuse with "Port 8000 is already in use" — and its own remedy
   (`lsof -ti:8000 | xargs kill`) would have killed the browser. The check now
   requires `-sTCP:LISTEN` and prints the pid.

**Rule of thumb:** the injected demo clock (`SIH_CLOCK_MODE=fixed|offset`) is
for the *case narrative* only. Anything operational — lockouts, token expiry,
wall-clock SLAs — must use real time.

### Known state of the local demo database
`backend/sih26262.db` has drifted from the seed through manual testing: 7
applications (3 extra test cases), 15 documents, `app-existing-0003` is
`approved`, `app-main-0001` is `returned`. Use the clean-slate recipe in §2
before a demo.

---

## 9. Conventions (enforced, not optional)

1. **No emoji anywhere in the product** — icons are inline SVG
   (`components/Icon.tsx`, keyed by `IconName`).
2. **Plain language in the UI**; jargon lives behind a "Technical details"
   disclosure. All user-visible wording goes through `labels.ts`.
3. **Do not break `frontend/src/api.ts` or `types.ts` contracts** — they are
   the typed boundary to the API. Add, don't rewrite.
4. **No silent failures or stale panels** — a panel that cannot load says so;
   every mutation refreshes what it touched (`useRefreshOnFocus` exists).
5. **Real behaviour over mock** — mock adapters exist for determinism in tests
   and are always labelled `simulated: true`. Do not ship mock results as real.
6. **Determinism** — the rule engine never uses `eval`, never calls a model,
   and produces the same output for the same snapshot and rule version.
   An LLM may extract or explain; it may never decide.
7. **Every rejection is audited** (with reason); every finding carries its
   `regulatory_reference`.
8. **No invented regulation** — if the APH clause is not known, the reference
   stays "clause mapping pending verification" rather than a guessed number.
9. Three outcomes only: **Pre-check passed · Review required · Deficiency
   candidate.**

---

## 10. API map (one line per endpoint, all under `/api/v1`)

```
auth          POST /auth/login (UI origin only) · GET /auth/me · POST /auth/change-password
applications  GET|POST /applications · GET /applications/{id} · GET .../evidence · GET .../compliance
documents     GET|POST /applications/{id}/documents · GET .../{doc}/content · POST .../{doc}/fields/{f}/verify
compliance    POST /applications/{id}/compliance/evaluate
deficiencies  GET|POST /applications/{id}/deficiencies · PATCH .../{id} · POST .../{id}/close
coi           POST|GET /applications/{id}/conflicts-of-interest · POST /conflicts-of-interest/{id}/review (declare hides the case from the declarer; advisory only)
readiness      GET /applications/{id}/blocked-flags · POST /applications/{id}/blocked-flags/{flag_id} · GET /applications/{id}/lease-check
portal         GET /portal/feed (FR-01 stub: 7 fields + as_of; scope-filtered; read-only)
workflow      GET /workflow/routes · GET /workflow/table-2-3-scoreboard · POST /applications/{id}/transitions · POST .../revert · GET .../transitions
undertakings  GET|POST /applications/{id}/undertakings · POST .../{id}/waive|submit|verify
rehearsals    POST /applications/{id}/rehearsals · GET /rehearsals/{run_id}
evc           GET /evc/committees · GET|POST /applications/{id}/evc/visits · GET /evc/queue
alerts        GET /alerts · POST /alerts/{id}/ack · POST /alerts/{id}/close · POST /internal/deadline-sweep · GET /internal/deadline-preview · GET /internal/reconcile-clocks
audit         GET /applications/{id}/audit · GET /audit/verify
officer       GET /officer/{dashboard,pendency,ageing,escalations,assignments}
reports       GET /reports (+ /pendency /regions /evc /undertakings /documents /overdue /workload)
admin         GET /admin/{roles,users,audit} · POST /admin/assignments · POST /admin/assignments/{id}/revoke · GET|POST /admin/demo-clock{,/advance,/set,/reset} (admin.users)
institutions  GET /institutions
app-level     GET / · /health · /health/live · /health/ready · /metrics
```

---

## 11. Where to go next

| You want to… | Read |
|---|---|
| Understand the system design | `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/ROLE_MODEL.md` |
| Understand rules and outcomes | `docs/RULES.md`, `docs/EVIDENCE_INTELLIGENCE.md` |
| Understand the rehearsal engine | `docs/REHEARSAL_ENGINE.md` |
| Run the demo in front of judges | `docs/DEMO_SCRIPT.md`, `docs/USER_JOURNEY.md`, `docs/ACCEPTANCE_TESTS.md` |
| Know what was deliberately deferred | `docs/DEFERRALS.md`, `docs/PRODUCTION.md` |
| **Start the next feature (NOC)** | **`things.md`** — research, P0–P3 backlog, §4b location/EVC plan, build order |
| Quick start as a new person | `README.md` |

### Current build order (from the Layer 0–9 plan reconciled with `things.md`)

1. DOCX text extraction + keep pypdfium2 (no Poppler)
2. `university_noc` parser (11 fields incl. old/new address) + `other` fallback
3. Address field on `Application` + address in the lease parser
4. `change_of_location` route (Scrutiny → EVC)
5. 14 NOC rules with citations (extend the existing engine, do not write a new one)
6. Decision aggregation + NOC gate (reuse the existing transition guard)
7. Findings UI with observed/expected + APH source; relabel outcomes
8. OpenRouter adapter + confidence-triggered fallback
9. Static "Why this failed" panel (no LLM)
10. Three-value field model + autofill API
11. Ten NOC fixtures in `make test`
12. Reviewer page-level view → bbox overlay (needs bbox + DPI columns)
13. Citation-grounded reviewer assistant (only after 9)

Phase 6.2 reminder update: EVC visits now have 7/2/1-day advance alert levels in `backend/rules/deadline_policy.json`, tested and labelled Unverified operational placeholders; overdue/escalation alerts remain. Named expert assignment, confirmation authority, and the Region calendar remain open pending the human decision requested for Phase 6.2 (IMPL-0051 / DEC-0015).
Phase 6.2 update: visit scheduling also records online/physical mode and Monitoring now shows a scope-filtered upcoming Region calendar. Existing visits retain unknown mode; expert assignment and confirmation still need an authority decision (IMPL-0052 / DEC-0016).
Phase 6.2 complete: active committee-scoped EVC members can be assigned (open-COI members excluded); institution representatives confirm visit bookings; API/UI/audit/migration verified (IMPL-0053 / DEC-0017). Phase 6.3 is next; fraud referral and subsequent committee/decision routes remain subject to human authority and regulatory-source approval.
Phase 6.3 complete: assigned EVC experts upload human reports; completed visits with reported deficiencies appear in the regional SHC queue; fraud flags create pending Competent Authority referrals without penalty or automated findings (IMPL-0054 / DEC-0018). Next: Phase 6.4 SHC scheduling and recommendation.
Phase 6.4 complete: SHC can schedule hearings, record human compliance notes and recommendations; completed recommendations appear in a region-scoped Executive Committee queue with scoped EVC report download. No decision or case transition is inferred (IMPL-0055 / DEC-0019). Verification: `make lint`, `make test` (794 passed, 1 upstream warning, 0 skipped), frontend build and SQLite migration upgrade/check through 0021. Next: Phase 6.5 human Executive Committee decision and Speaking Order (FR-26).

Phase 6.6 complete: verified Chapter II appeal rules are implemented for `existing_technical`, `evc_only`, and `evc_sac_shc`: institution filing, SAC schedule/recommendation, Council final decision and order, scoped evidence, role permissions, audit and UI (IMPL-0057 / DEC-0021). `make lint`, `make test` (809 passed, 1 upstream warning), frontend build, SQLite migration upgrade/check pass. `new_technical` remains excluded until its Chapter I appeal rule is verified. Next: Phase 6.7.

Phase 6.7 complete: one-time submitted-state reopening now requires a same-case resolution, scoped Competent Authority approval with applicable Public Notice reference, and human verification of linked TER/penalty payment evidence before the configured transition resumes the case. Annual fee/deadline values are not guessed; in-process route coverage remains out of scope pending mapping (IMPL-0058 / DEC-0022). Verification: `make lint`; `make test` 815 passed/2 upstream warnings; frontend build; SQLite migration upgrade/check through `c78327c876fb`. Next: Phase 6.8.

**48-hour cut line: items 1–9 + 11.**

Phase 6.8 implemented and tested: human-reviewed Chapter II grant batches carry per-course approved intake and explicit Academic Calendar date/source; Council ratification, EoA letter upload, guarded publication, institution scoped view/download and audit are added. Chapter I remains excluded and dates/intake are not inferred (IMPL-0059 / DEC-0023). Verification: `make lint`; `make test` 820 passed / 2 upstream warnings; frontend build; fresh SQLite upgrade/check through `d948f3303deb`. Full Phase 6 exit journey remains partial because yearly security-deposit inputs are placeholders.
2026-10-28 S1 safety update: rule approval lifecycle is separate from regulatory-source verification. All current clause-pending rules are Unverified and advisory only; only Verified blocking outcomes can gate transitions or dispositions (IMPL-0060 / DEC-0024). Verification: `make lint && make test` (826 passed, 2 upstream warnings), frontend build, fresh SQLite upgrade/check and downgrade/re-upgrade. Phase 6 exit remained partial pending an integrated route test and deposit-intimation data; the route test is now covered by IMPL-0061.
2026-10-28 Phase 6 integration update: a synthetic public-API case now traverses submission, scrutiny, EVC, SHC, Executive Committee decision, appeal, Council approval, grant publication and advisory deposit read in one test (IMPL-0061). Journey test passes. Phase 6 exit remains partial: the app has no separate deposit-intimation event/date or case fields for §2.25(e–f) applicability/exemptions; placeholder penalty figures remain advisory.
2026-10-28 Phase 7.1 complete: Institution, Scrutiny, Regional and Regulation Bureau roles now see scope-filtered dashboards with a reconciling application list for every displayed metric. Institution and Regulation Bureau receive only the narrow `dashboard.read` permission; reports and general case reads remain unavailable through that permission (IMPL-0062 / DEC-0025). Verification: `make lint && make test` (828 passed, 2 upstream warnings), focused dashboard/authz tests (37 passed), frontend build.
2026-10-28 Phase 7.2 complete: dashboards include age bands, weekly stage throughput, overdue/due-soon cases by stage/region/officer, EVC queue status and visit mode, deficiency/compliance issued/closed/overdue metrics, and returns/reverts grouped only by recorded reason codes. Scoped rows reconcile with displayed metrics; rejections without a reason-code field are explicitly surfaced uncoded. Stage-limit, compliance-window, and return/revert-code configuration is visibly marked placeholder/advisory (IMPL-0063 / DEC-0026). Verification: `make lint && make test` (829 passed, 2 upstream warnings), focused dashboard/RBAC suite and frontend build.
2026-10-28 Phase 7.3 complete: monitoring-authorized roles can download seven scoped PRD §12 report families as PDF or UTF-8 CSV; advisory labels are preserved and appeal grounds/meeting links are excluded. Region performance is grouped by the cycle recorded on the case. Verification: `make lint`; `make test` (833 passed, 2 upstream Starlette warnings, 116.30s); frontend production build passed (IMPL-0064 / DEC-0027).
2026-10-28 Phase 7 complete: monitoring-role report exports and dashboard aggregates reconcile to the server-scoped case lists; tests cover Scrutiny, Regional, Supervisory and Administrator report access scopes, plus Institution, Scrutiny, Regional and Regulation Bureau dashboard drilldowns. Verification: `make lint`; `make test` (833 passed, 2 upstream Starlette warnings, 116.30s); frontend production build passed (IMPL-0065 / DEC-0028).
2026-10-28 Phase 9.2 complete: Security Deposit proof clock begins only when an officer records the separate notice date and links the same-case notice document; approval alone creates no undertaking. Institutions link uploaded proof/Affidavit 3 document IDs on submission, officers verify, and configured day 1/10/14 reminders dedupe. Window and penalty values remain placeholders/advisory (DEC-0029 / IMPL-0070). Verification: `make lint`; `make test` 843 passed, 2 upstream warnings; frontend production build; temporary SQLite migration upgrade and `alembic check` passed. Phase 6 remains partial pending official deposit-intimation applicability/exemptions/verification.
2026-10-28 Phase 9.3 partial: added PRD-candidate fee table for additional EVC and Scrutiny/SHC/SAC fees, plus a guarded lookup engine. Unverified table returns no payable amount and cannot block; activation needs named clause review, institution-class mapping and payment evidence model (DEC-0030 / IMPL-0071). Phase 9.3 remains unchecked until those inputs and the P1 gates are complete.
2026-10-28 Phase 9.4 complete: added admin policy drafts and version history for routes, deadlines, fees, escalation and templates; different administrator approval, hash audit and immutable approved snapshots. Approved deadline ladders now feed both alert preview and sweep; other categories remain staged history without runtime consumers. No Unverified fee activates (DEC-0031 / IMPL-0072). Verification: `make lint`; `make test` 852 passed/2 upstream warnings; frontend build; SQLite migration upgrade/downgrade/re-upgrade, direct SQL immutability triggers and `alembic check` passed.
2026-10-28 Phase 9.5 complete: fixed-clock composed test uses the admin draft/second-admin approval path and proves an approved reminder-offset change moves the actual alert sweep timing for the same synthetic due date (IMPL-0073). Full Phase 9 remains partial: Phase 9.3 additional-fee blocks are not active pending named Chapter II clause review plus institution-class/payment evidence inputs (IMPL-0071).
2026-10-28 OCR/evidence retrieval improvement: hybrid PDFs now OCR sparse or image-only pages even when other pages have text; local lease agreement extraction covers common address/expiry labels; extracted values cite matched source lines; evidence list supports query and review-only filtering. Uploads consistently use configured local OCR (IMPL-0074 / DEC-0032). Verification: `make lint`; `make test` 856 passed/2 upstream warnings; focused OCR/evidence tests 24 passed; frontend production build passed.
2026-10-28 Scanned EoA follow-up: selected `eoa_letter` uploads now OCR the repository's three-page scan and return institution/trust identity, addresses, approval metadata, change-options text, and per-course programme/intake rows with page evidence; OCR fields remain unverified. Legacy lease scanning uses the same local OCR reader (IMPL-0075 / BUG-0084 / DEC-0032). Verification: `make lint`; `make test` 858 passed/2 upstream warnings; frontend production build passed.
2026-10-28 EoA OCR verification update: change-options aggregate now derives from geometry-detected option rows after the scan showed the next course heading was not reliably legible as text. Focused regressions 3 passed/1 upstream warning; `make lint`; `make test` 858 passed/2 upstream warnings/0 skipped; frontend production build passed (IMPL-0076 / BUG-0086). OCR values remain candidates for human review.
