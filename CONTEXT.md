# CONTEXT.md — read this first

Everything an AI (or a new teammate) needs to work on this repository without
re-discovering it. Last verified against a running stack and a green test
suite on **26 Oct 2026**.

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
make test      # pytest — 457 passing
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
  **`GET /evc/queue`**.
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

- `make test` → **457 passing** (~414 test functions; some parametrised).
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
  read from active stint + configured days, nothing stored).
- Gates to run before you push: **`make lint && make test && make build`**.
  CI (`.github/workflows/ci.yml`) runs the same. Keep all three green — the
  repo is currently green at `65d5850`.

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
readiness      GET /applications/{id}/blocked-flags · POST /applications/{id}/blocked-flags/{flag_id} · GET /applications/{id}/lease-check
portal         GET /portal/feed (FR-01 stub: 7 fields + as_of; scope-filtered; read-only)
workflow      GET /workflow/routes · GET /workflow/table-2-3-scoreboard · POST /applications/{id}/transitions · POST .../revert · GET .../transitions
undertakings  GET|POST /applications/{id}/undertakings · POST .../{id}/waive|submit|verify
rehearsals    POST /applications/{id}/rehearsals · GET /rehearsals/{run_id}
evc           GET /evc/committees · GET|POST /applications/{id}/evc/visits · GET /evc/queue
alerts        GET /alerts · POST /alerts/{id}/ack · POST /alerts/{id}/close · POST /internal/deadline-sweep · GET /internal/deadline-preview
audit         GET /applications/{id}/audit · GET /audit/verify
officer       GET /officer/{dashboard,pendency,ageing,escalations,assignments}
reports       GET /reports (+ /pendency /regions /evc /undertakings /documents /overdue /workload)
admin         GET /admin/{roles,users,audit} · POST /admin/assignments · POST /admin/assignments/{id}/revoke
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

**48-hour cut line: items 1–9 + 11.**
