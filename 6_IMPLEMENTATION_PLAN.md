# Implementation Plan

Rules for the agent: do **one unchecked task at a time, top to bottom**. Each task ends with `make lint && make test` (and `npm run build` for UI) green and the box ticked. Don't start a phase until the previous phase's **Exit check** passes. FR numbers refer to `1_PRD.md`.

**Baseline (already built, do not redo):** rule engine + versioning, workflow guards, audit hash chain, rehearsal engine + Postgres isolation, upload + OCR + evidence verify, undertakings, deadline scheduler, officer monitoring, auth hardening, review UI, Docker/prod/CI.
**Before Phase 0 ends, confirm by reading code** what `workflow_routes.json` and `deadline_policy.json` already contain, so you extend rather than duplicate.

---
## Phase 0 — Align and baseline
- [ ] 0.1 Run `make setup`, `make test`, `make lint`; record counts (expect 159 tests).
- [ ] 0.2 Fix README test count (155 → actual) and note Python 3.13 / Node 26 as the verified versions.
- [ ] 0.3 Copy the six docs into `docs/prd/` and `AGENTS.md`/`CLAUDE.md` into repo root.
- [ ] 0.4 Inventory current `workflow_routes.json`, `deadline_policy.json`, `compliance_rules.json` into `docs/prd/GAP_NOTES.md` (what exists vs PRD).
- [ ] **Exit check:** green suite, gap notes written.

## Phase 1 — Routing engine and Table 2.3 scoreboard (FR-07–FR-11) · build order #1
- [ ] 1.1 Encode all 21 Table 2.3 rows in `workflow_routes.json` (category id, route, window, EVC-not-applicable flag for FN/OCI/Gulf).
- [ ] 1.2 `services/routing.py`: category → ordered stage list; support SD, SCR, SCR+EVC, SCR+EVC+AA.
- [ ] 1.3 `test_routing_table_2_3.py`: one parametrised test per row (21 passing).
- [ ] 1.4 Combined applications: `ApplicationItem` model + migration; union of stages; per-category outcome (FR-08).
- [ ] 1.5 Sequencing: Women's conversion before merger (2.13.1m).
- [ ] 1.6 Random EVC add for SD (2.3.5) and second EVC after site shift (2.17e) as authorised actions.
- [ ] 1.7 "AA" gate: SHC/SAC opens only on deficiency or negative outcome (FR-10).
- [ ] 1.8 Fallback-to-EoA branch after "not approved" (FR-11).
- [ ] 1.9 `GET` route-scoreboard endpoint + `RouteScoreboard.tsx`.
- [ ] **Exit check:** scoreboard shows 21/21; audit events written for every routing decision.

## Phase 2 — Readiness and intake (FR-01–FR-05)
- [ ] 2.1 `calendars.json` + `working_calendar.py` (IST, holidays, Public Notice dates, Academic Calendar) (FR-37).
- [ ] 2.2 `readiness.py`: cut-off check → tag next AY, never reject (FR-02).
- [ ] 2.3 Blocked-application flags: five rules from FR-03, officer can clear or hold.
- [ ] 2.4 Lease-years computation and flag (FR-05, RULE-LEASE-01), reusing the grounded lease extractor.
- [ ] 2.5 Stubbed portal feed endpoint carrying the FR-01 fields, with "as of" timestamp.
- [ ] **Exit check:** late application lands in next-AY queue; blocked flags visible to Regional officer.

## Phase 3 — Stage graph, clocks, escalation, demo clock · build order #2 (FR-09, FR-27, FR-33, §11)
- [ ] 3.1 `StageInstance` model + migration; `stages.py` auto-advance on authorised completion (FR-09).
- [ ] 3.2 Return/revert with reason code + free text (FR-28); audit.
- [ ] 3.3 `stage_limits.json` with **placeholder** day counts, clearly labelled; per-stage due dates.
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

## Deferred (do not build now)
MFA, SMS provider, live portal/payment/DSC integrations, SSO, Hindi labels, post-approval EVC tracking (FR-23), withdrawal/revocation (FR-30), enrolment reminders (FR-34), University-views window (FR-35), session-recording refs (FR-16), case-summary drafting (FR-17), historical replay, Rehearsal Load Factor.
