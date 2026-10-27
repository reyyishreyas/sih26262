# docs/BUG_LOG.md

**Purpose:** every error, bug, failed test, failed command, regression, environment problem or surprising behaviour hit while working on this repo, **with the solution that was actually applied** (or the status if unsolved). Decisions and normal implementation go in `docs/IMPLEMENTATION_LOG.md`; link the two by ID.

## Rules
1. **Log it when it happens**, not at the end. Open the entry as soon as you hit the problem; fill in the fix when you have it. If you end a session with it unsolved, leave it `Open` with what you tried.
2. **Append-only.** Newest first. Don't delete entries or rewrite history. If a "fix" turns out to be wrong, change `Status` to `Reopened` in a new "Update" line inside the entry, and describe the new attempt; keep the old attempt.
3. **Include the real error text** (trimmed to the relevant lines) and the exact command. **Never paste secrets, tokens, connection strings, real personal data or document contents**; redact them.
4. **Record failed attempts too.** They stop the next agent repeating them.
5. **Root cause before "fixed".** `Fixed` requires a root cause statement and a test or command that now passes; otherwise use `Workaround` or `Open`.
6. **Add a regression test** for every fixed bug (repo rule: every fixed bug gets a test) and name it in the entry.
7. Severity: `S1` data loss / security / wrong regulatory outcome / audit integrity · `S2` feature broken, no workaround · `S3` feature degraded, workaround exists · `S4` cosmetic / docs.
8. Status: `Open` · `Investigating` · `Workaround` · `Fixed` · `Reopened` · `Won't fix` (needs a human to approve) · `Not reproducible`.
9. Anything that could affect safety rules (audit tampering, authz bypass, a model changing state, secret leak) is `S1` and must be reported to a human immediately in your response, not just logged.

