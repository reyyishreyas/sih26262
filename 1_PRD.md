# PRD: AICTE EoA Verification Workflow & Automation (PS 26262)

**Status:** Prototype in progress · **Repo:** reyyishreyas/sih26262 · **Source:** APH 2024-27, Chapter II
**Rule for readers (human or AI):** this file says *what* and *why*. It contains no code. How it is built is in `2_ARCHITECTURE.md`.

---

## 1. Product in one paragraph
A platform that routes, verifies and monitors Extension of Approval (EoA) applications from existing institutions. It sends each application to the correct stages, tracks every deadline, escalates when clocks are missed, reads uploaded documents and flags inconsistencies, and records everything in a tamper-evident audit trail. **People decide; the system routes, reminds, extracts and flags.**

## 2. Problem
- Routes per category (Table 2.3) are applied by hand, so applications go to the wrong stage or stall.
- Pendency, EVC scheduling and appeal clocks (e.g. 7 days to appeal) are watched manually, so deadlines slip.
- Deficiency, return and reopening reasons are scattered.
- Officers and institutions have no shared view of status, so they chase by phone and email.

## 3. Goals
1. Route every application automatically and advance it when a stage completes.
2. Real-time status, ageing and workload by Region, stage, institution, officer.
3. Alert and escalate before and after every deadline; no missed clock.
4. Record every action, reason and decision in an audit trail traceable end to end.
5. Keep human authorities in control of every verification and decision.

**Non-goals:** auto-approve or auto-reject anything; replace committee judgement, inspection or the Speaking Order; build the AICTE portal, payment gateway or application forms (we integrate with or stub them).

## 4. Scope
**In scope (Module 1):** intake and readiness checks (cut-off, TER paid, eligibility blocks); routing by category (Tables 2.2, 2.3); stages: Scrutiny / Re-Scrutiny, EVC, SHC, Executive Committee, appeal to SAC, grant; deficiency, return/revert, one-time reopening, withdrawal, fallback-to-EoA; pendency monitoring, alerts, escalation, dashboards, reports; Security Deposit proof clock (15 days) and penalty dates; document intelligence (OCR + AI pre-check); audit trail.

**Out of scope:** Chapter I and Chapters III onward; any decision or inspection outcome; portal, gateway, forms; full undertaking tracker and lease monitor (Phase 2 — only thin slices in the prototype).

**Lease rule carried here (cl. 2.1e):** EoA stops once the live lease equals the longest course duration unless extended by 30 years. Compute and flag remaining years during verification.

## 5. Users and roles
Access is role-based and Region-scoped. No role can edit a committee finding once recorded; corrections are new logged entries. Committee members cannot see applications where they declare a conflict. Institutions see only their own data. Every view of a sensitive document is logged.

| Role | Main tasks | Decides? |
|---|---|---|
| Institution (Director/Principal/signatory) | Track, upload compliance, receive alerts, view orders, file appeal | No |
| Scrutiny / Re-Scrutiny member | Verify against checklist, record deficiencies | Recommendation |
| EVC expert | Accept visit, upload report, findings | Recommendation |
| SHC | Review compliance, recommend | Recommendation |
| Executive Committee | Decide, upload Speaking Order | Decision |
| SAC / Council | Hear appeal, final decision | Final |
| Regional officer | Monitor Region, assign/reassign, first escalation | Workflow only |
| Regulation Bureau officer | All Regions, consolidated grant list, second escalation | Workflow only |
| Policy & Academic Planning Bureau | Unapproved-institution representations (cl. 2.26e) | Per APH |
| System administrator | Configure rules, calendars, templates, users | No |
| Auditor (read-only) | View audit trail and reports | No |

## 6. Application categories and routing
Four routes, held as **configuration, not code**:
- **SD** — Self-Disclosure only: system generates Nil Deficiency report; no scrutiny.
- **SCR** — Scrutiny / Re-Scrutiny only.
- **SCR+EVC** — Scrutiny then EVC.
- **SCR+EVC+AA** — Scrutiny, EVC, then SAC/SHC only if earlier outcome has deficiencies ("AA" = as applicable).

