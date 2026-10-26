# Implementation Plan

Rules for the agent: do **one unchecked task at a time, top to bottom**. Each task ends with `make lint && make test` (and `npm run build` for UI) green and the box ticked. Don't start a phase until the previous phase's **Exit check** passes. FR numbers refer to `1_PRD.md`.

**Baseline (already built, do not redo):** rule engine + versioning, workflow guards, audit hash chain, rehearsal engine + Postgres isolation, upload + OCR + evidence verify, undertakings, deadline scheduler, officer monitoring, auth hardening, review UI, Docker/prod/CI.
**Before Phase 0 ends, confirm by reading code** what `workflow_routes.json` and `deadline_policy.json` already contain, so you extend rather than duplicate.

---
## How this plan maps to the specification
| Spec phase | This plan | Agent tasks |
|---|---|---|
| 0 Discovery | Phase 0 | AGENT-01 |
| 1 Core consistency (workflow, authz, transactions/audit, doc access) | Phases 1, 3, 8 | AGENT-02, 03, 10 |
| 2 Documents/evidence | Phase 5 | AGENT-03, 04 |
| 3 Rules/deficiencies | Phases 4, 5 | AGENT-05, 06 |
| 4 Assignment/deadlines/alerts | Phase 3 | AGENT-07, 08 |
| 5 Reporting/routes | Phases 6, 7 | AGENT-09 |
| 6 Hardening | Phases 8, 10 | AGENT-10, 11, 12 |
Do not run phases concurrently without agreed interfaces (see `4_AGENTS.md`). Each phase's definition of done = code + tests + docs + limitations updated.