## Index (one line per entry)
| ID | Date | Sev | Area | Title | Status | Linked IMPL |
|---|---|---|---|---|---|---|
| BUG-0017 | 2026-10-27 | S4 | test | Exit check's audit-order helper read rows in `entity_id` index order (no `ORDER BY`) — chronology faked, ordering walk failed; now ordered by `AuditEvent.seq` | Fixed | IMPL-0037 |
| BUG-0016 | 2026-10-27 | S4 | compliance window / test | Exit check read `open` instead of `received` after resubmit: `_resubmitted_at`'s strict `>` vs return+resubmit at the identical fixed-clock instant — test now advances the audited demo clock between the steps (service correct) | Fixed | IMPL-0037 |
| BUG-0015 | 2026-10-27 | S4 | test | First run of the RULE-DOC-01 suite: expected candidate set omitted `affidavit_2` on a case that uploads no affidavit — the service was right, the expectation incomplete | Fixed | IMPL-0036 |
| BUG-0014 | 2026-10-27 | S3 | workflow config | `existing_technical` route defines no `return_for_clarification`/`resubmit` transitions — the FR-15 deficiency→compliance loop is unreachable on that route; route-table change needs human approval | Open | IMPL-0035 |
| BUG-0013 | 2026-10-27 | S4 | test | Third run of the FR-15 suite: `select().count()` misuse (AttributeError), 23:59 asserted on a UTC timestamp (it is 23:59 in the business timezone), re-return attempted from `submitted` without `start_scrutiny` | Fixed | IMPL-0035 |
| BUG-0012 | 2026-10-27 | S4 | test | First run of the FR-15 suite: 11 failures — wrong seeded route (`existing_technical` has no return leg → BUG-0014) and a missing mandatory FR-28 reason code on the return | Fixed | IMPL-0035 |
| BUG-0011 | 2026-10-27 | S4 | migration | `alembic check` red on the new scrutiny tables: model said `unique=True` on the column, migration created a named constraint — two DDL forms for one rule | Fixed | IMPL-0034 |
| BUG-0010 | 2026-10-27 | S4 | test | New scrutiny-result tests wrote invented user ids (`user-a`, `user-scrutiny`) into the real `recorded_by` FK — 12 × IntegrityError | Fixed | IMPL-0034 |
| BUG-0009 | 2026-10-27 | S4 | test | New Phase 3 exit-check test failed `make lint` on first run (F401: unused `timedelta` import left from drafting; also a stray mid-file `import pytest` and hard-coded guessed user ids `user-regional`/`user-supervisory` that do not exist — seeded ids are auto-generated) | Fixed | IMPL-0032 |
| BUG-0008 | 2026-10-27 | S4 | test | New routing test expected `POST /applications` → 200; route returns 201 Created | Fixed | IMPL-0025 |
| BUG-0007 | 2026-10-26 | S4 | test | Routing test assumed every PRD §6 pattern is used by a Table 2.3 row; no row is plain SCR+EVC | Fixed | IMPL-0008 |
| BUG-0006 | 2026-10-26 | S2 | migration | `alembic check` red: `deficiencies` and `evc_visits` tables added to the ORM with no migration — a Compose deploy would lack both | Fixed | IMPL-0005 |
| BUG-0005 | 2026-10-26 | S4 | test | New authz-matrix tests failed on first run (unauthenticated request builder `KeyError: 0`; admin's global scope wrongly expected 404) | Fixed | IMPL-0004 |
| BUG-0004 | 2026-10-26 | S2 | workflow | EVC visit updates ran in a second transaction after the main commit — a failure left the case and its booking contradictory | Fixed | IMPL-0003 |
| BUG-0003 | 2026-10-26 | S4 | test-harness | Test session showed pre-request state after an API call committed in another session | Fixed | IMPL-0002 |
| BUG-0002 | 2026-10-26 | S4 | docs | README repository map said 155 tests; actual 163 | Fixed | IMPL-0001 |
| BUG-0001 | 2026-10-26 | S3 | ocr | Tesseract binary missing → OCR tests skipped | Workaround | IMPL-0001 |

## Entry template
```
### BUG-XXXX — <short title>
- Date found / found by (human or agent + model) / branch / commit:
- Severity / Area (auth, workflow, rules, ocr, llm, db, migration, audit, frontend, ci, deploy, docs):
- Status:
- Where it showed up (command, endpoint, screen, test ID):
- Expected behaviour:
- Actual behaviour:
- Exact error output (trimmed, redacted):
- Steps to reproduce:
- Environment (OS, Python/Node versions, DB: SQLite/Postgres/Supabase, relevant env flags — no secrets):
- Hypotheses tried and what each showed (including ones that failed):
- Root cause:
- Solution applied (what changed, files, and why this fix rather than alternatives):
- Verification (exact command + result; regression test name/path):
- Side effects / follow-ups / related decisions (DEC-XXXX) / related IMPL-XXXX:
- Update history (date — change in status or approach):
```

## Entries (newest first)
<!-- add entries below this line -->

### BUG-0017 — second run of the Phase 4 exit check: audit actions came back in index order, faking the chronology
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), second `pytest tests/test_phase4_exit_check.py` (after BUG-0016's fix)
- Branch / commit: master (work uncommitted at time of fix; baseline `e0585f7`)
- Severity / Area: **S4** (test-only query; no product behaviour involved) / test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_phase4_exit_check.py -q` → 1 failed, 1 passed:
  ```
  E   AssertionError: missing audit action 'deficiency.finalized' in ['deficiency.finalized',
  E   'deficiency.closed', 'application.created', 'workflow.submit', 'workflow.start_scrutiny',
  'deficiency.doc_check_staged', 'deficiency.doc_check_staged', 'workflow.return_for_clarification',
  'workflow.resubmit', 'workflow.start_scrutiny']
  ```
- Expected behaviour: the ordered walk (staged → finalized → return → resubmit → start_scrutiny) should find each action after the previous one; `deficiency.finalized` was expected between staging and the return.
- Actual behaviour: `deficiency.finalized` and `deficiency.closed` appeared **first** in the list — before `application.created` — so the "after the previous index" walk failed even though every action was present.
- Environment: macOS, Python 3.13, SQLite.
- Hypotheses tried: (1) seed writes deficiency audit rows? — no: a fresh seeded DB holds exactly 3 events (`application.created`, `workflow.submit`, `workflow.start_scrutiny`, printed via a direct query); (2) promotion audit written before staging? — impossible, staging committed first; (3) **root cause** — my helper did `select(action).where(entity_id.in_(APP, def_id))` with no `order_by`; SQLite satisfied the `IN` filter through the `entity_id` index and returned rows in index order (all `def_id` uuid rows sort before `app-main-0001`), not insertion order.
- Root cause: the test assumed SQL returns rows in insertion order; without `ORDER BY` the planner is free to use the indexed column's order. `AuditEvent` has an autoincrement `seq` primary key precisely for chronology.
- Solution applied: the helper now orders by `AuditEvent.seq`. No product change — every event was written correctly all along.
- Verification: `pytest tests/test_phase4_exit_check.py -q` → **2 passed**; `ruff check` clean.
- Side effects / follow-ups: none. Worth remembering for future audit-order assertions: order by `seq`, never rely on natural order. Related IMPL-0037.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0016 — first run of the Phase 4 exit check: report read `open` instead of `received` after resubmit
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `pytest tests/test_phase4_exit_check.py` after writing the exit check
- Branch / commit: master (work uncommitted at time of fix; baseline `e0585f7`)
- Severity / Area: **S4** (test-time composition; production timing unaffected) / compliance window + test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_phase4_exit_check.py -q` → 1 failed, 1 passed:
  ```
  >       assert report["window_status"] == "received"
  E       AssertionError: assert 'open' == 'received'
  E         - received
  E         + open
  ```
  (in `test_the_full_deficiency_compliance_rescrutiny_loop`, after the institution's `resubmit`)
- Expected behaviour: after the institution resubmits, the report answers `window_status: "received"` with `resubmitted_at` set (Phase 4.4 design, FR-15).
- Actual behaviour: still `"open"`, `resubmitted_at: null`, so `awaiting_re_scrutiny` was false as well.
- Environment: macOS, Python 3.13, SQLite, fixed clock (`FixedClock(2026-10-22T09:00Z)` from `tests/conftest.py`).
- Hypotheses tried: (1) wrong `ISSUE_ACTION`/`RESUBMIT_ACTION` constants? — no, the issue instant resolved fine (report went `not_issued → issued` with `window_status: open`); (2) resubmit not recorded as a `WorkflowTransition`? — no, `workflow.resubmit` audited and state became `submitted`; (3) **root cause** — `_resubmitted_at` (compliance.py line 101) requires `moment > since` (strictly after the issue instant), and the exit-check test ran `return_for_clarification` and `resubmit` in the *same fixed-clock instant* (`09:00:00Z`), so `09:00 > 09:00` is false.
- Root cause: time compression in the test, not a service defect — the strict `>` is correct production semantics (a reply must come *after* the issue, and a same-instant resubmit from an *earlier* return cycle must not count as the reply to the *latest* one; ids are uuid4 so timestamps are the only order). The demo/test clock simply never moved between the two transitions.
- Solution applied: the exit-check test now advances the clock through the **real Phase 3.8 demo-clock service** (`demo_clock.advance(db, admin_access, 1)`, audited) between the return and the resubmit — one day later, matching reality where correction takes time — plus an autouse `set_clock(FixedClock(DEMO_NOW))` reset fixture so the jump cannot leak (the Phase 3 exit-check pattern). Service code unchanged.
- Verification: `pytest tests/test_phase4_exit_check.py -q` → **2 passed** (see IMPL-0037).
- Side effects / follow-ups: none — no production behaviour changed. Demo note: a walkthrough that returns and resubmits *without* advancing the demo clock will read `open`, not `received`; advance the clock (admin demo-clock) between the two steps. Related IMPL-0037.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0015 — first run of the new RULE-DOC-01 suite: one failure from a wrong test expectation (candidates omitted the affidavit)
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `pytest tests/test_doc_check.py` after writing the suite
- Branch / commit: master (work uncommitted at time of fix; baseline `6545a09`)
- Severity / Area: **S4** (test-only; the service behaviour was correct) / test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_doc_check.py -q` → 1 failed, 23 passed:
  ```
  E         Extra items in the left set:
  E         'affidavit_2'
  tests/test_doc_check.py:199: AssertionError
  ```
  (in `test_a_transcribed_checklist_names_each_missing_line`)
- Expected behaviour: the candidate set for `app-second-0002` + t23-13 was asserted as exactly the two Annexure-2 lines missing there (`noc_format_2`, `resolution_format_3`).
- Actual behaviour: the service also named `affidavit_2` — correctly: `app-second-0002` uploads only `lease_deed`, so FR-06's affidavit is missing too and the precedence makes it a definite candidate.
- Environment: macOS, Python 3.13, SQLite, fixed clock.
- Hypotheses tried: (1) wrong line keys from the service? — no, both `annexure:t23-13:*` keys were present as expected, the diff showed one *extra* item only; (2) should the affidavit be suppressed on a case with a transcribed checklist? — no: FR-06 names Affidavit 2 independently of the inventory, and suppressing it would hide a real candidate.
- Root cause: my test premise forgot the affidavit leg while exercising the inventory leg — the expectation was incomplete, not the rule evaluation.
- Solution applied: `backend/tests/test_doc_check.py` — the expected key set now includes `affidavit_2` with a comment that SECOND uploads no affidavit. Service and config unchanged.
- Verification: `pytest tests/test_doc_check.py -q` → **24 passed**; `make lint` clean; full `make test` → 673 passed.
- Side effects / follow-ups: none. Related IMPL-0036.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0014 — the `existing_technical` route defines no deficiency-return or resubmit transition at all (FR-15 loop unreachable on that route)
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), while driving the Phase 4.4 deficiency-report tests on the first seeded case
- Branch / commit: master (work uncommitted at time of discovery)
- Severity / Area: **S3** (feature degraded on one route; other routes work, tests use `new_technical`) / workflow config (`backend/rules/workflow_routes.json`)
- Status: **Open** — a route-table change is a human-approval gate (AGENTS.md: "new regulatory routes/states"); I did NOT edit the route config
- Where it showed up: `workflow_service.request_transition(..., "return_for_clarification")` on `app-existing-0003` →
  ```
  TransitionDecision(accepted=False, ..., reasons=["action 'return_for_clarification' is not defined for route 'existing_technical'"])
  ```
- Expected behaviour: every route whose cases can be scrutinised can also be returned for clarification with a deficiency report and later resubmitted (FR-15, PRD flow line 116: "Scrutiny/Re-Scrutiny ⇄ Compliance cycle"), unless a documented regulatory reason says otherwise.
- Actual behaviour: the route table has `return_for_clarification` (scrutiny→returned) and `resubmit` (returned→submitted) for `new_technical`, `evc_only` (from submitted) and `evc_sac_shc`, but **neither** transition for `existing_technical`. An officer on an existing-technical case therefore cannot return it with a deficiency report through the configured workflow at all — `api/deficiencies.py` will happily create draft rows, but there is no route that issues them.
- Steps to reproduce: seeded DB → `request_transition(db, scrutiny_access, "app-existing-0003", "return_for_clarification", reason="x", reason_code="RC-CLARIFICATION")` → refused as above. Route dump: `json.load(open("backend/rules/workflow_routes.json"))["routes"]["existing_technical"]["transitions"]` contains only submit/start_scrutiny/schedule_evc/complete_evc/approve/reject.
- Environment: macOS, Python 3.13, SQLite, fixed clock; `workflow_routes.json` as of commit `c2e054d`.
- Hypotheses tried: (1) mis-read the route key? — no, `Application.route_key == "existing_technical"` in seed and the route's own transition list confirms the absence; (2) maybe the return happens from `submitted` instead? — `evc_only` returns from `submitted`, but `existing_technical` defines the action nowhere.
- Root cause: **not determined — and it needs a human.** Either the route table is incomplete for `existing_technical` (likely: `md/GAP_NOTES.md` line 15 documents the other routes' returned-state shape but not this one), or the regulatory handling of existing-technical applications genuinely differs. Deciding which is an APH-interpretation call.
- Solution applied: **none to the config.** Worked around for testing by driving the FR-15 loop on `app-main-0001` (`new_technical`, which has both legs) and recorded the gap here + in IMPL-0035's limitations/open-questions. Nothing in `compliance.py` or the API assumes a route, so the feature works the moment a human adds the transitions.
- Verification: `pytest tests/test_compliance_report.py -q` → 25 passed on `new_technical`; `pytest tests/test_authz_matrix.py` → green.
- Side effects / follow-ups: if confirmed a gap, the fix is two entries in `workflow_routes.json` (same shape as `new_technical`) + a regression test per route — route config change needs approval first. Related IMPL-0035.
- Update history: 2026-10-27 — found; left Open pending a human decision.

### BUG-0013 — third run of the new FR-15 suite: three test-authoring defects (`select().count()`, business-tz hour asserted on a UTC timestamp, re-return attempted from `submitted`)
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), `pytest tests/test_compliance_report.py` after fixing BUG-0012
- Branch / commit: master (work uncommitted at time of fix)
- Severity / Area: **S4** (test-only; the product code was never wrong) / test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_compliance_report.py -q` → 3 failed, 22 passed:
  1. `AttributeError: 'Select' object has no attribute 'count'` in `test_the_sweep_raises_the_7d_2d_and_due_reminders`
  2. `assert (18 == 23)` in `test_the_window_closes_at_the_end_of_the_configured_day`
  3. `AssertionError: ["action 'return_for_clarification' requires state 'scrutiny', case is in 'submitted'"]` in `test_a_re_return_starts_a_fresh_reminder_cycle`
- Expected behaviour: all 25 tests pass.
- Actual behaviour: three independent failures, all in the draft test code.
- Environment: macOS, Python 3.13, SQLite, fixed clock.
- Hypotheses tried and what each showed: (1) for the hour assertion — maybe `end_of_day` was wrong? No: `deadline_service.end_of_day` builds 23:59:59 in `settings.business_timezone` and converts to UTC, and `compliance.iso()` renders UTC, so 18:29 is *correct* (Asia/Kolkata 23:59); the assertion was checking the wrong timezone. (2) for the AttributeError — no hypothesis needed, SQLAlchemy 2.0 `select()` has no `.count()`; `select(func.count()).select_from(Alert).where(...)` is the repo's style. (3) for the state error — the resubmit had moved the case to `submitted`, and only then does `start_scrutiny` (submitted→scrutiny) make a second return legal; the helper needed that leg, mirroring the real Re-Scrutiny loop.
- Root cause: three drafting mistakes in the new suite — a SQLAlchemy API slip, an assertion that ignored the documented end-of-day-in-business-tz convention, and an incomplete walk of the workflow loop.
- Solution applied: `backend/tests/test_compliance_report.py` — an `alert_count()` helper using `select(func.count()).select_from(...)`; the close-time assertion now converts with `ZoneInfo(get_settings().business_timezone)` before checking 23:59; the re-return test drives `start_scrutiny` an hour before the second `return_for_clarification`. Product code unchanged — each failure was a wrong expectation about correct behaviour.
- Verification: `pytest tests/test_compliance_report.py -q` → **25 passed**; `make lint` clean; full `make test` → 649 passed.
- Side effects / follow-ups: none. Related IMPL-0035.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0012 — first run of the new FR-15 suite: 11 failures from two test-authoring mistakes (wrong seeded route; missing mandatory FR-28 reason code)
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `pytest tests/test_compliance_report.py` after writing the suite
- Branch / commit: master (work uncommitted at time of fix; baseline `c2e054d`)
- Severity / Area: **S4** (test-only) / test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_compliance_report.py -q` → 11 failed, 14 passed:
  ```
  AssertionError: ["action 'return_for_clarification' is not defined for route 'existing_technical'"]
  ```
  then, after switching the case, still 11 failed:
  ```
  AssertionError: ['a reason code is mandatory on return (PRD FR-28); valid codes: RC-DOC-MISSING, RC-CLARIFICATION, RC-OTHER']
  ```
- Expected behaviour: the helper issues the report (draft deficiencies + accepted return) so the window tests can assert against it.
- Actual behaviour: every test that needed an issued report failed at the setup helper.
- Environment: macOS, Python 3.13, SQLite, fixed clock (2026-10-22 09:00 UTC).
- Hypotheses tried: (1) the transition helper was wrong? — no, `request_transition` correctly refused both times; (2) which seeded route actually has the legs? — dumped `workflow_routes.json`: `new_technical` and `evc_sac_shc` have return+resubmit, `existing_technical` has neither (that absence became BUG-0014, still Open); (3) the reason-code refusal — no hypothesis needed, the message names the rule (FR-28) and the valid codes.
- Root cause: two test-authoring mistakes — the suite picked `app-existing-0003` for convenience without checking its route's transitions, and the return call omitted the reason code that FR-28 (via `reason_codes.json`) makes mandatory.
- Solution applied: `backend/tests/test_compliance_report.py` — the case became `app-main-0001` (`new_technical`: both legs, institution-owned, assigned to the scrutiny officer), and `_transition()` gained a `reason_code` parameter with `RC-CLARIFICATION` on every return. The workflow rules themselves are untouched — they were right.
- Verification: `pytest tests/test_compliance_report.py -q` → 22 passed (3 remained, filed as BUG-0013).
- Side effects / follow-ups: surfaced BUG-0014 (route-config gap). Related IMPL-0035.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0011 — `alembic check` red on the new scrutiny tables: model said `unique=True` on the column, migration created a named constraint
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `alembic check` after writing `backend/migrations/versions/0015_scrutiny_results.py`
- Branch / commit: master (work uncommitted at time of fix; baseline f537b40)
- Severity / Area: **S4** (caught before commit; nothing deployed) / migration
- Status: **Fixed**
- Where it showed up: `SIH_DATABASE_URL=sqlite:////tmp/sih_check_43.db alembic check` →
  ```
  Detected changed index 'ix_scrutiny_overall_results_application_id' on 'scrutiny_overall_results': unique=False to unique=True
  FAILED: New upgrade operations detected: [('remove_constraint', ...), ('remove_index', ...), ('add_index', ... unique=True)]
  ```
- Expected behaviour: `alembic check` answers "No new upgrade operations detected." after `upgrade head`.
- Actual behaviour: autogenerate saw a diff between the ORM metadata and the just-created schema — first on the index uniqueness, then (after the first fix attempt) a leftover `UniqueConstraint` the DB did not have.
- Steps to reproduce: create the two tables with `sa.UniqueConstraint("application_id", name="uq_scrutiny_overall_result_case")` in the migration but model the column as `index=True, unique=True`; run `alembic upgrade head` then `alembic check`.
- Environment: macOS, Python 3.13, SQLite (`sqlite:////tmp/sih_check_43.db`), alembic from `.venv`.
- Hypotheses tried: (1) make the migration's index `unique=True` to match `unique=True` on the model column → next check flagged a `UniqueConstraint` removal, because SQLAlchemy emits *both* a unique index and the column-level constraint semantics that autogenerate compares differently from a named table constraint; (2) align both sides on the **named-constraint** form used by every other table in this repo (`__table_args__ = (UniqueConstraint("application_id", name="uq_scrutiny_overall_result_case"),)` + plain `index=True`) and keep the migration's named constraint + plain index → clean.
- Root cause: the ORM model and the migration expressed the same "one overall row per case" rule in two different DDL forms; autogenerate compares forms, not intent.
- Solution applied: `backend/app/models/application.py` — `ScrutinyOverallResult.__table_args__` now declares the named `UniqueConstraint` and `application_id` is plain `index=True`; the migration keeps the named constraint and a non-unique index (matches the sibling `ScrutinyItemResult` table's style). No behaviour change: the constraint is identical either way.
- Verification: `rm -f /tmp/sih_check_43.db && alembic upgrade head && alembic check` → "No new upgrade operations detected."; `pytest tests/test_scrutiny_results.py -q` → 24 passed.
- Side effects / follow-ups: none. Related IMPL-0034.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0010 — new scrutiny-result tests wrote placeholder user ids into a real FK (`recorded_by`)
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `pytest tests/test_scrutiny_results.py` after writing the suite
- Branch / commit: master (work uncommitted at time of fix; baseline f537b40)
- Severity / Area: **S4** (test-only; the FK correctly refused the bad data) / test
- Status: **Fixed**
- Where it showed up: `pytest tests/test_scrutiny_results.py -q` → 12 failed, 33 passed:
  ```
  sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) FOREIGN KEY constraint failed
  [SQL: INSERT INTO scrutiny_item_results (..., recorded_by, ...) VALUES (...)]
  [parameters: (..., 'app-existing-0003', ..., 'user-scrutiny', ...)]
  ```
- Expected behaviour: the suite records results under real seeded user ids and passes.
- Actual behaviour: every service-level test passed `actor_id="user-a"` / `"user-scrutiny"` — invented ids that exist in no `users` row, so the `recorded_by` FK refused them at flush.
- Steps to reproduce: `record_item_result(db, app, ..., actor_id="user-scrutiny")` on a seeded database, then `db.commit()`.
- Environment: macOS, Python 3.13, SQLite test database, fixed clock.
- Hypotheses tried: none needed — the error text pointed straight at the parameter; the same defect had been seen before in BUG-0009 (guessed user ids) and the fix pattern already exists in `test_escalation.py` (`select(User.id).where(User.email == ...)`).
- Root cause: the draft suite invented actor ids instead of resolving seeded users; `recorded_by` is a genuine foreign key to `users.id`, and rightly so.
- Solution applied: `backend/tests/test_scrutiny_results.py` gains a `_user_id(db, email)` helper (resolves a seeded user by email); all placeholder ids replaced with `_user_id(db)` / `_user_id(db, "regional@demo.local")`. The model is unchanged — the FK staying strict is the correct behaviour.
- Verification: `pytest tests/test_scrutiny_results.py -q` → 24 passed; full `make test` → 624 passed.
- Side effects / follow-ups: none. Regression coverage: every test in the suite that records a result now goes through `_user_id`, and `test_every_recording_is_audited` additionally proves the recorded-by chain end to end. Related IMPL-0034.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0009 — new exit-check test failed lint (unused import) and guessed non-existent user ids
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `make lint` after writing `backend/tests/test_phase3_exit_check.py`
- Branch / commit: master (work uncommitted at time of fix; baseline 959f141)
- Severity / Area: **S4** (test-only; no product code involved) / test-harness
- Status: **Fixed**
- Where it showed up: `make lint` → `Found 1 error`:
  ```
  F401 [*] `datetime.timedelta` imported but unused
    --> tests/test_phase3_exit_check.py:26:22
  ```
  The same drafting pass also left a stray mid-file `import pytest` and two recipient assertions that hard-coded `"user-regional"` / `"user-supervisory"` as user ids — seeded `User` ids are auto-generated, so those assertions would have failed with `AssertionError` on the first API run (caught by reading `seed.py`, not by a red test).
- Expected behaviour: lint clean; recipient assertions that hold against the seeded data.
- Actual behaviour: one F401; two latent assertion failures against ids that do not exist.
- Steps to reproduce: run the file at the drafted version, then `make lint` / `pytest tests/test_phase3_exit_check.py`.
- Environment: macOS, Python 3.13.9 (venv), SQLite test DB, fixed clock.
- Hypotheses tried:
  1. *Recipient ids are stable strings like `user-regional`* — rejected: `seed.py::user()` builds `User` rows through `_get_or_create` with no explicit id, so ids are `new_id()`-generated; the correct lookup is by email.
- Root cause: drafting leftovers (unused import, hoisting not applied) and an unverified guess about seed id formatting instead of resolving users by their documented email keys.
- Solution applied: removed the unused `timedelta` import and the mid-file import; added `_user_id(db, email)` helper resolving `regional@demo.local` / `supervisor@demo.local` via query. No product code changed.
- Verification: `make lint` → All checks passed; `make test` → **582 passed**; `pytest tests/test_phase3_exit_check.py -q` → 7 passed.
- Side effects / follow-ups: none. Related: IMPL-0032.
- Update history: —

### BUG-0008 — new routing test expected 200; `POST /applications` returns 201
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first run of `backend/tests/test_routing.py::test_creating_a_case_audits_its_route_decision`
- Branch / commit: master (work uncommitted at time of fix)
- Severity / Area: **S4** (test-only; the route was created correctly and the audit row was written) / test-harness
- Status: **Fixed**
- Where it showed up: `pytest tests/test_routing.py::test_creating_a_case_audits_its_route_decision -q -p no:randomly` → `1 failed`:
  ```
  E       assert 201 == 200
  E        +  where 201 = <Response [201 Created]>.status_code
  ```
- Expected behaviour: application creation succeeds and the audit row is asserted.
- Actual behaviour: the assertion failed on the HTTP status; the request itself returned `201 Created` and wrote the audit event.
- Steps to reproduce: run the new test at the commit before the fix.
- Environment: macOS, Python 3.14.3, SQLite (test DB), fixed clock.
- Hypotheses tried:
  1. *The endpoint errors* — rejected: the log line shows `POST /api/v1/applications "HTTP/1.1 201 Created"`.
  2. *The status code is wrong* — confirmed: `create_application` is a resource-creation route and FastAPI returns 201 for a successful `POST` that creates a resource; my test asserted the generic 200.
- Root cause: my test guessed the status code instead of matching the route's actual (correct) 201 Created.
- Solution applied: changed the assertion to `assert created.status_code == 201`. No product code changed.
- Verification: `pytest tests/test_routing.py -q -p no:randomly` → **11 passed**; `make test` → **491 passed, 2 skipped**.
- Side effects / follow-ups: none. Related: IMPL-0025.
- Update history: —

### BUG-0007 — routing test assumed every pattern is used by a Table 2.3 row
- Date found / found by: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6), first run of `backend/tests/test_routing.py`
- Branch / commit: master @ 0975417 (work uncommitted at time of fix)
- Severity / Area: **S4** (test-only; the configuration and service were correct) / test-harness
- Status: **Fixed**
- Where it showed up: `pytest tests/test_routing.py -q -p no:randomly` → `1 failed, 9 passed`:
  ```
  FAILED tests/test_routing.py::test_every_route_used_by_a_table_2_3_row_has_a_stage_list
  ```
- Expected behaviour: all 10 routing tests green against the data written in task 1.1.
- Actual behaviour: the drift-guard failed.
- Exact error output (trimmed):
  ```
  E       AssertionError: ({'SCR', 'SCR+EVC+AA', 'SD'}, {'SCR', 'SCR+EVC', 'SCR+EVC+AA', 'SD'})
  E       Extra items in the right set:
  E       'SCR+EVC'
  ```
- Steps to reproduce: run the new file as written at the commit before the fix.
- Environment: macOS, Python 3.13.9, SQLite (test DB), fixed clock.
- Hypotheses tried:
  1. *A Table 2.3 row's route value is misspelled or the patterns section lost a key* — rejected: the failing tuple shows the rows use exactly {SD, SCR, SCR+EVC+AA} and all four patterns are defined.
  2. *The test's invariant is wrong* — confirmed: re-reading the PRD's Table 2.3 (md/1_PRD.md §6), **no row is plain SCR+EVC**; the pattern exists in §6's definitions and in the prototype state machines (e.g. `new_technical`), and is needed for the random-EVC add (2.3.5), but no category currently maps to it.
- Root cause: the test asserted `used == defined` (every pattern used by a row, every used route defined). The true contract is `used ⊆ defined` plus "all four documented patterns exist".
- Solution applied: the test now asserts `used <= defined` (a row may never point at an undefined pattern) **and** `defined == {SD, SCR, SCR+EVC, SCR+EVC+AA}` (all four documented patterns stay defined), with a comment recording that plain SCR+EVC is currently used by no Table 2.3 row and why it must still exist. No data or product code changed.
- Verification: `pytest tests/test_routing.py -q -p no:randomly` → **10 passed**; `make lint` → `All checks passed!`; `make test` → **221 passed, 1 warning**.
- Side effects / follow-ups: none. Related: IMPL-0008.
- Update history: —

### BUG-0006 — migrations out of sync: `deficiencies` and `evc_visits` had no migration
- Date found / found by: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6), running the mandatory `make migrate-sqlite` (which includes `alembic check`) as part of the H.4 definition of done
- Branch / commit: master @ 271f8db (work uncommitted at time of fix)
- Severity / Area: **S2** (feature broken in a Compose deploy, no workaround in that environment) / migration, db
- Status: **Fixed**
- Where it showed up: `make migrate-sqlite` → `alembic upgrade head` succeeded, then `alembic check` failed:
  ```
  ERROR [alembic.util.messaging] New upgrade operations detected: [('add_table', Table('evc_visits', ...
  Detected added index 'ix_deficiencies_application_id' ... (12 add_index, 4 add_table ops total)
  ```
- Expected behaviour: `alembic check` reports `No new upgrade operations detected.` — every ORM table and index is created by a migration.
- Actual behaviour: `alembic check` detected two whole tables (`deficiencies`, `evc_visits`) plus 12 indexes missing from the migration chain. The SQLite **test** suite stayed green because `conftest.py` builds the schema from `Base.metadata.create_all`, but the Compose stack (`docker-compose.yml` migrate service: `alembic upgrade head` only, then `sql/roles.sql`) would come up with a schema lacking both tables — `POST /applications/{id}/deficiencies`, the whole deficiency loop, and EVC visit scheduling would fail at runtime with "no such table".
- Exact error output (trimmed):
  ```
  ERROR [alembic.util.messaging] New upgrade operations detected: [('add_table', Table('evc_visits', MetaData(), ...
  ```
- Steps to reproduce: `cd backend && SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic upgrade head && ... -m alembic check` (or `make migrate-sqlite`) at any commit after `889c026`/`4fd3c4d`.
- Environment: macOS, Python 3.13.9, SQLite throwaway DB; same drift would affect Postgres/Compose.
- Hypotheses tried:
  1. *The tables exist under different names* — rejected: `grep -o "create_table('[a-z_]*'" migrations/versions/*.py` showed neither name anywhere in the chain.
  2. *Only my new `upload_reason` column is missing* — rejected: the column was covered by my 0007; the diff listed `add_table` ops only for `deficiencies` and `evc_visits`.
  3. *Tests create tables another way, masking this* — confirmed: `conftest.py` uses `Base.metadata.create_all`, which is why 199 tests passed while the migration chain was broken.
- Root cause: commits `889c026` (structured deficiency loop) and `4fd3c4d` (EVC visit scheduling) added ORM classes `Deficiency` and `EvcVisit` to `app/models/application.py` without generating Alembic migrations. Nothing in CI runs `alembic check`, so the drift went unnoticed.
- Solution applied: generated the missing migration with `alembic revision --autogenerate`, then restyled it to house conventions (revision id `0008_deficiencies_and_evc_visits`, dated docstring explaining why it exists, `from __future__ import annotations`, 88-col formatting) → `backend/migrations/versions/0008_deficiencies_and_evc_visits.py`. Tables and indexes exactly as the models declare them (FK `ondelete` clauses preserved: CASCADE on `application_id`, SET NULL on document/field references). The autogenerated draft file was deleted. Why a single new migration rather than amending old ones: history must stay append-only and re-runnable for anyone already at 0007.
- Verification: `ruff check migrations` → `All checks passed!`; fresh `/tmp/sih26262-migrate.db`: `alembic upgrade head` → runs 0007 then 0008; `alembic check` → **`No new upgrade operations detected.` / CHECK_OK**; `alembic downgrade 0007_document_upload_reason` then `upgrade head` again → both succeed (up/down/up round trip). `make test` still 206 passed.
- Regression guard: `make migrate-sqlite` (upgrade head + `alembic check`) is the definition-of-done gate for every model-touching task from now on; it is already a Makefile target and was run for H.4. CI does **not** run it — noted as an open question for a human (adding a CI step is a repo-config change outside this task's scope).
- Side effects / follow-ups: none for the test suite; a Compose deploy that had already run `upgrade head` before 0008 will pick both tables up on the next `make up`. Related: IMPL-0005.
- Update history: —

### BUG-0005 — authz-matrix tests failed on their first run (two test-authoring defects)
- Date found / found by: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6), first run of `backend/tests/test_authz_matrix.py`
- Branch / commit: master @ 0b4bd11 (work uncommitted at time of fix)
- Severity / Area: **S4** (test-only; the product behaved correctly in both cases) / test-harness
- Status: **Fixed**
- Where it showed up: `pytest tests/test_authz_matrix.py -q -p no:randomly` → `2 failed, 19 passed`:
  ```
  FAILED tests/test_authz_matrix.py::test_every_gated_route_refuses_a_request_without_a_token
  FAILED tests/test_authz_matrix.py::test_out_of_scope_case_is_404_not_403_for_a_role_that_may_act[admin@demo.local]
  ```
- Expected behaviour: all 21 matrix tests green against the unmodified application.
- Actual behaviour: two failures, both in the new tests, not in the API.
- Exact error output (trimmed):
  ```
  E           KeyError: 0                      <- unauthenticated test
  ```
  and, for the administrator row, `got 200, expected 404`.
- Steps to reproduce: run the new file as-is at the commit before the fix.
- Environment: macOS, Python 3.13.9, SQLite (test DB), fixed clock.
- Hypotheses tried:
  1. *The product returns the wrong status for anonymous calls* — rejected: the `KeyError` came from inside the test's own request builder.
  2. *The product leaks an out-of-scope case to the administrator* — rejected: the administrator has `SCOPE_GLOBAL`, so `app-second-0002` **is** in scope for them by design.
- Root cause (two separate defects in the new test file):
  1. `_request` built the `POST /api/v1/applications` body by calling `GET /api/v1/institutions` and indexing `[0]`; without a token that call answers `401 {"error": ...}` (a dict), so `listed[0]` raised `KeyError: 0` instead of letting the route gate answer 401.
  2. The out-of-scope test assumed every role was confined to a scope. `ROLE_DEFAULT_SCOPE[administrator] == SCOPE_GLOBAL`, so the expected status for them is "passes authorisation", not 404.
- Solution applied: `_target_institution(...)` now accepts a non-list/empty answer (401 payload, or a role whose institution list is scope-filtered to nothing) and falls back to a seeded institution id from the database — the body is only a placeholder for callers the gate will refuse anyway. The out-of-scope test branches on `ROLE_DEFAULT_SCOPE[role] == SCOPE_GLOBAL` and asserts the in-scope expectation for the administrator, with a comment saying why. No product code touched (`git diff` on `app/api/deps.py` and `app/services/authorization_service.py` empty after the temporary mutation proof was restored).
- Verification: `pytest tests/test_authz_matrix.py -q -p no:randomly` → **21 passed**; `make lint` → `All checks passed!`; `make test` → **199 passed, 1 warning**.
- Side effects / follow-ups: none. Related: IMPL-0004.
- Update history: —

### BUG-0004 — EVC visit updates committed in a second transaction after the main workflow commit
- Date found / found by: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6), Phase 0.5 H.2 code inspection, confirmed by a failing test before the fix
- Branch / commit: master @ a3477cb (work on top, uncommitted at time of fix)
- Severity / Area: **S2** (feature degraded: case and booking can contradict; no data loss, chain still valid, recoverable by re-running the completion) / workflow + evc
- Status: **Fixed**
- Where it showed up: `backend/tests/test_transaction_boundary.py::test_visit_update_failure_rolls_back_the_whole_evc_completion` and `...::test_visit_cancellation_failure_rolls_back_the_whole_revert` (both written first, both failed against the old code)
- Expected behaviour: a workflow action and its EVC booking side-effects (completion on `complete_evc`, cancellation on revert) commit in **one** transaction — all or nothing (plan H.2; Essentials 17).
- Actual behaviour: `request_transition` committed the state/transition/assignment/audit at line 342 and *then* called `_complete_evc_visits`, which ran its own `db.commit()` in a second transaction; `revert_last_transition` did the same with `_cancel_visits_on_revert`. A failure in the second transaction left the case at `evc_completed` with the visit still `scheduled` (or reverted with the booking still live) — the queue report and the workflow state contradicting each other.
- Exact error output (trimmed):
  ```
  E       AssertionError: assert 'evc_completed' == 'evc_scheduled'
  E         - evc_scheduled
  E         + evc_completed
  ```
