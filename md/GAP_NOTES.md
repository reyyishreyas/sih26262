# GAP_NOTES.md — rules inventory (plan 0.4) and gap matrix (plan 0.5 / AGENT-01)

- Date: 2026-10-26 · Agent: MiMo (OpenCode agent) · Branch: master @ `a3477cb`
- Linked: `IMPL-0001`, `docs/DECISIONS.md`, `docs/TRACEABILITY.md`
- Method: files below were **opened and read this run** unless marked *(reported — spot-check next task)*. Status words per the PRD vocabulary; "Implemented" never means "regulatory Verified".
- Lives in `md/` (not `docs/prd/GAP_NOTES.md`) per DEC-0004.

---

## 1. Rules-as-data inventory (what `backend/rules/*.json` contains today)

### 1.1 `workflow_routes.json` — 4 routes (PRD wants 21 Table 2.3 category rows)
| route_key | States | Verdict vs PRD |
|---|---|---|
| `new_technical` | draft→submitted→scrutiny→(returned)→evc_scheduled→evc_completed→approved/rejected | SCR+EVC shape ✓ |
| `existing_technical` | draft→submitted→scrutiny→approved/rejected | SCR shape ✓ (the EoA workhorse) |
| `evc_only` | draft→submitted→(returned)→evc_scheduled→evc_completed→approved/rejected | SCR-less shape ✓ |
| `evc_sac_shc` | draft→submitted→scrutiny→evc_scheduled→evc_completed→sac_review→approved/rejected | SCR+EVC+AA shape ✓ (no "returned" from scrutiny, no reject at scrutiny) |

Gaps vs PRD §6 / plan Phase 1:
- **No SD (self-disclosure) route**; no category→route mapping table at all — `Application.category` (e.g. `new_technical`) *is* the route key today. Table 2.3's 21 rows are **not encoded**; no `routing.py`; no window (Public Notice vs year-round) field; no EVC-not-applicable flag (row 8 FN/OCI/Gulf); no combined-application model; no random-EVC / second-EVC action; no fallback-to-EoA branch; no "AA" gate rule (SHC only on deficiency).
- Stage SLA days exist per route (`stage_sla_days`) — values are illustrative config, labelled as such in the file's `note` ✓ (honest labelling already present).
- Transitions carry `required_permission`, `allowed_roles`, `required_rules`, `required_documents`, `requires_reason` — the policy-as-data contract the PRD wants is **already here**; Phase 1 should extend it, not replace it.

### 1.2 `deadline_policy.json` — 4 profiles
`undertaking` (-30/-7/+1/+7), `document_expiry` (-60/-30/+1/+15), `stage_ageing` (-2/+0/+5), `evc_visit` (-7/+0/+10). All offset/severity ladders with a disclaimer `note`.
Gaps vs PRD §10/§11: **no appeal 7-day clock**, **no security-deposit 15-day clock**, no 31-May/31-July penalty dates, no escalation chain (L0–L3), no 70/90/100/125% thresholds, no working-day/holiday calendar, no snooze. All of these are Unverified regulatory values → must land as **labelled, disabled/advisory config** (PRD §0; rules2 REG-CUTOFF-001), never as code constants.

### 1.3 `compliance_rules.json` — version `2026.1`, 7 rules
`LEASE_VALID_COVERS_PERIOD`, `LEASE_ISSUING_AUTHORITY`, `REQUIRED_DOC_AFFIDAVIT`, `LEASE_DATE_CONSISTENCY`, `INSTITUTION_IDENTITY_MATCH`, `EXISTING_INSTITUTION_FACULTY_RATIO`, `UNDERTAKING_NO_OVERDUE`.
- Contract per rule: `applicability`, `condition` (allowlisted ops), `missing_outcome`, `unverified_outcome`, `failure_outcome`, `blocking`, `severity`, `regulatory_reference` ✓ — matches rules1 `rule_engine_contract` shape closely; extension needed, not replacement.
- **Every `regulatory_reference` still reads "clause mapping pending verification"** except `LEASE_DATE_CONSISTENCY` ("Internal consistency requirement (prototype policy)"). → Consistent with essentials rule 4; needs the human clause-mapping from `docs/SOURCES.md` before any rule may gate on regulatory grounds.
- **0 NOC rules, 0 E01–E03/SITE-01/SITE-02/DOC-01 rules** (PRD §8 registry, scaffold, things.md P0-2). RULE-OCR-01 and RULE-EDIT-01 also absent (they are engine-level behaviours, not JSON rules today).