### Table 2.3 (21 rows) — routing test source of truth
| # | Category | Route | Window |
|---|---|---|---|
| 1 | EoA based on Self-Disclosure | SD | Public Notice |
| 2 | Introduction / Continuation of NRI seats | SD | Public Notice |
| 3 | Conversion Diploma↔Degree | SCR+EVC+AA | Public Notice |
| 4 | Change in Name of Institution / affiliating University or Board / Type (not converted into University) | SCR | Public Notice |
| 5 | Start new Programme / Level | SCR+EVC+AA | Public Notice |
| 6 | Merger of Institutions | SCR+EVC+AA | Public Notice |
| 7 | EoA after break / Restoration of Intake / Hibernation | SCR+EVC+AA | Public Notice |
| 8 | Seats for Foreign Nationals, OCI, Children of Indian Workers in Gulf | SCR (EVC n/a) | Public Notice |
| 9 | Increase in Intake / Additional Course(s) | SCR+EVC+AA | Public Notice |
| 10 | Integrated / Dual Degree Course | SCR+EVC+AA | Public Notice |
| 11 | Fellow Programme in Management | SCR+EVC+AA | Public Notice |
| 12 | Change in Name of Course / Merger of Courses / Reduction in Intake | SCR | Public Notice |
| 13 | Collaboration and Twinning Programme | SCR+EVC+AA | Public Notice |
| 14 | Change of Site / Location | SCR+EVC+AA | Year round |
| 15 | Closure of the Institution | SCR | Year round |
| 16 | Women's Institution ↔ Co-ed | SCR | Year round |
| 17 | Closure of Programme(s) / Course(s) | SCR | Year round |
| 18 | Change in Bank Details | SCR | Year round |
| 19 | Change in Name of Trust / Society / Company | SCR | Year round |
| 20 | Type converted into Deemed-to-be-University | SCR+EVC+AA | Year round |
| 21 | Online Learning / ODL | SCR+EVC+AA | Year round (processed twice a year per UGC timeline) |

### Routing rules
1. **Random EVC (2.3.5):** an authorised user can pull an SD application into the EVC queue.
2. **Combined applications:** route = union of needed stages; outcome recorded per category.
3. **Fallback to EoA (2.7l, 2.14j, 2.15e):** after "not approved" for new programme / level conversion / Women's-to-Co-ed, issue EoA for the existing institution if requirements are met; the engine opens this branch automatically.
4. **Women's merger (2.13.1m):** Women's-to-Co-ed conversion first, merger after it clears.
5. **Change of Site (2.17e):** a second EVC may be needed after movable property is shifted.
6. **Increase in intake (2.6):** EVC must confirm infrastructure and faculty.
7. **Cut-off:** applications after the Public Notice cut-off are queued for the next Academic Year.

**Gaps to confirm with AICTE:** Off-Campus (cl. 2.11e) and Extended EoA appear in text/Table 2.2 but have no Table 2.3 row.

## 7. End-to-end workflow
Submitted → Readiness checks → Route decision → (SD: Nil Deficiency report) or Scrutiny/Re-Scrutiny ⇄ Compliance cycle → EVC (if route needs it, or random) → SHC (only if deficiencies remain) → Executive Committee decision + Speaking Order → Appeal (once, 7 days, SAC, Council) → Grant (list, letter, Security Deposit clock). Return/revert and withdrawal at any stage with a recorded reason.

| Stage | Owner | Starts when | Completes when |
|---|---|---|---|
| Readiness checks | System; Regional officer clears flags | Final submission + TER received | All pass, or official clears/holds each flag |
| Routing | System | Readiness done | Route and stage list recorded per category |
| Scrutiny / Re-Scrutiny | Scrutiny committee | Assigned | Nil Deficiency recorded, or deficiency report issued |
| Compliance cycle | Institution, then scrutiny | Deficiency issued | Institution replies and Re-Scrutiny result recorded |
| EVC | EVC coordinator + experts | Scrutiny done and route needs EVC, or random add | Visit held, report uploaded |
| Hearing (SHC) | SHC | Deficiency remains | Compliance heard, recommendation recorded |
| Executive Committee decision | Executive Committee | Recommendation / Nil list ready | Decision + Speaking Order uploaded |
| Appeal | Institution, SAC, Council | Decision uploaded; 7-day window opens | Window lapses or Council final decision |
| Grant | Regulation Bureau, EC/Council | Decisions final | List ratified, letter published, deposit clock starts |