- Steps to reproduce: monkeypatch `workflow_service._complete_evc_visits` (or `_cancel_visits_on_revert`) to raise, call the transition/revert, then read the case state and the visit row: the case had moved, the visit had not.
- Environment: macOS, Python 3.13.9, SQLite (test DB), fixed clock — the bug is dialect-independent (two commits, not an SQLite quirk).
- Hypotheses tried: none needed beyond the failing test — the two-commit structure was visible in the source (`workflow_service.py` lines 342→347/386 and 646→694); the test pinned it before the fix to prove causality.
- Root cause: the booking side-effects were added *after* the main `db.commit()` as a second transaction (probably to reuse the session post-commit), splitting one business action across two commits with a failure window between them.
- Solution applied: moved both helper calls **before** the single `db.commit()` in their respective flows and removed their internal `db.commit()`s (documented "runs inside the caller's transaction" in both docstrings). Files: `backend/app/services/workflow_service.py` only. Rejected alternative: a compensating action on failure — more code and still a visible half-state between the commits.
- Verification: the two regression tests above now pass; `make lint` clean; `make test` → **178 passed, 1 warning** (0 skipped).
- Side effects / follow-ups: audit-event ordering changed slightly — `evc.visit_cancelled` now lands in the same transaction as `workflow.revert` (previously a separate committed event after it); the full suite passes, no test depended on the old order. Related: IMPL-0003.
- Update history: —