## 2. Gap matrix (plan 0.5 / AGENT-01) — FEAT-01…18

Legend: **I** = Implemented (code inspected) · **P** = Partial · **N** = Not started (search found nothing) · *(R)* = reported in CONTEXT.md/README, spot-checked only.

| ID | Feature | Evidence (files/symbols) | Status | Gap → plan task |
|---|---|---|---|---|
| FEAT-01 | Application intake/readiness | `api/applications.py` (GET/POST exist); **no** `services/readiness.py`, no cut-off/blocked-flag logic (search found nothing) | P | cut-off check + 5 blocked flags + portal stub → Phase 2 (2.2–2.5) |
| FEAT-02 | Workflow state machine | `services/workflow_service.py` (guard order scope→permission→role→route→state→reason→documents→rules verified in code lines 150–245); `rules/workflow_routes.json` | I | Table 2.3 routing + stage graph → Phase 1, 3 |
| FEAT-03 | Document upload/access | `api/documents.py`, `services/upload_validation.py` (magic bytes, 10 MB, SHA-256); `Document.version` column exists (`models/application.py:90`) | I (R) | replacement-creates-new-immutable-version semantics: verify in H.4 |
| FEAT-04 | OCR/field extraction | `adapters/ocr/real.py` (pypdf→pypdfium2→Tesseract), `adapters/ocr/mock.py`; `ExtractedField.{method,confidence,source_page,source_span}` | I (R) | **no bbox column, no DPI**; 5 parsers only; `university_noc`/`other` parsers absent → P0-1, Layer 6 |
| FEAT-05 | Compliance rule engine | `services/rule_engine.py` (no eval, 3-valued); rule versioning `models/rules.py` + migration 0004 immutability trigger | I (R) | NOC rules + clause mapping → Phase 5 / P0-2,4 |
| FEAT-06 | Evidence-linked review | `api/documents.py::verify` field endpoint; `evidence_service.build_snapshot`; unverified → NEEDS_REVIEW degradation | I (R) | split-screen + bbox highlight → 5.11 |
| FEAT-07 | Structured deficiencies | `models` Deficiency (`draft→open→addressed→closed`), `api/deficiencies.py` CRUD + close | I (R) | institution response does not overwrite officer finding: verify in AGENT-06 |
| FEAT-08 | Resubmission/revalidation | `workflow_service` `return_for_clarification` promotes drafts; documents re-upload path re-extracts | P | SYS-REVAL-001: record *which* checks were re-run; prior results auditable → AGENT-06 |
| FEAT-09 | Role/jurisdiction authorisation | `core/permissions.py` ROLE_PERMISSIONS (6 roles), `services/authorization_service.py`, scope from `user_role_assignments` | I (R) | full route×role×scope matrix test → H.3 |
| FEAT-10 | Automatic assignment | `services/case_assignment_service.py::assign_next_actors` (called in-transaction on transition) | I | no-eligible-officer visibility test → Phase 4.1 |
| FEAT-11 | Manual reassignment | **no per-case reassign endpoint** (search `reassign` → 0 hits); admin `POST /admin/assignments` + `/revoke` only changes role-scope | N | explicit reassignment with reason + audit → Phase 4.1 / AGENT-07 (needs approved policy — see PRD OPEN) |
| FEAT-12 | Deadlines/SLA | `services/deadline_service.py` (idempotent sweep, dedupe keys), `workers/scheduler.py` persistent worker, `POST /internal/deadline-sweep` manual | I | appeal/deposit clocks, calendar, escalation chain → Phase 3 |
| FEAT-13 | Notifications | `adapters/notifications/mock.py` only (`channel: in_app`, JSON-line log); base Protocol mentions email/SMS as future | P (mock) | channels stay mock until a provider is approved (deferred list) |
| FEAT-14 | Audit chain/verification | `services/audit_service.py` SHA-256 chain, `audit_chain_head`, `GET /audit/verify`, rejected actions committed post-rollback | I (R) | export+hash-check, tamper demo script, document-view logging → Phase 8 |
| FEAT-15 | Dashboards/reports | `api/officer_dashboard.py`, `api/reports.py`, `services/monitoring_service.py`, `reporting_service.py` | I (R) | role dashboards + PDF/CSV export → Phase 7 |
| FEAT-16 | EVC/committee/appeals | `api/evc.py` (committees, visits, schedule, queue); `evc_sac_shc` route has sac_review; **no appeal window/clock, no SHC/EC/Speaking Order models** | P | appeal clock + hearings → Phase 3.5, 6.4–6.6 |
| FEAT-17 | Lease/security-deposit monitoring | lease rules exist; undertakings due/overdue + alerts exist; **no security-deposit model/clock** | P | deposit 15-day clock → Phase 3.6, 9.2 |
| FEAT-18 | Admin/rule configuration | `api/admin_access.py` (roles, users, assignments, audit); rule versions via DB with immutability trigger; **no admin UI, no four-eyes approval, no calendars/fees console** | P | admin console → Phase 9.4 |