## Phase 0 — Align and baseline
- [x] 0.1 Run `make setup`, `make test`, `make lint`; record counts (expect 159 tests). → **163 passed, 1 warning, 0 skipped; lint clean** (2026-10-26, IMPL-0001). `make setup` not re-run (venv already healthy).
- [x] 0.2 Fix README test count (155 → actual) and note Python 3.13 / Node 26 as the verified versions. → repository-map line 155 → 163 (BUG-0002); verified locally: Python 3.13.9, Node v26.0.0.
- [x] 0.3 Copy the six docs into `docs/prd/` and `AGENTS.md`/`CLAUDE.md` into repo root. → **Deviation (DEC-0004):** planning docs live in `md/` (user's layout); no duplicate `docs/prd/` created. `AGENTS.md` + `CLAUDE.md` created at root with paths adapted to `md/`.
- [x] 0.4 Inventory current `workflow_routes.json`, `deadline_policy.json`, `compliance_rules.json` into gap notes (what exists vs PRD). → `md/GAP_NOTES.md` §1.
- [x] 0.5 **AGENT-01:** produce the gap matrix mapping FEAT-01…18 and the spec's sections to files/symbols (or confirmed search absence), each with an explicit status word. → `md/GAP_NOTES.md` §2.
- [x] 0.6 Create `docs/SOURCES.md`; record the exact official URL/version of SRC-PS-26262 and SRC-APH-2024-27 (human task; do not guess URLs). → **seeded**: APH/addendum/FAQ URLs copied from `things.md` research notes, attributed, marked *needs human verification*; SRC-PS-26262 exact URL unknown → null with required action.
- [x] 0.7 Create `docs/TRACEABILITY.md` seeded with the spec's rows (PRD-WF-001, PRD-AUTH-001, PRD-DOC-001, PRD-OCR-001, PRD-RULE-001, PRD-DEF-001, PRD-ASG-001, PRD-SLA-001, PRD-AUD-001, PRD-UI-001, REG-001, REG-002). → created; row meanings reconstructed from PRD context because the technical-spec file is not in the repo (flagged in the file).
- [x] 0.8 Answer from code and record in `docs/DECISIONS.md`: Is `baseline_version` enforced? Is the alert sweep scheduled or manual? Which notification channels are tested? Is manual reassignment present? Is COI present? Is Tesseract required or optional? → all six answered from code inspection.
- [x] **Exit check:** green suite (record skips), gap matrix, source register started. → 163 passed / 0 skipped; `md/GAP_NOTES.md`; `docs/SOURCES.md` seeded. Open: human clause verification (0.6).

## Phase 0.5 — Consistency hardening (AGENT-02, AGENT-03) *(do before new features)*
- [x] H.1 Enforce `baseline_version`: stale transition rejected; test concurrent and duplicate requests; invalid action leaves no partial write. → optional `expected_baseline_version` on transition/revert, audited rejection envelope, `test_concurrency.py` (7); 170 passed (IMPL-0002, BUG-0003, 2026-10-26).
- [x] H.2 Transaction boundary: state + transition + assignment + required audit commit together; audit-write failure fails the operation. → single commit per action; `_complete_evc_visits`/`_cancel_visits_on_revert` pulled inside the main transaction (BUG-0004 fixed); `test_transaction_boundary.py` (8); 178 passed (IMPL-0003, 2026-10-26).
- [x] H.3 Authorisation matrix test: every sensitive route × role × scope (institution/assignment/region); 404-vs-403 policy documented. → `test_authz_matrix.py` (21) driven by the 54 permission-gated routes discovered from the running app (coverage guard included), both gates proved by deliberate mutation; policy written up in `docs/ROLE_MODEL.md` §404-vs-403; 199 passed (IMPL-0004, 2026-10-26).
- [x] H.4 Document versioning: replacement creates a new immutable version with reason; extraction/finding links to a version; partial-storage-failure test; file-signature check. → `test_document_versioning.py` (7); `documents.upload_reason` column + migration 0007; BUG-0006 fixed (migrations 0008 for `deficiencies`/`evc_visits`); 206 passed (IMPL-0005, 2026-10-26).
- [x] **Exit check:** regression tests for all four pass; limitations listed. → `pytest test_concurrency + test_transaction_boundary + test_authz_matrix + test_document_versioning` = **43 passed**; `make lint` clean; `make test` = **206 passed, 0 skipped** (2026-10-26, after IMPL-0002…0005). **Limitations carried forward:** (1) optimistic concurrency is opt-in — clients that send no `expected_baseline_version` are unaffected; UI adoption is AGENT-11; the stale-write envelope is `200 {accepted:false}`, not 409 (open question for a human). (2) The H.3 matrix asserts authorisation, not business outcomes; nested-resource routes are probed with placeholder ids so their 404 can't distinguish scope from missing record; six seeded demo users only; Postgres/Compose not exercised. (3) H.4 verified on SQLite; migration 0008 not run against Postgres yet; `alembic check` is not in CI (question for a human). (4) Other mutation endpoints (field verify, deficiencies, undertakings) still lack the expected-version guard. (5) Tesseract present locally → 0 skips, but environments without it skip OCR tests (BUG-0001, Workaround). (6) Plan ticks live in the untracked `md/6_IMPLEMENTATION_PLAN.md` — not in version control until the user approves committing it.

## Phase 1 — Routing engine and Table 2.3 scoreboard (FR-07–FR-11) · build order #1
- [x] 1.1 Encode all 21 Table 2.3 rows in `workflow_routes.json` (category id, route, window, EVC-not-applicable flag for FN/OCI/Gulf). → `table_2_3` section added (additive; existing `routes` untouched), transcribed from the PRD's own Table 2.3, marked `unverified` + `advisory_only` per PRD §0/DEC-0003, each row citing its PRD source; `test_table_2_3_data.py` (5 contract tests); 211 passed (IMPL-0007, 2026-10-26).
- [x] 1.2 `services/routing.py`: category → ordered stage list; support SD, SCR, SCR+EVC, SCR+EVC+AA. → `app/services/routing.py` reading `table_2_3.route_patterns` (stage lists live in config, not code; `when` = always / if_deficiencies / on_decision); `test_routing.py` (10); 221 passed (IMPL-0008, BUG-0007, 2026-10-26).
- [x] 1.3 `test_routing_table_2_3.py`: one parametrised test per row (21 passing). → PRD table transcribed independently in the test; per-row route + window + stage order checked against `routing.py`; 24 passed in file, 245 overall (IMPL-0009, 2026-10-26).
- [x] 1.4 Combined applications: `ApplicationItem` model + migration; union of stages; per-category outcome (FR-08). → `ApplicationItem` (one row per category, unique per case, outcome nullable until that category decides) + migration 0009; `routing.stages_for_categories()` ordered union on new config `stage_order`; `test_combined_applications.py` (8); `alembic check` clean; 253 passed (IMPL-0010, 2026-10-26).
- [x] 1.5 Sequencing: Women's conversion before merger (2.13.1m). → `table_2_3.sequencing_rules` (t23-06 requires t23-16 cleared; rule cites its clause) + `routing.prerequisites_for()` / `routing.unmet_prerequisites()`; `test_sequencing.py` (7); 260 passed (IMPL-0011, 2026-10-26).
- [x] 1.6 Random EVC add for SD (2.3.5) and second EVC after site shift (2.17e) as authorised actions. → `table_2_3.additional_evc_actions` (two rows: `random_evc` by route pattern SD, `second_evc_after_site_shift` by category t23-14; both `unverified`/`advisory_only`, each citing its clause); `authorised_roles` left empty as a labelled placeholder (PRD §19 #4 open); `routing.additional_evc_actions()` / `evc_actions_for_category()`; `test_additional_evc.py` (9); 269 passed (IMPL-0012, 2026-10-26). Advisory lookup only — no transition, no authority invented.
- [x] 1.7 "AA" gate: SHC/SAC opens only on deficiency or negative outcome (FR-10). → `table_2_3.aa_gate` (opens on deficiency OR negative scrutiny result; result vocabulary from FR-14; undecided/unrecognised → `needs_review`, never a guessed open/closed); `routing.aa_gate()` / `aa_stage_is_due()`; `test_aa_gate.py` (8); 277 passed (IMPL-0013, 2026-10-26). Advisory — the stage graph (3.1) will consume it.
- [x] 1.8 Fallback-to-EoA branch after "not approved" (FR-11). → `table_2_3.fallback_eoa` (categories t23-03/05/16; trigger mapped provisionally to `rejected`; clauses 2.7l/2.14j/2.15e kept as a set, no clause→category mapping asserted; "requirements are met" = unevaluated placeholder); `routing.fallback_eoa_rule()` / `fallback_eoa_applies()` / `fallback_eoa_status()` → `review_required` | `not_applicable` | `not_triggered`; `test_fallback_eoa.py` (9); 286 passed (IMPL-0014, 2026-10-26). Advisory — a triggered case is never auto-issued.
- [x] 1.9 `GET` route-scoreboard endpoint + `RouteScoreboard.tsx`. → `routing.scoreboard()` + `GET /workflow/table-2-3-scoreboard` (auth-gated, read-only, no case data); `expected_rows: 21` config so coverage is a real check; `RouteScoreboard.tsx` as a 4th view `#/routing` behind `canMonitor`; `test_route_scoreboard.py` (8); 294 passed; `npm run build` clean (IMPL-0015, 2026-10-26).
- [ ] **Exit check:** scoreboard shows 21/21; audit events written for every routing decision. → **scoreboard 21/21: Met** (service + HTTP test assert `coverage == "21/21"`). **audit events: Partial** — the creation-time route is audited (`application.created` carries `route_key`, verified); the dedicated per-category route/stage-list decision event arrives with the stage graph (3.1) and is not faked. Phase 1 otherwise complete.

## Phase 2 — Readiness and intake (FR-01–FR-05)
- [x] 2.1 `calendars.json` + `working_calendar.py` (IST, holidays, Public Notice dates, Academic Calendar) (FR-37). → `calendars.json` (unverified/advisory; `timezone` Asia/Kolkata bound by test to `settings.business_timezone`; `weekend_days` config not code; **`years: {}` — no date invented** because the PRD/rules files record none, with a `template` for a reviewer to fill) + `policy.calendars()` + `working_calendar.py` (`business_date`, `public_notice_cutoff`, `academic_calendar`, `holidays_for`, `is_working_day`, `add_working_days` — unconfigured year → `None`, never a guess; no-working-day → raises, never hangs); `test_working_calendar.py` (24); 318 passed (IMPL-0016, 2026-10-26). FR-37 *load* half Partial by design: loader done, no year loaded pending an official date.
- [x] 2.2 `readiness.py`: cut-off check → tag next AY, never reject (FR-02). → `readiness_policy.json` (`cut_off` rule: `action_on_after_cutoff`, **`reject: false`** + reject_note, `date_source` → calendars.json; unverified/advisory) + `policy.readiness_policy()` + `readiness.cut_off_policy()` / `cut_off_check()` → `within_window` | `after_cutoff` (names the tag) | `needs_review` (no date / no submission time — never a guessed pass); status vocabulary provably has no rejected/blocked; pure, no state changed; `test_readiness_cutoff.py` (14); 332 passed (IMPL-0017, 2026-10-26). FR-02's *reject* half deliberately NOT implemented (PRD §0 + plan "never reject"); tag unpersisted — 2.3 owns flag persistence.
- [x] 2.3 Blocked-application flags: five rules from FR-03, officer can clear or hold. → `readiness_policy.json.blocked_flags` (5 rules `bf-01`…`bf-05` with the PRD's exact wordings + clauses 2.21f/2.16.1a/2.3.1/2.6e/2.27 — positional mapping labelled Unverified, cross-confirmed for 2.16.1a + cl. 2.6; declared `inputs` mostly `modelled: false` placeholders; unverified/advisory) + `readiness.evaluate_blocked_flags()` (three-valued: `flagged` = all inputs recorded & matching, `clear` = a *recorded* input provably fails, else `needs_review` — absent data is unknown, never false) + `ReadinessFlag` model + migration `0010` (`alembic check` clean) + `GET /applications/{id}/blocked-flags` (READ_ANY) + `POST .../{flag_id}` (`require(CASE_TRANSITION)`, `decisions: cleared|held` — `rejected` is 422) with `readiness_flag.decided` audit; matrix rows added; `test_blocked_flags.py` (31); 363 passed (IMPL-0018, 2026-10-26). Officer decision stored, evaluation never stored; no permission invented (CASE_TRANSITION, so scrutiny officer may also decide — limitation logged).
- [x] 2.4 Lease-years computation and flag (FR-05, RULE-LEASE-01), reusing the grounded lease extractor. → `readiness_policy.json.lease` (RULE-LEASE-01 cl. 2.1e, `longest_course_duration_years: null` — nothing invented, §19 Q11 open; `extension_years: 30` PRD-carried/Unverified; `extension_on_file` `modelled: false`) + `readiness.lease_check()` (three-valued `sufficient|insufficient|needs_review`; equality = "stopped unless extended"; expired lease insufficient without a duration; unverified evidence never decisive; 29-Feb anniversary clamps to 28-Feb) + `readiness.lease_evidence()` reading the **persisted** grounded-extractor output via `evidence_service.build_snapshot` (no re-parse, no model at read time; `lease_deed` then `lease_agreement`) + `GET /applications/{id}/lease-check` (`READ_ANY`, read-only, no audit — nothing changes); matrix row added; `test_lease_check.py` (23); 386 passed (IMPL-0019, 2026-10-26). Production answers `needs_review` with real computed years until a human records the duration; no migration (nothing new stored).
- [x] 2.5 Stubbed portal feed endpoint carrying the FR-01 fields, with "as of" timestamp. → new `rules/portal_feed.json` (FR-01/cl. 2.3.1 + §18 "as of" row; the seven fields in the PRD's order, `pid`/`institution_type`/`ter_status` declared `modelled: false` and served **null, never guessed**; `sync_cadence: null` — no cadence invented) + `policy.portal_feed_policy()` + `portal_feed.build_feed()` (submitted-only, deterministic order, scope-filtered with the same `scope_filter` as the applications list, rejected documents excluded) + `GET /api/v1/portal/feed` (`READ_ANY`, read-only; envelope `source: "stub"` + `as_of` from the injectable clock); matrix row added; `test_portal_feed.py` (17); 403 passed (IMPL-0020, 2026-10-26). **Ingestion deliberately not implemented** — a portal service identity + untrusted-write path are human approval gates; open question recorded.
- [x] **Exit check:** late application lands in next-AY queue; blocked flags visible to Regional officer. → **Both Met (advisory, per 2.2/2.3's design).** (1) A post-cut-off submission answers `status: after_cutoff` with `tag: queue_for_next_academic_year` and **never rejects** — asserted in `test_readiness_cutoff.py::test_a_submission_after_the_cutoff_names_the_queue_tag`; the tag is computed on read, not persisted as a queue row (2.2 scope: "never reject"; persisting a queue assignment is a state change left to Phase 3/4 workflow work — limitation carried). (2) The Regional officer sees all five FR-03 flags with evaluation + decision state — `test_blocked_flags.py::test_the_regional_officer_sees_all_five_flags` (API-level; no UI yet, AGENT-11).

## Phase 3 — Stage graph, clocks, escalation, demo clock · build order #2 (FR-09, FR-27, FR-33, §11)
- [x] 3.1 `StageInstance` model + migration; `stages.py` auto-advance on authorised completion (FR-09). → `rules/stage_graph.json` (per-route ordered PRD §7 stages ×4 routes, `active_states` mapping cross-checked against each route's own transitions, `terminal_states` mirroring `TERMINAL_STATES`; unreachable stages ship empty+labelled; **`sac_review` deliberately unmapped** — the PRD doesn't say whether it is SHC or Executive Committee, so no stage is mislabelled — open question) + `StageInstance` (unique application+stage, `sequence`/`status pending|active|completed`/`started_at`/`completed_at`/`completed_by`) + migration `0011` (`alembic check` clean) + `stages.sync_stage_instances()` hooked into `request_transition` (accepted path) and `revert_last_transition` (`retract=True`) in the same transaction — derived bookkeeping only: never moves a case, never gates a transition, never bumps `baseline_version`, no new audit events (the transition is already audited). Forward moves complete the stint they left; undos retract it; a terminal decision completes only entered stages plus earlier stages the route *provably* passed (cut-set over its transition graph) so seeded mid-flow cases record readiness honestly without ever completing an unentered stage; re-entry reactivates the same row (Re-Scrutiny ≠ second row). `test_stage_graph.py` (18); 421 passed (IMPL-0021, 2026-10-26).
- [x] 3.2 Return/revert with reason code + free text (FR-28); audit. → `rules/reason_codes.json` (**placeholder** vocabulary — the PRD mandates a code but never enumerates codes and §19 has no vocabulary question; 4 codes with `applies_to` return/revert + per-code source, `required_for_actions` config-scopes the mandate to returns so `reject` keeps free-text-only, cross-config-tested against `workflow_routes.json`) + `WorkflowTransition.reason_code` (nullable, migration `0012`, `alembic check` clean) + `workflow_service._reason_code_error()` — return/revert refuse without a valid code AND free text (both halves mandatory; unknown/revert-only-on-return codes refused with the valid list in the message; even non-mandated actions refuse an unvalidated supplied code) + code persisted on the transition row and echoed in the audit event's `after` (the §11 "returns by reason code" metric reads structured data) + `TransitionRequest`/`RevertRequest.reason_code` + `GET /workflow/reason-codes` (signed-in; serves the placeholder vocabulary) + `available_transitions` exposes `requires_reason_code`. `test_reason_codes.py` (21); 442 passed (IMPL-0022, 2026-10-26).
- [x] 3.3 `stage_limits.json` with **placeholder** day counts, clearly labelled; per-stage due dates. → `rules/stage_limits.json` (**placeholder** — PRD §19 Q1 asks AICTE for the official target days, so every count is a labelled project proposal citing it; per-route × per-PRD-stage, all 8 stages × 4 routes, values **moved unchanged** out of `workflow_routes.json`'s inline `stage_sla_days` blocks which are now removed — one source of truth, pinned test proves no behaviour change) + `state_overrides` for stages whose states count differently (EVC booked 30 vs held 10) + `unmapped_state_days` for `sac_review`'s 20 days (state ages honestly, stage label not invented — 3.1 open question carried) + explicit `days: null` + note wherever there is deliberately no clock + `policy.stage_limits_policy()` + `stage_sla_days()` rewired (same signature/values → sweep/monitoring/reporting/EVC unchanged) + `stages.due_dates()` — per-stage `days`/`due_at`/`placeholder`/`note` **computed on read** (active stages only; clock starts on entry, stops on completion; nothing stored). `test_stage_limits.py` (15, incl. cross-config stage-set equality + all 14 old values pinned); 457 passed (IMPL-0023, 2026-10-27).
- [ ] 3.4 `escalation_chain.json` + `escalation.py`: L0–L3 at 70/90/100/125%, unassigned-after-1-day rules.
- [ ] 3.5 Appeal: 7-day clock on Speaking Order upload; one appeal only; alerts day 3 and day 6 (FR-27).
- [ ] 3.6 Security Deposit: 15-day clock, alerts day 1/10/14, 10% penalty to 31 May, 20% to 31 July, withdrawal flag after (FR-33).
- [ ] 3.7 Snooze-once-with-reason.
- [ ] 3.8 `demo_clock.py` endpoint + `DemoClock.tsx`; disabled when `SIH_ENV=production`; test that prod config refuses it.
- [ ] 3.9 `reconcile_clocks.py` nightly job + report showing zero differences.
- [ ] **Exit check:** advance demo clock → alerts fire at configured lead times → escalate L0→L1→L2; reconciliation shows 0 diff.

## Phase 4 — Scrutiny, deficiency, compliance (FR-06, FR-12–FR-15)
- [ ] 4.1 Assignment by Region/workload + conflict-of-interest declaration and hiding (FR-12).
- [ ] 4.2 Checklist generated from category Annexure-2 list beside documents (FR-13); start with the Change of Site list, others as data.
- [ ] 4.3 Per-item and overall result with remarks (FR-14).
- [ ] 4.4 Deficiency report draft (labelled draft) → compliance window → institution upload → Re-Scrutiny (FR-15).
- [ ] 4.5 Affidavit 2 / DSC-signed check as RULE-DOC-01 (FR-06).
- [ ] **Exit check:** full deficiency → compliance → Re-Scrutiny loop for one seeded case.

## Phase 5 — AI pre-check for Change of Site · build order #4 (FR-38–FR-48)
- [ ] 5.1 `doc_classifier.py` for EoA letter, Format-2 NOC, Format-3 Resolution, lease, affidavit.
- [ ] 5.2 Store per-field bbox, confidence, engine+version, page (extend extracted-field model + migration).
- [ ] 5.3 `fuzzy_grounding.py`: model value must match OCR words on page else `REVIEW_REQUIRED` (FR-40).
- [ ] 5.4 `three_value.py`: Extraction / Claim / Master values, edit reason, RULE-EDIT-01 (FR-41).
- [ ] 5.5 Rules E01–E03 on Extraction Value (FR-42); test that an edit cannot clear a failed rule.
- [ ] 5.6 RULE-SITE-01 (phrase list + programme-list comparison) (FR-44); RULE-SITE-02 with synthetic `jurisdiction.json` (FR-43).
- [ ] 5.7 Outcome assignment PASSED / REVIEW / DEFICIENCY CANDIDATE; confirm none blocks (FR-46).
- [ ] 5.8 Gate: Scrutiny cannot complete until every amber/red finding has a disposition (FR-47).
- [ ] 5.9 Optional vision-model adapter (OpenRouter), config-driven model + 0.75 threshold, JSON-schema validated, **off by default**, `ExternalCallLog` for each call (FR-39, FR-51).
- [ ] 5.10 Synthetic Format-2 NOC and Format-3 Resolution fixtures, labelled synthetic; public EoA letter as master record.
- [ ] 5.11 `SplitReview.tsx`, `EvidenceHighlight.tsx`, `EditBadge.tsx` (FR-48).
- [ ] **Exit check:** demo steps 2–5 work: auto-fill → edit → amber badge → address mismatch + "partial shifting" red findings → highlight → confirm one, dismiss one.

## Phase 6 — EVC, SHC, decision, grant (FR-18–FR-27, FR-31–FR-32)
- [ ] 6.1 `EVC` model; queue entry after scrutiny when route needs it (FR-18).
- [ ] 6.2 Schedule online/physical, experts, confirmation, Region calendar (FR-20); reminders 7/2/1 days.
- [ ] 6.3 EVC report upload; deficiency → SHC; fraud flag to competent authority, no penal step (FR-22).
- [ ] 6.4 SHC scheduling, compliance record, recommendation (FR-24).
- [ ] 6.5 Executive Committee decision + Speaking Order upload (FR-26) → triggers appeal clock (3.5).
- [ ] 6.6 SAC/Council appeal flow and final decision (FR-27).
- [ ] 6.7 One-time reopening with Competent Authority approval, TER + penalty gate (FR-29).
- [ ] 6.8 Consolidated grant list + ratification (FR-31); publish letter + Approved Intake (FR-32).
- [ ] **Exit check:** one application travels submit → scrutiny → EVC → SHC → decision → appeal window → grant → deposit clock.

## Phase 7 — Dashboards and reports (§12) · build order #3
- [ ] 7.1 Role dashboards: Institution, Scrutiny, Regional, Regulation Bureau; every count drills down to applications.
- [ ] 7.2 Ageing bands, throughput, overdue/near-due, EVC status, compliance metrics.
- [ ] 7.3 Reports with PDF + CSV export (the seven in §12).
- [ ] 7.4 Region scoping verified by tests for each role.
- [ ] **Exit check:** dashboard counts equal drill-down lists (reuse existing reconcile test pattern).

## Phase 8 — Audit completeness · build order #5
- [ ] 8.1 Audit every PRD-listed event type, including document views.
- [ ] 8.2 Single-application timeline endpoint + `AuditTimeline.tsx`.
- [ ] 8.3 Export with hash-check; `scripts/tamper_demo.py` on a throwaway DB shows the check failing.
- [ ] **Exit check:** tamper test fails the chain; untouched chain passes.

## Phase 9 — Thin slices and admin · build order #6–7
- [ ] 9.1 Lease thin slice: end date read, advance + overdue alerts (FR-45).
- [ ] 9.2 Undertaking thin slice: Security Deposit proof/Affidavit 3 record with evidence upload, officer verification, reminders.
- [ ] 9.3 `fee_table.json` + `fee_engine.py`; additional-fee blocks for EVC/SHC/SAC (FR-21, FR-25) as P1 if time permits.
- [ ] 9.4 Admin console: edit route, deadline, fee, escalation, template with version history and four-eyes approval (FR-36, FR-50).
- [ ] 9.5 Change one deadline in the console → alert timing moves (demo step 10).

## Phase 10 — Hardening and handoff
- [ ] 10.1 Postgres run: `make up`, `make smoke`, `make verify-isolation` all pass with new tables (grants updated in `roles.sql`).
- [ ] 10.2 CI green; coverage not lower than baseline.
- [ ] 10.3 Update `docs/` (ARCHITECTURE, DATA_MODEL, RULES, ACCEPTANCE_TESTS, DEMO_SCRIPT, DEFERRALS) to match what exists.
- [ ] 10.4 Rehearse the five-minute demo script end to end on the Compose stack.
- [ ] 10.5 Update `CONTEXT.md` build order and README status table.

## Phase 11 — Evaluation, scenarios and release (AGENT-12)
- [ ] 11.1 Demo Scenario A — submission to correction: institution creates/submits, uploads synthetic PDF, officer inspects evidence, records finding, issues deficiency/return, institution responds with new version, revalidation runs, officer records supported outcome, audit timeline shown. **If a stage is missing, say so; do not fake it.**
- [ ] 11.2 Scenario B — access control: unauthenticated, unrelated institution, unassigned officer denied; authorised allowed.
- [ ] 11.3 Scenario C — processing failure: corrupt/unsupported file and OCR-unavailable → clear failure/`REVIEW_REQUIRED`, never a pass, no file contents in logs.
- [ ] 11.4 Scenario D — deadline/audit: synthetic dates, run sweep, rerun → no duplicates, audit events + verification result.
- [ ] 11.5 Measure and record (no invented numbers): extraction precision/recall on a labelled set, % findings with valid evidence, access-control pass rate, processing time per page, API latency; agree workload targets with the team first.
- [ ] 11.6 Fill the evaluation matrix (Workflow, Documents, Traceability, Security, Audit, UX, Reliability, Scope honesty) **with evidence only**; no scores without evidence.
- [ ] 11.7 Walk Appendix F of the PRD; every unchecked box is listed as a limitation.

## Test scenario catalogue (each test: ID, preconditions, synthetic data, actions, expected response/state/audit events, cleanup)
- **Submission:** valid draft submits; missing field fails; wrong institution denied; transition + audit recorded; duplicate submit has no duplicate effects.
- **Documents:** valid upload; unsupported/oversized/corrupt rejected; unauthenticated denied; unrelated institution denied; authorised officer allowed; replacement = new version; partial storage failure leaves no public file.
- **OCR:** text PDF extracts expected fields; scan uses OCR or reports unavailable; missing binary/provider never marks compliant; malformed output rejected; low confidence/conflict ⇒ review; results tied to version; reprocessing preserves history.
- **Rules/deficiencies:** required-doc presence; missing doc = candidate not rejection; contradictory dates ⇒ finding; missing master record ⇒ unknown; institution cannot edit officer fields; corrected upload triggers revalidation; closure stores reviewer/reason/time/rule version.
- **Workflow/security:** valid transition succeeds; invalid state/action fails with no partial writes; unauthorised role/scope denied; stale version rejected; concurrent updates safe; failed transaction leaves no inconsistent assignment/audit; unsupported route action rejected.
- **Assignment/deadlines:** eligible assignment; no eligible officer handled; unauthorised reassignment denied; date maths respects calendar/timezone; repeated sweep idempotent; delivery failure recorded and retryable; unverified deadline not activated.
- **Audit/reporting:** expected events visible; valid chain verifies; altered/missing/**reordered** record detected; unauthorised audit denied; dashboard counts match definitions; filters/pagination do not leak records.

## Agent task acceptance (summary; full text in the spec §33)
| Task | Acceptance |
|---|---|
| AGENT-01 | Findings cite files/symbols or confirmed absence; explicit status; gap matrix |
| AGENT-02 | Invalid actions leave no partial writes; valid transitions create history + audit; do not invent routes |
| AGENT-03 | Exact scope checks; immutable prior versions; tests: unauthenticated, wrong institution, unassigned officer, authorised user, unsupported/oversized file |
| AGENT-04 | Version-specific outputs; schema validation; timeouts; failure states; no fabricated values; tests: text/scan/corrupt/missing binary/timeout/malformed output |
| AGENT-05 | Active rules have source/version/tests; unknown ⇒ review-required; tests: positive, negative, boundary, missing/contradictory, old rule version |
| AGENT-06 | Institution cannot edit officer fields; responses and reasons preserved; tests: unauthorised response, replacement, revalidation |
| AGENT-07 | Eligible selection documented; no-eligible safe; changes audited; tests: inactive/wrong-jurisdiction/none/conflict/duplicate; **do not invent COI policy** |
| AGENT-08 | Policy version recorded; repeated sweeps don't duplicate; failures visible/retryable; tests: boundaries, calendar, duplicate sweep, delivery failure, policy change |
| AGENT-09 | Definitions documented; filters/permissions correct; no hard-coded live numbers |
| AGENT-10 | Sensitive events covered; tampering detected; endpoint protected; do not claim absolute immutability |
| AGENT-11 | Loading/error/empty/stale states; server enforces actions; test build, roles, failures, focus refresh; no fake persistence |
| AGENT-12 | Reproducible synthetic lifecycle; setup, expected states, limitations documented; do not fake unsupported stages |

## Deferred (do not build now)
MFA, SMS provider, live portal/payment/DSC integrations, SSO, Hindi labels, post-approval EVC tracking (FR-23), withdrawal/revocation (FR-30), enrolment reminders (FR-34), University-views window (FR-35), session-recording refs (FR-16), case-summary drafting (FR-17), historical replay, Rehearsal Load Factor; official-portal integration claims; production processing of real institutional records (needs security/privacy approval); any unverified regulatory rule as a gating rule.