### BUG-0003 — Test session showed pre-request state after an API call committed elsewhere
- Date found / found by / branch / commit: 2026-10-26 / MiMo (OpenCode agent) / master @ a3477cb (uncommitted H.1 work)
- Severity / Area: S4 / test-harness
- Status: Fixed
- Where it showed up: `pytest tests/test_concurrency.py::test_transition_endpoint_carries_the_expected_version` — final assertion `current_state == "approved"` returned `"scrutiny"` even though both HTTP responses were correct (200, accepted true; then 200, accepted false with reload message).
- Expected behaviour: after the API accepted the transition, the test-side `db` session reads the committed state.
- Actual behaviour: the test session's identity map still returned the `Application` row as it was when the test first loaded it.
- Exact error output (trimmed):
  ```
  E       + scrutiny
  tests/test_concurrency.py:221: AssertionError
  ```
- Steps to reproduce: in one test, load an Application via the `db` fixture, mutate it through `client.post(...)` (API uses its own session per request), then `db.get(Application, id)` without expiring.
- Environment: macOS, Python 3.13.9, SQLite test DB, fixed clock; FastAPI TestClient.
- Hypotheses tried: (a) thought the transition had not committed — disproved by the HTTP body (`accepted: true`) and by the service-level tests passing on the same flow; (b) real cause: SQLAlchemy session identity-map staleness — each TestClient request opens a *new* session via `get_db`, so the test session never sees the commit until its own snapshot is expired.
- Root cause: cross-session read-your-writes; the `db` fixture session caches ORM objects and does not auto-refresh after another session commits.
- Solution applied: `db.expire_all()` before the database assertion in the HTTP-level test (comment references this BUG). Chose this over `db.expire(application)` (targeted but brittle — any earlier-touched object would bite next) and over committing/rolling back in the test (would hide the real committed state).
- Verification: `pytest tests/test_concurrency.py -q` → 7 passed; `make test` → 170 passed.
- Side effects / follow-ups: none in product code. Future HTTP-then-DB tests in this suite must expire before asserting.
- Update history: —

