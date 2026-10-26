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