## 8. Document intelligence and AI pre-check
The AI layer extracts and flags. **It never approves, rejects or returns an application.**

1. **Ingest** PDF / scan / DOCX; classify (EoA letter = master record, Format-2 NOC, Format-3 Resolution, lease, affidavit, other Annexure-2 item).
2. **Extract (hybrid OCR):** PDF text layer first, then Tesseract with per-word confidence and bounding boxes. Fields below threshold (default 0.75, configurable) go to an optional vision-model fallback returning structured JSON.
3. **Ground:** a model value counts only if its text is found on the page (fuzzy match to OCR words); else `REVIEW_REQUIRED`.
4. **Compare:** rule engine checks extracted values against AICTE's record and the APH clause.
5. **Classify:** PRE-CHECK PASSED / REVIEW REQUIRED / DEFICIENCY CANDIDATE. None blocks or rejects.
6. **Present:** officer opens a split-screen review with evidence highlighted on the original.

**Three-value model** (every field keeps all three): *Extraction Value* (what the document says), *Claim Value* (what the institution confirms/edits), *Master Record Value* (AICTE's record). Rules run on the Extraction Value only; an edit is flagged, both values kept, a reason required, and an edit can never clear a failed rule. Wording stays neutral ("edited after extraction").

**Rule registry** (ID, clause, severity, on/off, version; admin-maintained; clause text comes from the registry, never a model):
| Rule | Check | Clause | If fails |
|---|---|---|---|
| RULE-DOC-01 | Required docs present, DSC-signed; Affidavit 2 present | 2.3.4a,b | Deficiency candidate |
| RULE-E01 | Trust/Society/Company name on NOC = EoA | Annexure-2 (confirm) | Deficiency candidate |
| RULE-E02 | Old address + survey no. on NOC = current EoA address | Annexure-2 (confirm) | Deficiency candidate |
| RULE-E03 | Institution name, PID, type agree across docs | Annexure-2 | Deficiency candidate |
| RULE-SITE-01 | Format-3 Resolution covers all approved programmes; no partial shifting (keyword/phrase list + programme-list comparison) | 2.17i | Deficiency candidate |
| RULE-SITE-02 | New address inside current affiliating University's jurisdiction (not for PGDM) | 2.17b | Deficiency candidate |
| RULE-LEASE-01 | Remaining lease years > longest course duration, or 30-yr extension on file | 2.1e | Deficiency candidate |
| RULE-OCR-01 | Field below confidence threshold or fallback value not found on page | none | Review required |
| RULE-EDIT-01 | Claim Value ≠ Extraction Value | none | Review required |

**Gate:** Scrutiny cannot be marked complete until the officer records a disposition (Confirmed / Dismissed with reason / Clarification requested) for every amber and red finding. Every officer action on a finding is audited.

**Split-screen reviewer:** form left (edit badges, original value one click away); original document right (highlight box from stored bounding box; if no box found, say so); findings report below (rule ID, clause, values compared, page, snippet, officer buttons).

**Data kept per extracted field:** value, page, bounding box, confidence, engine + version, grounding result, Claim Value, edit reason, officer disposition, plus document hash.

**Risks:** poor scans lower confidence and must never create a false pass; keyword checks miss paraphrases; external model calls send page images off-system (switch to turn off, only low-confidence pages, every call logged); model drift (temperature 0, JSON-schema output, version stored); University jurisdiction table must be supplied by AICTE.

## 9. Functional requirements
P0 = prototype and first release. P1 = next release.

**A. Intake and readiness**
| ID | Requirement | APH | P |
|---|---|---|---|
| FR-01 | Receive each final-submitted application with ID, PID, category, institution type, submission time, TER status, documents | 2.3.1 | P0 |
| FR-02 | Reject from processing and tag for next AY any application submitted/paid after cut-off | 2.2, 2.22 | P0 |
| FR-03 | Flag blocked applications: Closure applicants applying for other categories; no EoA for 6 years; standalone PGDM/PGCM without full student data; intake increase during Central/State inquiry; partial approval of programmes | 2.21f, 2.16.1a, 2.3.1, 2.6e, 2.27 | P0 |
| FR-04 | Record which of six 3-year EoA criteria are claimed; checklist for verifier | 2.1a | P1 |
| FR-05 | Compute remaining lease years vs longest course duration; flag | 2.1e | P0 |

**B. Routing**
| FR-07 | Assign route from category via configurable table | T2.3 | P0 |
| FR-08 | Combined applications, per-category outcomes, sequencing rules | 2.13.1m | P0 |
| FR-09 | Auto-advance when authorised user marks stage complete | PS A | P0 |
| FR-10 | Open SAC/SHC only on deficiency or negative outcome | T2.3 | P0 |
| FR-11 | After "not approved", open fallback EoA branch | 2.7l, 2.14j, 2.15e | P0 |

**C. Scrutiny / Re-Scrutiny**
| FR-06 | Confirm Affidavit 2 and DSC-signed docs; list missing items as deficiency draft | 2.3.4 | P0 |
| FR-12 | Assign to committee/member by Region and workload, with conflict-of-interest declaration | 1.8 | P0 |
| FR-13 | Generate checklist from category's Annexure-2 list beside uploaded docs | Annex-2 | P0 |
| FR-14 | Result per checklist item and overall (Nil Deficiency / Deficiency) with remarks | 2.4 | P0 |
| FR-15 | Deficiency report, compliance window, compliance upload to Re-Scrutiny | 2.3.3b, 2.4 | P0 |
| FR-16 | Store reference of scrutiny session recording | 2.28 | P1 |
| FR-17 | Pre-fill case summary and draft communications (drafts only) | PS A | P1 |

**D. EVC**
| FR-18 | Queue for EVC after scrutiny when route needs it | 2.23.2 | P0 |
| FR-19 | Authorised user adds random EVC; schedule second EVC after site shift | 2.3.5, 2.17e | P0 |
| FR-20 | Schedule EVC online/physical, assign experts, confirmation, Region calendar | 1.9 | P0 |
| FR-21 | Block additional EVC until additional TER paid (Rs 1.25 lakh online, 2.50 physical; Govt 0.25/0.50) | 2.3.2c | P1 |
| FR-22 | Collect EVC report; route deficiency to SHC; flag fraudulent-document findings for competent authority | 2.3.5b | P0 |
| FR-23 | Track EVCs required after approval | 2.6j | P1 |

**E. Hearing, decision, appeal**
| FR-24 | Schedule SHC, record compliance, place recommendation before Executive Committee | 2.23.3 | P0 |
| FR-25 | Block additional Scrutiny/SHC/SAC until fee paid (Rs 0.60 lakh; Govt 0.15) | 2.3.2b | P1 |
| FR-26 | Record Executive Committee decision and Speaking Order | 2.23.3, 2.25c | P0 |
| FR-27 | 7-day appeal clock from decision upload; one appeal only; schedule SAC; record Council final decision | 2.24 | P0 |

**F. Return, reopening, withdrawal**
| FR-28 | Return/revert to prior stage or institution; reason code + free text mandatory | PS A | P0 |
| FR-29 | One-time reopening with Competent Authority approval; TER + late penalty before resuming | 2.3.3e | P0 |
| FR-30 | Withdrawal/revocation: within 7 days of last date (refund minus Rs 0.25 lakh); closure revocation by 10 April | 2.3.3d,f,g | P1 |

**G. Grant and post-grant**
| FR-31 | Consolidated list of institutions with Approved Intake; record ratification | 2.25a | P0 |
| FR-32 | Publish EoA letter and Approved Intake to institution login; none after Academic Calendar last date | 2.25b,j | P0 |
| FR-33 | Security Deposit: 15-day clock for proof + Affidavit 3; 10% penalty to 31 May, 20% to 31 July; flag withdrawal after | 2.25d-f | P0 |
| FR-34 | Remind student enrolment upload before 30 Nov | 2.25n | P1 |
| FR-35 | Track 15-day University/Board views window; proceed if none arrives | 2.19c | P1 |

**H. Configuration**
| FR-36 | Admin console: routes, owners, timelines, fees, calendars, templates, escalation chains, version history | PS | P0 |
| FR-37 | Load yearly Public Notice dates and Academic Calendar; apply to all clocks | 2.2, 2.25 | P0 |

**I. Document intelligence**
| FR-38 | Accept PDF/scan/DOCX; classify | 2.3.4 | P0 |
| FR-39 | Extract with Tesseract (conf + boxes); low-confidence re-read by vision model (model, threshold configurable) | §8 | P0 |
| FR-40 | Accept model value only if found on page, else REVIEW_REQUIRED | §8 | P0 |
| FR-41 | Keep Extraction/Claim/Master values; edits flagged with reason | §8 | P0 |
| FR-42 | Cross-check Format-2 NOC vs EoA (names, address, survey no., PID, type) on Extraction Value | Annex-2 | P0 |
| FR-43 | Check new site within affiliating University jurisdiction (not PGDM) | 2.17b | P0 |
| FR-44 | Raise finding if Resolution names only some programmes / partial shifting | 2.17i | P0 |
| FR-45 | Read lease end date, compute years, finding if equal or shorter; store end date for expiry alerts | 2.1e | P0 |
| FR-46 | Assign PASSED / REVIEW REQUIRED / DEFICIENCY CANDIDATE; none rejects or blocks | PS | P0 |
| FR-47 | Scrutiny cannot complete until every amber/red finding has a disposition | 2.4 | P0 |
| FR-48 | Split-screen review with highlight box and findings report | §8 | P0 |
| FR-49 | Warn institution of findings before final submission | 2.3.3 | P1 |
| FR-50 | Rule registry editable by admins, change logged | PS | P1 |
| FR-51 | Switch to turn external model fallback off; log each external call | PS | P1 |

## 10. Business rules (all configuration with effective date)
| Rule | Value | APH |
|---|---|---|
| Appeal to Council | Once, within 7 days of decision upload | 2.24a |
| Revocation of submitted application (non-EoA) | Within 7 days of last date; refund minus Rs 0.25 lakh | 2.3.3f |
| Withdrawal of pending Closure | On/before 10 April | 2.3.3g |
| Reopening | One time, Competent Authority approval, TER + late penalty | 2.3.3e |
| Security Deposit proof + Affidavit 3 | 15 days; 10% penalty to 31 May; 20% to 31 July; withdrawn after | 2.25f |
| University/Board views on name/type change | 15 days of last submission date | 2.19c |
| Student enrolment upload | Before 30 November | 2.25n |
| Restoration after punitive action | Next AY and within 6 years | 2.16.2a |
| Break in EoA | 6 consecutive years without application → apply as new institution | 2.16.1a |
| Hibernation period | One year less than longest course duration | 2.16.1d |

**Unstated timelines:** APH gives no day counts for Scrutiny, EVC scheduling, SHC, Executive Committee. These are configurable; the prototype uses clearly labelled placeholders until AICTE supplies them.

**TER (Table 2.1, Rs lakh).** Charges rise 10% per year; not refunded if processed and rejected. Bank-details change Rs 0.06; closure of institution nil.
| Head | Govt/Central/State Univ | All other |
|---|---|---|
| SD per Division (non-PGDM/MBA) | 0.05 | 0.20 |
| SD per Division (PGDM/MBA) | 0.15 | 0.40 |
| SD vocational | Nil | Nil |
| Late submission penalty | 0.25 | 2.50 |
| Break in EoA / Restoration of Intake | 0.50 | 2.50 |
| Introduce OCI/FN/Gulf/Off-Campus | 0.50 | 6.00 |
| Continue OCI/FN/Gulf per Course | 0.05 | 0.30 |
| Fellow Programme in Management | 0.50 | 1.25 |
| Group A: site change; Diploma→Degree; new Programme/Level; Trust name; Merger | 0.25 | 3.50 |
| Group B: Degree→Diploma; Women's↔Co-ed; NRI seats; intake increase/additional course; Integrated/Dual | 0.15 | 1.25 |
| Group C: course name/merger; intake reduction; closure of programme; institution/University name; type→University; Trust address | 0.10 | 0.60 |
| Additional Scrutiny/SHC/SAC | 0.15 | 0.60 |
| Additional EVC online | 0.25 | 1.25 |
| Additional EVC physical | 0.50 | 2.50 |

Refund: rejection at Scrutiny without appeal for Site/Conversion/New Programme/Merger refunds charge minus Rs 0.60 lakh (2.3.2e). No TER for PG degree other than MCA/Management, for hibernation, or where State changes University jurisdiction. **Verify the Group A/B/C column mapping against the official page (it came from a rotated image).**

## 11. Alerts, reminders, escalation
Every open task has an owner and due date. Escalation chain (default, editable): L0 assignee → L1 Regional officer → L2 Regulation Bureau → L3 competent authority.

| Trigger | Notified | Timing | Escalates to |
|---|---|---|---|
| Near stage limit | Owner | 70% and 90% | L1 at 100%, L2 at 125% |
| Over stage limit | Owner + Regional | Daily | L2, then L3 |
| Unassigned in queue | Regional | After 1 working day | L2 after 3 days |
| Deficiency issued | Institution | On issue, 7d, 2d, due date | Regional on miss |
| Compliance uploaded | Scrutiny owner | On upload; daily | L1 after 3 days |
| EVC to schedule | EVC coordinator | On entry; weekly | L1, then L2 |
| EVC scheduled | Institution, experts | On schedule; 7d, 2d, 1d | L1 if expert absent |
| EVC report missing | Expert | 2 days after; daily | L1, then L2 |
| Additional TER pending | Institution | On request; every 3 days | L1 after 10 days |
| SHC/SAC hearing | Institution, committee | 7d, 2d, 1d | L1 if absent |
| Speaking Order uploaded | Institution | Day 3 and day 6 of 7 | none; window closes day 7 |
| Security Deposit due | Institution | Day 1, 10, 14; 31 May, 31 July | Bureau |
| Enrolment due | Institution | 30d, 7d before 30 Nov | Regional after |
| Reopening/withdrawal request | Competent Authority | On request; every 2 days | L3 |

Channels: in-app, email, SMS (institutions); in-app, email (officers). Working-day calendar from config. Alerts stop when task closes; every alert, acknowledgement and escalation is logged. One snooze with a reason, no second.

## 12. Dashboards, reports, audit
Each role lands on a dashboard for its next action; every number drills down to applications.
- **Metrics:** status counts; ageing bands (0-7, 8-15, 16-30, 30+); throughput per stage per week; overdue/near-due by stage/Region/officer; EVC queued/scheduled/completed/delayed (online vs physical); compliance issued/closed/overdue; rejections and returns by reason code.
- **Reports (PDF + spreadsheet):** pendency; EVC status; deficiency & compliance; appeal & hearing; Security Deposit status; overdue & escalation; Region-wise performance per AY.
- **Audit trail:** append-only; stores what/who/when, application/stage, before/after, reason, document hashes, session recording refs, **chained hash**; full per-application timeline; export with hash check.

## 13. Non-functional requirements
Security (RBAC, Region scope, encryption, MFA for officers, document-view logging) · Confidentiality (conflict-of-interest blocking) · Deadline accuracy (single server time in IST, working-day calendar, nightly clock recompute) · Availability 99.5% in cycle · Performance (dashboards <3 s, alerts out within 5 min) · Auditability (append-only, retained as long as approval record) · Usability (desktop + mobile, English first, room for Hindi) · Storage (versioned object storage, virus scan on upload) · **Configurability: no routing, fee or timeline value hard-coded.**

## 14. Safeguards (non-negotiable)
- Works inside AICTE Regulations and the APH; supports but never replaces scrutiny, verification, inspection or competent-authority decision.
- No stage completes, and nothing is approved/rejected/returned, without a named authorised user.
- Auto-generated text is a **draft** a user must review and issue.
- Fraud findings are flagged to the competent authority; the system takes no penal step.
- Rules change only by administrators with a logged, dated version.

## 15. Success measures
| Measure | Target |
|---|---|
| Routing accuracy vs Table 2.3 | 100% (one test per row) |
| Alerts sent within 5 min | 99% |
| Clocks matching manual recomputation | 100% |
| Open applications with owner + due date | 100% |
| Manual follow-up | Down at least 50% in one cycle |
| Stage changes with actor + reason | 100% |
| Missed appeal/deposit deadlines from no reminder | Zero |

## 16. Prototype scope (synthetic data only)
1. Automatic routing for ≥4 categories (SD, SCR, Increase in Intake, Change of Site); Change of Site built in full with public EoA letter as master record + synthetic Format-2 NOC and Format-3 Resolution (labelled synthetic).
2. Role dashboards: Institution, Scrutiny, Regional, Regulation Bureau.
3. Scrutiny with checklist, split-screen review, dispositions, deficiency, compliance, Re-Scrutiny.
4. EVC queue, scheduling, reminders.
5. SHC + Executive Committee decision, Speaking Order, 7-day appeal clock, SAC.
6. Return/revert, one-time reopening, fallback to EoA.
7. Security Deposit 15-day clock with penalty dates.
8. Overdue escalation up the chain.
9. Full audit trail of one application with hash check.
10. Thin slices: one undertaking record; one lease with advance + overdue alerts.

**Demo extras:** a **demo clock** that advances time to show reminders and escalation; a **Table 2.3 test scoreboard**; a **tamper test** that breaks the hash chain; admin change of one deadline visibly moves alerts.

**Five-minute demo:** Regional dashboard → upload Change of Site pack (OCR auto-fill) → institution edits a field (amber badge) → rules fire (address mismatch, "partial shifting") → officer split-screen confirm/dismiss → EVC queue + second EVC → demo clock escalation → decision, appeal and deposit clocks → audit timeline + tamper test → admin changes a deadline.

**Demo data rules:** public AICTE EoA letter only as master record (may be older format); label every synthetic NOC/Resolution; keep external model fallback off for anything non-public/non-synthetic.

## 17. Phases
Prototype (sample data, stubbed portal feed) → Release 1 (live portal integration, all P0, role-based access, reports) → Release 2 (P1, extended channels, post-approval EVC) → Phase 2 (undertakings, lease/document validity monitor).

## 18. Risks
| Risk | Mitigation |
|---|---|
| APH rules change mid-cycle | Dated configuration, admin console, per-category regression tests |
| Portal data not real-time | Scheduled sync with "as of" time on every screen |
| Alert fatigue | Digest option, snooze once with reason, escalate only past due |
| Wrong fee/deadline configured | Four-eyes approval for rule changes; preview before publish |
| Over-reliance on automation | Mandatory human sign-off; drafts labelled |

## 19. Open questions for AICTE
1. Target days for Scrutiny, Re-Scrutiny, EVC scheduling, SHC, Executive Committee?
2. How is Off-Campus routed (cl. 2.11e; no Table 2.3 row)?
3. Does Extended EoA follow SCR, and what documents?
4. Which roles may add a random EVC and approve reopening?
5. Who is the designated authority at each escalation level, by Region?
6. Can the portal expose APIs, or only exports?
7. Confirm Table 2.1 change-and-addition column mapping.
8. Which APH sections beyond Chapter II and Annexure-2 lists load into the checklist engine first?
9. Can the system read the EoA letter and University as structured data? Are Format-2/3 templates available? Is any external model service allowed? Who maintains the University jurisdiction table?

## 20. Repo-specific addendum: Approval Crash-Test
The repo adds one capability beyond the source PRD: the **Approval Rehearsal (Crash-Test) Engine**. Before a real action, an officer can rehearse hypothetical evidence changes against the same immutable rule versions and see a finding-level diff, with the production application never written to (`production_modified: false`). This is retained as a differentiator and must not weaken any safeguard in §14.