### BUG-0002 — README repository map said 155 tests; actual is 163
- Date found / found by / branch / commit: 2026-10-26 / MiMo (OpenCode agent) / master / a3477cb
- Severity / Area: S4 / docs
- Status: Fixed
- Where it showed up: Phase 0 repository audit (IMPL-0001); reading `README.md` while reconciling doc claims against the recorded baseline.
- Expected behaviour: every test-count mention in the docs matches the recorded baseline (`make test`).
- Actual behaviour: the "Tests" section correctly said `163 passed`, but the "Repository map" section still said `tests/          155 tests`.
- Exact error output: n/a (doc drift, not an error). Stale line: `tests/          155 tests`.
- Steps to reproduce: `grep -n "155" README.md`.
- Environment: macOS, repo master @ a3477cb.
- Hypotheses tried: none needed — the live run (`163 passed, 1 warning`) is the authority.
- Root cause: the count was raised from 155 → 159 → 163 across earlier sessions; the Tests section was updated but the one-line repository-map entry was missed.
- Solution applied: `README.md` repository map now says `tests/ 163 tests`. Chose a direct text fix over removing the number: the map is meant to be scannable, and an accurate count is more useful than none.
- Verification: `make test` → `163 passed, 1 warning in 16.59s`; `grep -n "163" README.md` shows the updated map line. Regression guard: none possible for prose (doc-only change) — noted instead of claimed.
- Side effects / follow-ups / related: none. Related IMPL-0001.
- Update history: —