### 2b. Spec architecture constraints (rules3.json) — current state
| Requirement | Evidence | Status |
|---|---|---|
| ARCH-REHEARSAL-001 isolated rehearsal | `services/rehearsal_service.py` (baseline freeze, stale-run marking line 344–346), `models/rehearsal.py` sim_* tables, `sql/roles.sql` 4 roles, `scripts/verify_isolation.py` | I (R) — isolation proven only on PostgreSQL (`make verify-isolation`); SQLite dev cannot enforce it |
| ARCH-GROUNDING-001 OCR grounding + bbox | grounded lease extractor has `source_quote` grounding; **no fuzzy_grounding.py, no bbox columns, no coordinate contract** | P — grounding exists for one extractor only; bounding boxes N |
| ARCH-LLM-GUARD-001 ExternalCallLog + guardrails | `adapters/llm/base.py` Protocol + `mock.py` (unwired); `grounded_lease_extractor.py` is the only live call site (Gemini via urllib, hardcoded confidence 0.98, print() logging — weaknesses already noted in CONTEXT.md §4.6); **no ExternalCallLog model/migration, no external-call switch** (search `ExternalCallLog|external_call` → 0 hits) | P | full guardrail set → Phase 5.9 / addendum 7 |

### 2c. Cross-cutting requirements (rules2.json XREQ)
- **XREQ-SOURCE-001** — every rule carries a `regulatory_reference` string ✓ but no structured `source_id/clause/status/effective_from` fields on rules → extend rule schema when clause mapping starts (do not invent values).
- **XREQ-AI-001** — advisory-only enforced by design (three outcomes; engine cannot transition) ✓; low-confidence → REVIEW ✓ at engine level.
- **XREQ-AUDIT-001** — hash chain covers workflow/document/deficiency/undertaking/alert events ✓ (spot-checked in service code); **document *views* not audited yet** (Phase 8.1).
- **XREQ-TEST-001** — 163 tests; required groups partially covered; **missing**: authz matrix, concurrency/stale-write, document-versioning, audit reorder, deadline calendar, LLM failover (scaffold test list).

## 3. Priority order this audit suggests (reconciles with plan)
1. Phase 0.5 hardening first (H.1 stale-write enforcement is a real, verified gap — see DECISIONS D-0001).
2. Phase 1 routing (largest PRD delta; everything downstream keys off category→route).
3. Phase 3 clocks (appeal/deposit are demo-critical and currently absent).
4. Phase 5 grounding/bbox/three-value (the differentiator for the NOC story in things.md).