### BUG-0001 — Tesseract binary missing, OCR tests skipped (seed entry from the technical specification)
- Date found: reported in spec v0.1 (26 Oct 2026) / found by: prior local run / commit: unknown
- Severity: S3 / Area: ocr / Status: Workaround
- Where it showed up: `make test` — historical report: 154 passed, 2 skipped, 1 warning
- Expected: OCR tests run; if the binary is absent the app degrades with an honest warning and never marks a document compliant
- Actual: 2 tests skipped because Tesseract was missing
- Root cause: host binary not installed (`brew install tesseract` on macOS; apt on Ubuntu)
- Solution applied: install Tesseract on the dev/CI host, or document it as optional and keep the skip explicit (`backend/tests/test_document_extraction.py::requires_ocr` = `skipif shutil.which("tesseract") is None`)
- Verification: **rerun 2026-10-26** on this machine (macOS, Python 3.13.9): `make test` → `163 passed, 1 warning in 16.59s`, **0 skipped** — Tesseract is present locally, so the OCR tests ran and passed. The skip mechanism remains as the honest degradation path for machines without the binary.
- Follow-ups: decide whether Tesseract is required or optional in CI (log as a DEC entry) — answered for the prototype in `docs/DECISIONS.md` D-0006: **optional** by design.
- Update history: 2026-10-26 — verified on a Tesseract-equipped machine: 0 skipped, status stays `Workaround` (skip path still exists for other hosts).
