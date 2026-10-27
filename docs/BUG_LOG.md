# docs/BUG_LOG.md

| BUG-0058 | 2026-10-28 | S2 | release packaging | Appeal API module omitted from Phase 6.6 commit | Fixed | IMPL-0057 |
| BUG-0060 | 2026-10-28 | S3 | regression tests | Reopening integration exposed assignment and stage bookkeeping assumptions | Fixed | IMPL-0058 |
| BUG-0059 | 2026-10-28 | S3 | lint | Ruff rejected generated migration import order | Fixed | IMPL-0058 |
| BUG-0062 | 2026-10-28 | S4 | test fixture | Reopening transition test expected generic transition authorization | Fixed | IMPL-0058 |
| BUG-0061 | 2026-10-28 | S3 | authorization matrix | New reopening routes and Competent Authority role were absent from the matrix | Fixed | IMPL-0058 |

### BUG-0062 — Reopening bypass test assumed Competent Authority had generic transition access
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / pending.
- Severity / Area: S4 / test contract.
- Status: **Fixed**.
- Expected: test proves CA cannot reopen without approval/payment evidence.
- Actual: it expected HTTP 200 from an endpoint gated by existing `case.read`/`application.read`; the role correctly receives 403.
- Reproduction: `pytest tests/test_phase6_reopening.py`.
- Environment: pytest, FastAPI test client, SQLite.
- Hypotheses tried: generic transition is not the designated CA endpoint.
- Root cause: test expected a permission bypass instead of testing endpoint and service contracts.
- Solution: assert HTTP 403, then call the workflow service with effective CA access and verify the configured transition rejects missing evidence.
- Verification: focused reopening suite passed (3 tests); full suite passed 815 tests.
- Regression test: `test_reopen_transition_cannot_bypass_request_and_payment_review`.
- Related: IMPL-0058.

### BUG-0061 — Reopening authorization matrix omitted new routes and role
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / pending.
- Severity / Area: S3 / authorization regression coverage.
- Status: **Fixed**.
- Expected: every permission-gated reopening route and CA role is represented in the exhaustive matrix.
- Actual: focused matrix tests identified six missing routes and a stale specialized-role permission expectation.
- Reproduction: `pytest tests/test_authz_matrix.py` after adding reopening endpoints.
- Environment: pytest, FastAPI test client, SQLite.
- Hypotheses tried: new route dependencies were absent from the matrix.
- Root cause: the test matrix deliberately requires every gated route and role permission to be explicitly listed.
- Solution: add exact reopen/read/review/payment/evidence endpoint rows and CA demo persona; assert narrow CA review permission.
- Verification: authz, stage, assignment and reopening targeted suite passed 57 tests; full suite passed 815 tests.
- Regression test: `test_matrix_lists_every_permission_gated_route` and specialized-role permission assertion.
- Related: IMPL-0058.

### BUG-0060 — Reopening integration exposed assignment and stage bookkeeping assumptions
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / pending.
- Severity / Area: S3 / workflow assignment and stage bookkeeping.
- Status: **Fixed**.
- Expected: a new Competent Authority role does not receive routine submitted cases, and a case that leaves a stage in an accepted transition has that stage recorded as completed even when other routes can skip it.
- Actual: full suite initially selected the Competent Authority as the primary officer due load ordering and left a pending Scrutiny stage incomplete on an accepted return.
- Reproduction: `make test` after adding the reopening role and route.
- Environment: Python 3.13, SQLite test fixtures.
- Hypotheses tried: seeded CA role changed assignment candidate ordering; stage sync only backfilled mandatory route stages.
- Root cause: generic role discovery treated the special reopening action as an ordinary next actor; stage completion failed to record the actually exited source stage on a cross-route transition.
- Solution: exclude `reopen_application` from routine case assignment; on accepted transitions, complete a pending source stage when the transition proves it was entered and left.
- Verification: targeted assignment/stage/authz/reopening suite 57 passed; full `make test` subsequently passed **815 tests, 2 upstream warnings**.
- Regression test: existing case assignment and stage graph tests plus `test_phase6_reopening.py`.
- Related: IMPL-0058.

### BUG-0059 — Ruff rejected generated reopening migration import order
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / pending.
- Severity / Area: S3 / lint.
- Status: **Fixed**.
- Expected: generated migration conforms to repo Ruff settings.
- Actual: `make lint` reported I001 on the Alembic/SQLAlchemy imports.
- Reproduction: `make lint` after generating `c78327c876fb`.
- Environment: repo Ruff configuration.
- Hypotheses tried: generated template does not match custom import ordering.
- Root cause: Alembic autogenerated a split unsorted import block.
- Solution: formatted the import block with Ruff.
- Verification: `make lint` → all checks passed.
- Regression test: lint.
- Related: IMPL-0058.

### BUG-0058 — Appeal API module omitted from Phase 6.6 commit
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / `cd22678`.
- Severity / Area: S2 / release packaging and application startup.
- Status: **Fixed**.
- Expected: a clean checkout of the pushed Phase 6.6 commit imports the appeal router and exposes the appeal API.
- Actual: `backend/app/api/appeals.py` remained untracked, although it was present in the working tree used by tests and frontend integration.
- Reproduction: `git ls-files backend/app/api/appeals.py` returned no path after `cd22678`.
- Environment: local repository on `master`.
- Hypotheses tried: the file was omitted from the explicit `git add` path list.
- Root cause: staging command omitted `backend/app/api/appeals.py`.
- Solution applied: add and push the missing module in a dedicated repair commit.
- Verification: rerun focused appeal tests, `make lint`, full backend suite, and clean tree status after commit.
- Regression test: existing `backend/tests/test_phase6_appeals.py` loads and exercises the API router; rerun against the now tracked module.
- Related: IMPL-0057 / Phase 6.6.

| BUG-0057 | 2026-10-27 | S4 | verification command | Initial Alembic command ran outside configured backend directory | Fixed | IMPL-0057 |

### BUG-0057 — Initial Alembic command ran outside configured backend directory
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / verification command.
- Status: **Fixed**.
- Expected: fresh SQLite database upgrades through head and Alembic checks model sync.
- Actual: initial root invocation returned `FAILED: No 'script_location' key found in configuration.`
- Reproduction: run Alembic from repository root without explicitly selecting `backend/alembic.ini`.
- Environment: repo root shell, Python 3.13, SQLite.
- Hypotheses tried: config discovery was relative to the current working directory.
- Root cause: Alembic configuration is scoped to `backend/`; root invocation did not discover it.
- Solution: reran from `backend/` using `../.venv/bin/alembic`.
- Verification: fresh database upgraded through `7b41d34be5ee`; `alembic check` → `No new upgrade operations detected`.
- Regression test: none needed; command/configuration error only.
- Related: IMPL-0057 / Phase 6.6.

### BUG-0056 Update — Fixed with SQLite batch migration
- Status: **Fixed**. The initial `op.add_column(... ForeignKey ...)` could not apply against SQLite's existing workflow table because that backend does not support this constraint alteration directly.
- Solution: migration `0022_speaking_order_transition.py` now uses `op.batch_alter_table` to recreate the table and add the nullable FK and index portably.
- Verification: fresh SQLite database upgraded through head and `alembic check` reported `No new upgrade operations detected`; full `make test` → **798 passed, 1 warning, 0 skipped**.
- Regression coverage: Phase 6.5 decision tests exercise the Speaking Order link and wrong-case rejection.
- Related: IMPL-0056 / Phase 6.5 / FR-26.

### BUG-0056 — Speaking Order migration used unsupported SQLite constraint ALTER
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S3 / schema migration portability.
- Status: Open pending fresh-database verification.
- Where it showed up: Phase 6.5 migration check using SQLite.
- Expected: migration 0022 adds the nullable Speaking Order FK and index on SQLite and PostgreSQL.
- Actual: `alembic upgrade head` stopped with `NotImplementedError: No support for ALTER of constraints in SQLite dialect` at `op.create_foreign_key`.
- Steps to reproduce: `SIH_DATABASE_URL=sqlite:////tmp/sih-phase6-5.db ../.venv/bin/alembic upgrade head`.
- Environment: SQLite, repo Alembic environment, Python 3.13.
- Hypotheses tried: traceback identified direct `op.create_foreign_key` as the unsupported SQLite operation.
- Root cause: SQLite cannot ALTER a table to add a foreign key constraint outside batch/copy mode.
- Solution applied: use `op.batch_alter_table` for the nullable column, foreign key and index (and batch mode for downgrade).
- Verification: pending fresh SQLite migration upgrade and `alembic check`.
- Regression test: migration upgrade/check sequence.
- Related: Phase 6.5 / FR-26.

### BUG-0055 — Ruff found import ordering issues in Phase 6.5
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: targeted Phase 6.5/authz/appeal verification setup.
- Expected: Ruff accepts changed API/service/test files.
- Actual: Ruff reported three import-block issues after initial code additions.
- Steps to reproduce: `cd backend && ../.venv/bin/python -m ruff check app tests migrations scripts` before auto-fix.
- Environment: repo Ruff configuration and virtual environment.
- Hypotheses tried: Ruff identified mechanical ordering only.
- Root cause: new imports were hand-sorted incorrectly.
- Solution applied: ran Ruff `--fix` on the backend app/tests/migrations/scripts tree.
- Verification: `make lint` → clean; focused Phase 6.5/authorization/appeal suite → **49 passed, 1 upstream warning**.
- Regression test: full Ruff check and focused suite.
- Related: Phase 6.5 / FR-26.

### BUG-0054 — Phase 6.5 authorization matrix names and admin exception were stale
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S3 / authorization contract.
- Status: Fixed.
- Where it showed up: first focused Phase 6.5/authz/appeal suite.
- Expected: every gated route matches the authorization matrix; administrators do not hold Executive Committee decision/order-upload permissions.
- Actual: the renamed queue document route was stale in the matrix, and the administrator's derived all-permissions set caused two dedicated Executive Committee routes to return 403 after the permission gate.
- Steps to reproduce: `cd backend && ../.venv/bin/pytest -q tests/test_phase6_executive_decision.py tests/test_authz_matrix.py tests/test_appeal_clock.py` before the fixes.
- Environment: SQLite authorization tests.
- Hypotheses tried: compared discovered route path and role permission mapping against the test matrix and explicit endpoint role checks.
- Root cause: matrix still used `{hearing_id}` after the route changed to `{queue_item_id}`; administrator inherited every permission, including actions deliberately restricted to a human Executive Committee appointment.
- Solution applied: update the route matrix path and exclude `executive.order.upload` / `executive.decision.record` from administrator's generated permissions.
- Verification: Ruff clean; focused Phase 6.5/authorization/appeal suite → **49 passed, 1 upstream warning**.
- Regression test: route-discovery matrix and administrator/role scope tests.
- Related: Phase 6.5 / FR-26.


### BUG-0053 — Ruff rejected unsorted imports in Phase 6.4 changes
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: first required `make lint` after adding Phase 6.4 API and tests.
- Expected: Ruff accepts modified Python files.
- Actual: `I001` import sorting errors in `backend/app/api/evc.py`, `backend/tests/test_authz_matrix.py`, and `backend/tests/test_phase6_shc.py`, plus one unused import.
- Steps to reproduce: run `make lint` with the initial Phase 6.4 diff.
- Environment: repository virtual environment; Ruff configured by `backend/ruff.toml`.
- Hypotheses tried: Ruff output identified only mechanical import-order and unused-import issues.
- Root cause: hand-added imports did not follow the repository's Ruff ordering.
- Solution applied: ran Ruff's `--fix` on the backend source/test/migration/script tree.
- Verification: `make lint` → all checks passed; full backend suite → **794 passed, 1 upstream warning, 0 skipped**.
- Regression test: full Ruff invocation and backend suite.
- Related: Phase 6.4 / FR-24.

### BUG-0052 — SHC queue joined but did not select hearing records
- Update (2026-10-27): Fixed. Added `ShcHearing` to the query selection; focused Phase 6.3/6.4/authz suite **27 passed, 1 upstream warning**; `make lint` clean; full backend suite **794 passed, 1 upstream warning, 0 skipped**. Migration upgrade/check and frontend build also passed.

### BUG-0052 — SHC queue joined but did not select hearing records
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S3 / Phase 6 SHC API.
- Status: Open pending regression verification.
- Where it showed up: `make test` after Phase 6.4 queue/scheduling changes.
- Expected: SHC queue returns report and hearing data for each eligible row.
- Actual: both SHC queue tests returned HTTP 500; traceback was `ValueError: not enough values to unpack (expected 5, got 4)` at `backend/app/api/evc.py` while unpacking results.
- Steps to reproduce: `make test`; the Phase 6.3 SHC referral test or Phase 6.4 hearing lifecycle test calls `GET /api/v1/shc/queue`.
- Environment: local repo virtual environment, SQLite pytest database, Python 3.13.
- Hypotheses tried: confirmed the query included an outer join to `ShcHearing` but its `select(...)` listed only four models, while response mapping unpacked five.
- Root cause: joined hearing rows were not part of the SQLAlchemy result tuple.
- Solution applied: add `ShcHearing` to the queue query's selected entities.
- Verification: pending targeted and full backend suites.
- Regression test: `backend/tests/test_phase6_shc.py` and existing `backend/tests/test_phase6_evc_report.py` SHC handoff assertion.
- Related: Phase 6.4 / FR-24.


### BUG-0046 — Seeded placeholder PDF has fewer pages than its synthetic field references
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / demo fixture and evidence preview.
- Status: Workaround (fixture limitation remains).
- Where it showed up: isolated Phase 5.11 browser review of seeded `fire-safety.pdf`, field `valid_to` (`source_page=2`).
- Expected: selecting the field shows its source page in the split review.
- Actual: the preview pane was blank in the in-app browser; the seeded placeholder PDF is generated as a one-page file while its synthetic field says page 2. That file has no bounding box either.
- Steps to reproduce: seed local demo data, sign in as scrutiny officer, select the fire safety `valid_to` evidence.
- Environment: isolated SQLite demo seeded with `app.services.seed`, Vite browser UI on 5174.
- Hypotheses tried: field source data says page 2 while `backend/app/api/documents.py::_placeholder_pdf` always creates a single page; screenshot confirmed blank viewer. No application data was edited outside the isolated test DB.
- Root cause: demo seed provenance page does not correspond to its one-page placeholder document.
- Solution applied: retain the explicit source page and no-box honesty behavior; add an “Open original PDF in a new tab” fallback. The fixture mismatch itself is not corrected in this task.
- Verification: preview pane and fallback link rendered in the isolated browser; page 2 could not be visually verified in the placeholder. Real uploaded PDFs with valid page/bbox provenance were not available for this smoke.
- Related: IMPL-0050; Phase 5 exit check remains open.
- Update (2026-10-27): documented with pushed Phase 5.11 commit `74b3ba6`; the seed/page mismatch remains a workaround limitation.

### BUG-0047 — Git staging was blocked by the default filesystem sandbox
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / repository tooling.
- Status: Workaround.
- Where it showed up: staging the completed Phase 6.2 reminder slice.
- Expected: `git add ...` creates the index lock and stages only the named Phase 6.2 files.
- Actual: `fatal: Unable to create '.../.git/index.lock': Operation not permitted`.
- Steps to reproduce: run the task-scoped `git add` command in the default sandbox.
- Environment: Codex workspace with repository `.git` read-only in the default sandbox profile.
- Hypotheses tried: no repository changes were staged; the error is before Git could write the index.
- Root cause: the default command sandbox allows repo working-tree writes but denies writes to `.git` metadata.
- Solution applied: retry the same task-scoped staging/commit/push with the approved elevated command pathway if allowed; otherwise leave the verified working-tree changes unstaged and report the restriction.
- Verification: pending.
- Related: IMPL-0051.
- Update (2026-10-27): the same task-scoped changes were staged, committed as `fd98ee1`, and pushed to `origin/master` using the elevated repository operation. No unrelated files were staged; the four pre-existing image files remain untracked.

### BUG-0051 — EVC report read route was missing from authorization matrix
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / test contract.
- Status: Fixed.
- Where it showed up: focused authorization matrix after introducing the report read route.
- Expected: discovered route permissions equal the explicit matrix.
- Actual: expected `application.read`/`case.read`; endpoint declares `case.read`/`document.read`.
- Steps to reproduce: `cd backend && ../.venv/bin/pytest -q tests/test_authz_matrix.py::test_matrix_lists_every_permission_gated_route`.
- Environment: repo virtual environment, SQLite tests.
- Hypotheses tried: none; discovery points to an outdated expected tuple.
- Root cause: matrix row used the shared `READ_ANY` alias even though report reads are gated by `CASE_READ` or `DOCUMENT_READ`.
- Solution applied: matrix row now asserts `CASE_READ`/`DOCUMENT_READ`, the endpoint's declared gates.
- Verification: Ruff clean; focused matrix/report/EVC suite **42 passed, 1 upstream warning**.
- Update (2026-10-27): first targeted run recorded the mismatch; corrected matrix and full focused suite passed.
- Regression test: `test_matrix_lists_every_permission_gated_route` and complete authz matrix.
- Related: Phase 6.3 / IMPL-0054.

### BUG-0050 — New Competent Authority role was missing from role seeding
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S3 / role initialization.
- Status: Fixed.
- Where it showed up: first focused Phase 6.3 API test run during database seeding.
- Expected: seeded role/permission matrix initializes with the new Competent Authority role.
- Actual: `KeyError: 'competent_authority'` in `services/seed.py::_ensure_access_model`.
- Steps to reproduce: `cd backend && ../.venv/bin/pytest -q tests/test_phase6_evc_report.py`.
- Environment: SQLite test database, repo virtual environment.
- Hypotheses tried: trace shows role permissions include the new role while the explicit role-creation tuple does not.
- Root cause: role seeding uses an allowlist tuple that was not updated alongside `ROLE_PERMISSIONS`.
- Solution applied: seed now creates roles from the canonical `ROLE_PERMISSIONS` mapping.
- Verification: Ruff clean; focused report/referral/authz/EVC suite **42 passed, 1 upstream warning**.
- Regression test: `test_assigned_expert_can_submit_report_and_flag_nonpenal_referral` seeds the complete role mapping and verifies scoped referral access.
- Update (2026-10-27): role initialization failure fixed and verified.
- Regression test: focused report/referral test and full backend suite.
- Related: Phase 6.3 / IMPL-0054.

### BUG-0049 — Phase 6.3 report API lint found import and name errors
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: first Ruff check after adding EVC report submission and fraud referral routes.
- Expected: touched backend files pass Ruff.
- Actual: Ruff reported I001 import ordering and F821 missing names `CASE_DECIDE`, `DOCUMENT_READ`, and `current_request_id`.
- Steps to reproduce: `cd backend && ../.venv/bin/ruff check app tests migrations`.
- Environment: repo virtual environment, Ruff from `backend/ruff.toml`.
- Hypotheses tried: none; static analysis identified the import/name defects.
- Root cause: new route code referenced existing permission/request-context names without importing them; added imports were not sorted.
- Solution applied: imported the required permission and request-id names; Ruff sorted all touched import blocks.
- Verification: full Ruff check clean; focused report/referral/authz/EVC suite **42 passed, 1 upstream warning**.
- Update (2026-10-27): import/name defects fixed and verified.
- Regression test: backend Ruff check plus focused report/referral tests.
- Related: Phase 6.3 / IMPL-0054.

### BUG-0048 — Phase 6.2 Ruff found EVC service import ordering
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: targeted lint after adding the EVC expert-assignment service.
- Expected: Ruff accepts the touched backend files.
- Actual: `I001 Import block is un-sorted or un-formatted` in `backend/app/api/evc.py`.
- Steps to reproduce: `cd backend && ../.venv/bin/ruff check app tests migrations`.
- Environment: repo virtual environment, Ruff from `backend/ruff.toml`.
- Hypotheses tried: none; Ruff directly identified import ordering.
- Root cause: new `evc_service` import was placed separately from sibling service imports.
- Solution applied: Ruff's import sorter grouped `evc_service` with sibling services.
- Verification: `make lint` clean; `make test` 787 passed; targeted suite 52 passed.
- Update: initial failure was logged immediately; correction and verification completed 2026-10-27.
- Regression test: full `make lint`.
- Related: Phase 6.2 / IMPL-0053.

### BUG-0045 — Isolated browser review origin was outside the configured CORS list
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / temporary local verification setup.
- Status: Workaround.
- Where it showed up: browser sign-in to the isolated UI on `http://localhost:5174` against the temporary API on port 8001.
- Expected: the temporary seeded account can sign in through the test UI.
- Actual: the API returned 400 to the browser's `OPTIONS /api/v1/auth/login` preflight; sign-in did not reach application logic.
- Steps to reproduce: run the temporary API with default CORS origins and open the UI on port 5174.
- Environment: isolated temporary SQLite API, Vite UI, local browser.
- Hypotheses tried: server log identifies `OPTIONS` and 400; no credentials or login data were rejected by the app.
- Root cause: default `SIH_CORS_ORIGINS` allows localhost:5173, not this separate verification port.
- Solution applied: restart only the temporary API with explicit `http://localhost:5174` CORS origin. No repository or existing server configuration changed.
- Verification: temporary API startup log confirmed preflight 400; after restart with `SIH_CORS_ORIGINS=["http://localhost:5174"]`, synthetic demo sign-in and case loading succeeded.
- Related: IMPL-0050.
- Update (2026-10-27): temporary CORS workaround and verification recorded in pushed commit `74b3ba6`; no persistent CORS setting changed.

### BUG-0044 — Local development server could not start on occupied API port
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / local environment.
- Status: Workaround.
- Where it showed up: `make dev` during Phase 5.11 UI review.
- Expected: the dev script starts API on port 8000 and frontend on 5173.
- Actual: script exited before startup because port 8000 is occupied by PID 41874.
- Steps to reproduce: run `make dev` while that process owns port 8000.
- Environment: macOS local workspace.
- Hypotheses tried: none; startup script reports the listener directly. The process was not stopped because it may be the user's existing app.
- Root cause: another process already listens on the API port.
- Solution applied: left the existing port 8000 process untouched. Started a separate test API on 8001 with isolated `/private/tmp/sih26262_phase5_ui.sqlite` and a test UI on 5174; synthetic browser review succeeded.
- Verification: existing process owns 8000; shell health check could not connect. Isolated UI sign-in and case view worked after CORS was configured; the broader current app was not restarted or altered.
- Related: IMPL-0050.
- Update (2026-10-27): isolated review workaround recorded in pushed commit `74b3ba6`; original port-8000 process remained untouched.

### BUG-0043 — Phase 5.10 test import ordering failed Ruff
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: required `make lint` after adding the Phase 5.10 fixture test.
- Expected: Ruff accepts the new test import block.
- Actual: Ruff reported `I001` in `backend/tests/test_phase5_site_move_fixtures.py`.
- Steps to reproduce: run `make lint`.
- Environment: repo virtualenv, Ruff configured by `backend/ruff.toml`.
- Hypotheses tried: none; Ruff identified the import block directly.
- Root cause: imports in the new regression test did not match repository ordering.
- Solution applied: format the import block with Ruff's import fixer; no product behavior changed.
- Verification: `make lint` clean; `make test` → **777 passed, 1 warning, 0 skipped**.
- Related: IMPL-0049.
- Update (2026-10-27): Ruff fix and verification recorded in pushed commit `5a69e2a`.

### BUG-0042 — System pytest auto-loaded an unrelated Anaconda plugin
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / local test environment.
- Status: Workaround.
- Where it showed up: first targeted Phase 5.10 invocation, `pytest -q tests/test_phase5_site_move_fixtures.py`, from `backend/`.
- Expected: pytest collects and runs the repository test.
- Actual: pytest failed before collection while importing the globally installed `napari` pytest plugin; Numba cache initialization raised `RuntimeError: cannot cache function ... no locator available`.
- Steps to reproduce: run bare system `pytest` in this environment with global setuptools pytest entrypoints enabled.
- Environment: macOS, system Anaconda Python 3.13, repo `backend/`.
- Hypotheses tried: no product code was loaded; traceback shows failure in global `napari`/`numba` plugin initialization.
- Root cause: command selected `/opt/anaconda3/bin/pytest` rather than the repository's documented `.venv` runner, causing unrelated global plugins to load.
- Solution applied: use `../.venv/bin/pytest` from `backend/` (or documented `make test`) to isolate repo dependencies; no dependency or plugin configuration changed.
- Verification: `../.venv/bin/pytest -q tests/test_phase5_site_move_fixtures.py` → **1 passed, 1 upstream warning**; full `make test` pending.
- Related: Phase 5.10 / IMPL-0049.
- Update (2026-10-27): repository virtualenv workaround and verification recorded in pushed commit `5a69e2a`.

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
| BUG-0051 | 2026-10-27 | S4 | test contract | EVC report read route was missing from authorization matrix | Fixed | IMPL-0054 |
| BUG-0050 | 2026-10-27 | S3 | role initialization | New Competent Authority role was missing from role seeding | Fixed | IMPL-0054 |
| BUG-0049 | 2026-10-27 | S4 | lint | Phase 6.3 report API lint found import and name errors | Fixed | IMPL-0054 |
| BUG-0048 | 2026-10-27 | S4 | lint | Phase 6.2 Ruff found EVC service import ordering | Fixed | IMPL-0053 |
| BUG-0047 | 2026-10-27 | S4 | repository tooling | Git staging blocked by default filesystem sandbox | Workaround | IMPL-0051 |
| BUG-0041 | 2026-10-27 | S4 | command | Local settings verification used a backend-relative Python path from repo root | Fixed | IMPL-0048 |
| BUG-0040 | 2026-10-27 | S4 | lint | New Phase 5.9 migration had unsorted imports on first Ruff run | Fixed | IMPL-0048 |
| BUG-0039 | 2026-10-27 | S4 | authz test harness | Phase 5.8 matrix probe lacked a valid request body, so Pydantic returned 422 before the scope check | Fixed | IMPL-0047 |
| BUG-0038 | 2026-10-27 | S4 | lint | Initial Phase 5.8 Ruff run found duplicated imports and a missing clock import | Fixed | IMPL-0047 |
| BUG-0037 | 2026-10-27 | S4 | test | Phase 5.7 policy contract test compared mapping keys instead of outcome labels | Fixed | IMPL-0046 |
| BUG-0036 | 2026-10-27 | S4 | test | Site jurisdiction test read field paths from the fixture instead of the site policy | Fixed | IMPL-0045 |
| BUG-0035 | 2026-10-27 | S4 | lint | Phase 5.6 Ruff check stopped on local service import ordering | Fixed | IMPL-0045 |
| BUG-0034 | 2026-10-27 | S4 | lint | Phase 5.5 first Ruff check found import ordering and an unused test import | Fixed | IMPL-0044 |
| BUG-0033 | 2026-10-27 | S4 | test harness / shared checkout | One combined `test_three_value` + `test_authz_matrix` run failed `test_matrix_lists_every_permission_gated_route`; never reproduced in six later runs incl. full suites | Workaround | IMPL-0043 |
| BUG-0032 | 2026-10-27 | S4 | test harness | Update: the four Phase 5.4 failures first seen in BUG-0023 are gone; final suite is green | Fixed | IMPL-0041 |
| BUG-0031 | 2026-10-27 | S4 | GitHub tooling | Default sandbox could not reach GitHub API to verify requested repo access; escalated read confirmed ADMIN | Fixed | IMPL-0041 |
| BUG-0030 | 2026-10-27 | S4 | patch tooling | One Phase 8 patch did not apply because its context did not match current source; no changes from the failed patch | Fixed | IMPL-0041 |
| BUG-0029 | 2026-10-27 | S4 | test harness | Targeted pytest command named a nonexistent node under `test_evidence_flow.py`; corrected to `test_case_assignment.py` | Fixed | IMPL-0041 |
| BUG-0028 | 2026-10-27 | S4 | lint | New Phase 8 test imports failed Ruff `I001`; `ruff --fix` corrected ordering | Fixed | IMPL-0041 |
| BUG-0027 | 2026-10-27 | S4 | tooling | Ruff command used a path relative to `backend/` while run from repository root | Fixed | IMPL-0041 |
| BUG-0026 | 2026-10-27 | S4 | audit | First Phase 8 lint found `application` referenced but not bound in the content-download handler | Fixed | IMPL-0041 |
| BUG-0025 | 2026-10-27 | S4 | audit | Repository script inspection used the wrong path; `scripts/verify_isolation.py` does not exist at root | Fixed | IMPL-0041 |
| BUG-0024 | 2026-10-27 | S4 | git tooling | `git fetch origin` could not write `.git/FETCH_HEAD` in the restricted sandbox; fetch succeeded with approved escalation | Fixed | IMPL-0041 |
| BUG-0023 | 2026-10-27 | S3 | test harness / Phase 5.4 in-progress | Baseline `make test` has four failures in uncommitted three-value work (missing spec key and missing claim route) | Open | IMPL-0041 |
| BUG-0022 | 2026-10-27 | S4 | test harness | Phase 5.3 API test: field lookup not scoped to the uploaded document hit seeded `lessee_name` rows (`MultipleResultsFound`) | Fixed | IMPL-0040 |
| BUG-0021 | 2026-10-27 | S4 | test harness | Phase 5.3 API test read upload warnings from the wrong key — they live at `body["extraction"]["warnings"]` | Fixed | IMPL-0040 |
| BUG-0020 | 2026-10-27 | S3 | document grounding | Phase 5.3: `matching.case_sensitive` polarity inverted at the read site — case differences failed the ground check (`not on page: Sub`) | Fixed | IMPL-0040 |
| BUG-0019 | 2026-10-27 | S4 | migrations tooling | `make lint` failed after autogenerating the 5.2 migration: Alembic's template imports fail ruff `I001` — `ruff --fix` on the file | Fixed | IMPL-0039 |
| BUG-0018 | 2026-10-27 | S4 | classification note | First run of the 5.1 suite: a classification resting on the file name lost that caveat whenever the declared type also mismatched — the note now composes both caveats | Fixed | IMPL-0038 |
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

### BUG-0039 — Phase 5.8 authorization-matrix probe sent no disposition body
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / test harness and authorization matrix.
- Status: Fixed.
- Where it showed up: `pytest -q tests/test_finding_dispositions.py tests/test_authz_matrix.py tests/test_api.py`, out-of-scope matrix cases for regional and scrutiny roles.
- Expected: out-of-scope case requests return 404 before revealing the case.
- Actual: the new POST probe returned 422 because no valid Pydantic request body was sent; body validation ran before the scoped application lookup.
- Exact error output (trimmed): `POST .../compliance/findings/matrix-missing-finding_id/disposition ... got 422, expected 404`.
- Steps to reproduce: add a permission-gated POST to `MATRIX`, omit its endpoint body from `JSON_BODIES`, run the scoped matrix test.
- Environment: macOS, Python 3.13, SQLite test database, FastAPI TestClient.
- Hypotheses tried: initially suspected the scope dependency; response was from body validation, and the same probe passed once given a valid body.
- Root cause: shared matrix request builder had no representative payload for the new POST.
- Solution applied: added a valid `confirmed` disposition body to the matrix fixture, so authz/scope behavior is reached. Regression coverage is the existing out-of-scope matrix test.
- Verification: targeted matrix + endpoint tests **38 passed**; final `make test` **771 passed, 0 skipped**.
- Related: IMPL-0047; BUG-0038.

### BUG-0038 — Initial Phase 5.8 lint found import defects
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: initial `cd backend && ../.venv/bin/ruff check app tests migrations`.
- Expected: newly edited API, migration, and test imports satisfy Ruff.
- Actual: `I001` import ordering in the new API/migration/test and duplicate imports plus `F821 Undefined name get_clock` in the new endpoint.
- Exact error output (trimmed): `F821 Undefined name get_clock` and `I001 Import block is un-sorted or un-formatted`.
- Steps to reproduce: run Ruff after the first implementation edits.
- Environment: macOS, Python 3.13, Ruff 0.14.4.
- Hypotheses tried: none; diagnostics directly identified the import block and missing clock import.
- Root cause: duplicated authorization import, missing clock import, and generated/import blocks not in repository order.
- Solution applied: consolidated imports, added `get_clock`, and ran Ruff autofix for ordering. Regression guard: full Ruff check.
- Verification: `make lint` clean; final `make test` **771 passed, 0 skipped**.
- Related: IMPL-0047.

### BUG-0041 — Config verification command used a path relative to the wrong working directory
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / command.
- Status: Fixed.
- Where it showed up: local `.env` settings verification command invoked from the repository root.
- Expected: Python imports the backend settings and confirms the key is configured while external calls remain disabled.
- Actual: `ModuleNotFoundError: No module named 'app'` because the command used `../.venv/bin/python` and ran outside `backend/`.
- Exact error output (trimmed): `ModuleNotFoundError: No module named 'app'`.
- Steps to reproduce: run the backend-module import from repo root without adding `backend` to `PYTHONPATH`.
- Environment: macOS, Python 3.13.
- Hypotheses tried: path/working-directory mismatch; no application defect was indicated.
- Root cause: relative executable path and module import root were inconsistent.
- Solution applied: reran from `backend/` using `../.venv/bin/python`; asserted the key loads and `openrouter_enabled` is false without printing the key.
- Verification: output confirmed the local key loaded and external calls remain disabled; `.env` mode is 600 and Git ignores it.
- Related: IMPL-0048.

### BUG-0040 — Ruff import ordering in the new external-call migration
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / pending commit.
- Severity / Area: S4 / lint.
- Status: Fixed.
- Where it showed up: initial `cd backend && ../.venv/bin/ruff check app tests migrations`.
- Expected: the additive migration passes repository Ruff rules.
- Actual: Ruff `I001` on the Alembic migration's `sqlalchemy` and `alembic` imports.
- Exact error output (trimmed): `I001 Import block is un-sorted or un-formatted`.
- Steps to reproduce: run Ruff before formatting the new migration.
- Environment: macOS, Python 3.13, Ruff 0.14.4.
- Hypotheses tried: none; direct import-order diagnostic.
- Root cause: Alembic template import order differed from repository Ruff configuration.
- Solution applied: `ruff check --fix migrations/versions/0017_external_call_logs.py`.
- Verification: backend Ruff clean; full `make lint` clean; final `make test` passed **776 tests**.
- Related: IMPL-0048.

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

### BUG-0037 — Phase 5.7 policy contract test compared the wrong side of the mapping
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / working tree for Phase 5.7
- Severity / Area: S4 / test
- Status: Investigating
- Where it showed up: targeted `test_precheck_status.py` run.
- Expected behaviour: policy contract test pins the PRD's three exact outcome labels.
- Actual behaviour: the test compared outcome-map keys (`passed`, `review_required`, `deficiency_candidate`) with their label values (`PRE-CHECK PASSED`, etc.).
- Exact error output (trimmed): assertion mismatch in `test_policy_labels_are_exact_prd_outcomes_and_never_block`.
- Steps to reproduce: `cd backend && ../.venv/bin/python -m pytest tests/test_precheck_status.py -q`.
- Environment: macOS, Python 3.13, SQLite test setup.
- Hypotheses tried: none; the assertion inspected keys rather than `policy["outcomes"].values()`.
- Root cause: test expected values to be dictionary keys.
- Solution applied: pending.
- Verification: pending.
- Side effects / follow-ups / related decisions / linked IMPL: none; IMPL-0046.
- Regression test: failing contract test itself after correction.
- Update (2026-10-27): corrected the assertion to inspect `policy["outcomes"].values()`; targeted tests → **17 passed, 1 warning**; full suite → **769 passed, 1 warning, 0 skipped**.
- Update history: opened immediately after the failed targeted run; fixed and verified in the update above.

### BUG-0036 — Site jurisdiction test read field paths from the wrong config
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / working tree for Phase 5.6
- Severity / Area: S4 / test
- Status: Investigating
- Where it showed up: targeted `test_site_checks.py` run.
- Expected behaviour: synthetic fixture lookup test builds its input using configured paths.
- Actual behaviour: `KeyError: 'university_path'` because the path keys belong to `site_check_policy.json`, while the test read `jurisdiction.json`.
- Exact error output (trimmed): `university_field = policy["university_path"]` → `KeyError: 'university_path'`.
- Steps to reproduce: run `cd backend && ../.venv/bin/python -m pytest tests/test_site_checks.py -q`.
- Environment: macOS, Python 3.13, SQLite test setup.
- Hypotheses tried: none; the failing test read the fixture schema directly.
- Root cause: test used `jurisdiction_config()` for input field paths, but the fields are in `site_check_policy()["site_02"]`.
- Solution applied: pending.
- Verification: pending.
- Side effects / follow-ups / related decisions / linked IMPL: none; IMPL-0045.
- Regression test: the failing test itself will verify lookup against policy-provided paths after correction.
- Update (2026-10-27): fixed by reading field paths from `site_check_policy()["site_02"]` and fixture entries from `jurisdiction_config()`; targeted test file passes as part of **7 passed** run.
- Update history: opened immediately after the failed test run. First correction moved path lookup to site policy; the next run exposed that fixture entries still come from the separate jurisdiction policy (`KeyError: 'entries'`). Final correction and verification are recorded above.

### BUG-0035 — Phase 5.6 Ruff check stopped on import ordering
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / working tree for Phase 5.6
- Severity / Area: S4 / lint
- Status: Investigating
- Where it showed up: `cd backend && ../.venv/bin/python -m ruff check app tests migrations scripts && ../.venv/bin/python -m pytest tests/test_site_checks.py tests/test_api.py::test_compliance_get_returns_the_latest_batch -q`
- Expected behaviour: Ruff accepts imports added for the SITE-01/02 service.
- Actual behaviour: command stopped before pytest; Ruff reported `I001` in `app/services/compliance_service.py`.
- Exact error output (trimmed): `I001 Import block is un-sorted or un-formatted`.
- Steps to reproduce: run the command above after adding the `site_checks` service import.
- Environment: macOS, Python 3.13, repository `.venv`.
- Hypotheses tried: none; Ruff points to import ordering.
- Root cause: import was inserted after a non-blank local import block instead of sorted with the sibling modules.
- Solution applied: pending.
- Verification: targeted tests did not run in the failed `&&` chain; pending.
- Side effects / follow-ups / related decisions / linked IMPL: none; IMPL-0045.
- Regression test: lint command itself is the check; no product behavior failure occurred.
- Update (2026-10-27): Ruff's import fixer sorted the imports; `ruff check app tests migrations scripts` passes and final `make lint && make test` reports **764 passed, 1 warning, 0 skipped**.
- Update history: opened immediately after the failed command; fix and verification recorded above.

### BUG-0034 — Phase 5.5 first Ruff check found import-only issues
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / working tree for Phase 5.5
- Severity / Area: S4 / lint
- Status: Fixed
- Where it showed up: `cd backend && ../.venv/bin/python -m ruff check app tests migrations scripts`
- Expected behaviour: Ruff accepts the new Phase 5.5 service and test imports.
- Actual behaviour: Ruff reported `I001` for import ordering in `app/services/compliance_service.py` and `F401` for an unused `copy.deepcopy` import in `tests/test_evidence_crosschecks.py`.
- Exact error output (trimmed): `I001 Import block is un-sorted or un-formatted`; `F401 copy.deepcopy imported but unused`.
- Steps to reproduce: add the Phase 5.5 service import and test file, then run the command above.
- Environment: macOS, Python 3.13, repository `.venv`.
- Hypotheses tried: none; Ruff identified both exact source lines.
- Root cause: import was placed after the local evidence-service import rather than in Ruff's sorted order; test drafting left one unused import.
- Solution applied: ran Ruff's import fixer and removed the unused symbol; no production behavior changed.
- Verification at initial entry: targeted Phase 5.5 and three-value tests → 21 passed; Ruff rerun pending at log time.
- Side effects / follow-ups / related decisions / linked IMPL: none; IMPL-0044.
- Regression test: no behavior regression was involved; lint itself is the verification gate.
- Update (2026-10-27): Ruff import fixer applied. `ruff check app tests migrations scripts` → All checks passed; final `make lint && make test` → **758 passed, 1 warning, 0 skipped**. Root cause and fix above; no behavior regression was involved.
- Update history: 2026-10-27 — entry opened immediately after the failed check; fixed and verified in the update above.

### BUG-0033 — matrix coverage test failed once in a combined run, never again
- Date found / found by / branch / commit: 2026-10-27 / MiMo (OpenCode agent) / master / uncommitted Phase 5.4 work (second agent editing the same checkout)
- Severity / Area: S4 / test harness
- Status: Workaround
- Where it showed up: first combined `pytest tests/test_three_value.py tests/test_authz_matrix.py` run while the 15 new three-value tests were already green.
- Expected behaviour: `test_matrix_lists_every_permission_gated_route` passes (all 36 tests in that run).
- Actual behaviour: `1 failed, 35 passed` — only `test_authz_matrix.py::test_matrix_lists_every_permission_gated_route` failed; the failure output was not captured (my filter looked for `^E ` lines in a later, passing run).
- Exact error output: not captured (regression: always capture the failure body before re-running).
- Steps to reproduce: never reproduced — the same command passed 6 consecutive times afterwards (once alone, 5× combined), plus full-suite greens at 742 and 753.
- Environment: macOS, repo `/Users/reyyishreyas/Desktop/sih26262`, pytest 9.1.1, no random-order plugin (order deterministic).
- Hypotheses tried: (1) stale bytecode after `ruff --fix` rewrote `documents.py` in the same command chain — unlikely, Python recompiles on mtime; (2) my two test edits between runs — they touched only `test_three_value.py`, not discovery; (3) **concurrent second agent (Codex) editing the shared checkout during the run** — its files show mtimes inside my run windows (`audit.py` 19:45, `test_phase8_audit.py` 19:52); leading hypothesis, unproven; (4) test-order dependence — ruled out, no randomisation plugin and argument order fixed.
- Root cause: not established. Most plausible: a concurrent agent's mid-run edit of the shared tree transiently affected route discovery.
- Solution applied: re-run (workaround); suite stable green since. Recorded honestly as unresolved.
- Verification: 6× green runs of the same pair of files; `make test` → `742 passed` (pre-merge) and `753 passed` (merged tree `72c7ed6`).
- Side effects / follow-ups / related decisions (DEC-XXXX) / related IMPL-XXXX: none; linked IMPL-0043. If it recurs under single-agent conditions, reopen with the captured traceback.
- Update history (date — change in status or approach): —

### BUG-0032 — Update: temporary Phase 5.4 failures are no longer present
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / shared worktree after concurrent changes
- Severity / Area: S4 / test harness
- Status: Fixed (update to BUG-0023)
- Where it showed up: final `make lint && make test` during IMPL-0041.
- Expected behaviour: the suite should pass after the in-progress Phase 5.4 work is completed.
- Actual behaviour: `742 passed, 1 warning in 70.55s`; the four earlier Phase 5.4 failures from BUG-0023 were absent.
- Exact error output: none on the final run.
- Steps to reproduce: `make lint && make test` in the current shared worktree.
- Environment: macOS, Python 3.13.9, SQLite, fixed test clock.
- Hypotheses tried: no product diagnosis; the shared Phase 5.4 files changed after BUG-0023 was observed.
- Root cause: the incomplete concurrent Phase 5.4 implementation was completed in the shared worktree; this agent did not change its three-value API/model/service files.
- Solution applied: none in Phase 8; the status is recorded so BUG-0023 remains as the original observation.
- Verification: `make lint && make test` → **742 passed, 1 warning, 0 skipped**.
- Side effects / follow-ups / related IMPL: BUG-0023 remains historical; IMPL-0041.
- Update history: 2026-10-27 — final full-suite run passed.

### BUG-0031 — Default sandbox blocked GitHub API access verification
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / 2ec5e1a
- Severity / Area: S4 / GitHub tooling
- Status: Fixed
- Where it showed up: `gh repo view reyyishreyas/sih26262 --json nameWithOwner,viewerPermission`.
- Expected behaviour: confirm repository identity and authenticated push permission before publishing.
- Actual behaviour: `error connecting to api.github.com; check your internet connection or https://githubstatus.com`.
- Exact error output: `error connecting to api.github.com`.
- Steps to reproduce: run the command in the default sandbox.
- Environment: macOS workspace with network access restricted.
- Hypotheses tried: sandbox network denial was suspected; approved escalation returned repository identity and viewer permission.
- Root cause: the default sandbox could not reach the GitHub API.
- Solution applied: reran the read-only repository check with approved escalation.
- Verification: response `{"nameWithOwner":"reyyishreyas/sih26262","viewerPermission":"ADMIN"}`.
- Side effects / follow-ups / related IMPL: no repository change; IMPL-0041.
- Update history: —

### BUG-0030 — A Phase 8 patch context did not match the current source
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / patch tooling
- Status: Fixed
- Where it showed up: a patch intended to wrap the classifier/grounding block in a failure-audit handler.
- Expected behaviour: apply the exact source hunk.
- Actual behaviour: patch tool returned `Failed to find expected lines`; it made no partial change for that hunk.
- Exact error output: `Failed to find expected lines`.
- Steps to reproduce: apply the stale context around the classifier/grounding block after the extraction-audit patch.
- Environment: local workspace; `backend/app/api/documents.py` had already changed.
- Hypotheses tried: source-context mismatch; inspected the current lines and reapplied against the current content.
- Root cause: the source hunk was stale after an earlier patch moved the extraction/classification lines.
- Solution applied: refreshed the source context and applied the change; subsequent lint and tests passed.
- Verification: `make lint` passed; `tests/test_phase8_audit.py::test_extraction_failure_is_recorded_without_storing_the_upload` passed.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0029 — A targeted pytest node name pointed to the wrong file
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / test harness
- Status: Fixed
- Where it showed up: an attempted targeted pytest invocation.
- Expected behaviour: select the regression test covering submitted-case assignment.
- Actual behaviour: pytest reported `ERROR: not found` for `test_evidence_flow.py::test_documents_uploaded_after_submitting_are_readable_by_the_reviewer`.
- Exact error output: `ERROR: not found: .../tests/test_evidence_flow.py::test_documents_uploaded_after_submitting_are_readable_by_the_reviewer`.
- Steps to reproduce: use that node path in the targeted pytest command.
- Environment: macOS, Python 3.13.9, pytest.
- Hypotheses tried: searched test files; the named function is in `test_case_assignment.py`.
- Root cause: used the wrong file name for a test node.
- Solution applied: corrected selector to `test_case_assignment.py::test_submitting_hands_the_case_to_the_reviewer_queue`.
- Verification: corrected targeted command → **33 passed, 1 warning**.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0028 — Ruff import order failed on a new audit test
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / lint
- Status: Fixed
- Where it showed up: first `make lint` after adding `test_phase8_audit.py`.
- Expected behaviour: lint should pass.
- Actual behaviour: Ruff reported `I001 Import block is un-sorted or un-formatted`.
- Exact error output: `I001 [*] Import block is un-sorted or un-formatted`.
- Steps to reproduce: run `make lint` before sorting the new file's import block.
- Environment: macOS, Python 3.13.9, repo Ruff config.
- Hypotheses tried: none; Ruff supplied a safe import-sort fix.
- Root cause: imports in the new test file were grouped in the wrong order.
- Solution applied: `./.venv/bin/ruff check --fix backend/tests/test_phase8_audit.py`.
- Verification: `make lint` → **All checks passed**.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0027 — Ruff executable path was relative to the wrong working directory
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / tooling
- Status: Fixed
- Where it showed up: a Ruff fix command run from the repository root.
- Expected behaviour: invoke the repo's virtualenv Ruff executable.
- Actual behaviour: shell returned `zsh: no such file or directory: ../.venv/bin/ruff`.
- Exact error output: `zsh: no such file or directory: ../.venv/bin/ruff`.
- Steps to reproduce: run `../.venv/bin/ruff` from the repository root.
- Environment: macOS, zsh, repository root.
- Hypotheses tried: path was intended for `backend/`; root-relative executable is `./.venv/bin/ruff`.
- Root cause: relative path assumed a different current directory.
- Solution applied: reran `./.venv/bin/ruff check --fix backend/tests/test_phase8_audit.py`.
- Verification: `make lint` → **All checks passed**.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0026 — First audit-download lint found an unbound application variable
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / audit
- Status: Fixed
- Where it showed up: first `make lint` after adding `document.accessed` metadata.
- Expected behaviour: the content-download handler should pass lint and audit the authorized application id.
- Actual behaviour: Ruff reported `F821 Undefined name application` at the new event's `application.id` reference.
- Exact error output: `F821 Undefined name application`.
- Steps to reproduce: run `make lint` against the initial audit-download edit.
- Environment: macOS, Python 3.13.9.
- Hypotheses tried: the handler already called `require_application`, but discarded its return value.
- Root cause: the new audit event used the validated application object without assigning the result.
- Solution applied: bind `application = require_application(...)` before loading the document.
- Verification: `make lint` → **All checks passed**; authorized and out-of-scope document-read tests pass.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0025 — verification script was inspected at the wrong repository path
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / uncommitted Phase 8 work
- Severity / Area: S4 / repository inspection
- Status: Fixed
- Where it showed up: a read-only `sed` command used `scripts/verify_isolation.py` at repository root.
- Expected behaviour: read the existing script.
- Actual behaviour: `sed: can't read scripts/verify_isolation.py: No such file or directory`.
- Exact error output: `No such file or directory`.
- Steps to reproduce: `sed -n '1,150p' scripts/verify_isolation.py`.
- Environment: macOS, repo root `/Users/reyyishreyas/Desktop/sih26262`.
- Hypotheses tried: the command had the wrong path; `rg --files` found the existing file at `backend/scripts/verify_isolation.py`.
- Root cause: repository scripts are under `backend/scripts/`, contrary to the path used in that inspection command.
- Solution applied: corrected the inspection path; no product changes.
- Verification: `rg --files | rg 'verify_isolation\\.py$'` → `backend/scripts/verify_isolation.py`.
- Side effects / follow-ups / related IMPL: none; IMPL-0041.
- Update history: —

### BUG-0024 — fetch needed write access to Git metadata
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / 2ec5e1a
- Severity / Area: S4 / git tooling
- Status: Fixed
- Where it showed up: `git fetch origin`.
- Expected behaviour: update remote-tracking refs and `FETCH_HEAD`.
- Actual behaviour: sandbox denied the `.git/FETCH_HEAD` write with `error: cannot open '.git/FETCH_HEAD': Operation not permitted`.
- Exact error output: `error: cannot open '.git/FETCH_HEAD': Operation not permitted`.
- Steps to reproduce: run `git fetch origin` in the restricted workspace.
- Environment: macOS, workspace sandbox with `.git` readable but not writable.
- Hypotheses tried: none; the error names the denied metadata file.
- Root cause: fetching requires writing Git metadata outside the writable sandbox paths.
- Solution applied: reran `git fetch origin` with the approved escalation; fetch completed and updated `origin/feat/next-implementation`.
- Verification: `git fetch origin` → completed; `git rev-list --left-right --count HEAD...origin/master` → `0 0`.
- Side effects / follow-ups / related IMPL: no worktree files changed; IMPL-0041.
- Update history: —

### BUG-0023 — baseline suite exposed incomplete uncommitted Phase 5.4 work
- Date found / found by / branch / commit: 2026-10-27 / Codex / master / 2ec5e1a plus local uncommitted work
- Severity / Area: S3 / test harness and three-value feature
- Status: Open
- Where it showed up: `make lint && make test` before Phase 8 edits.
- Expected behaviour: the existing checkout passes its baseline suite.
- Actual behaviour: lint passed; pytest reported **4 failed, 728 passed, 1 warning**. Failures were `test_the_config_is_pinned_to_the_prd_and_to_the_spec_rule` (`KeyError: 'rules'`) and three Phase 5.4 claim API tests (HTTP 404 for the not-yet-registered claim route).
- Exact error output (trimmed): `KeyError: 'rules'`; `POST .../fields/{field_id}/claim` returned `404 Not Found`.
- Steps to reproduce: `make lint && make test` with the existing local, uncommitted Phase 5.4 files.
- Environment: macOS, Python 3.13.9, SQLite test database, fixed clock.
- Hypotheses tried: no product hypothesis tested; failures are in files already present before Phase 8 work.
- Root cause: the in-progress Phase 5.4 test expects a top-level `rules` key absent from the actual `md/rules.json` schema, and the expected claim endpoint is not yet wired into the API.
- Solution applied: none in this Phase 8 task; left Phase 5.4 files untouched as requested.
- Verification: failed baseline reproduced once; Phase 8 targeted checks will be reported separately. Regression test: the existing failing tests are in untracked `backend/tests/test_three_value.py`.
- Side effects / follow-ups / related IMPL: full-suite green status remains blocked pending the owner of the in-progress Phase 5.4 change; IMPL-0041.
- Update history: —
<!-- add entries below this line -->

### BUG-0020 — first run of the Phase 5.3 suite: `case_sensitive` flag was inverted, so case differences failed the ground check
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first run of `tests/test_fuzzy_grounding.py` after implementing Phase 5.3
- Branch / commit: master (work uncommitted at time of fix; baseline `72163cd`)
- Severity / Area: **S3** (wrong `REVIEW_REQUIRED` on values that are on the page — over-flagging to a human, never a false "grounded", so the failure direction was conservative) / document grounding
- Status: **Fixed**
- Where it showed up: `pytest tests/test_fuzzy_grounding.py -q` → `2 failed, 11 passed`:
  ```
  FAILED tests/test_fuzzy_grounding.py::test_matching_ignores_case_punctuation_and_spacing
  E   AssertionError: {'grounded': False, 'status': 'REVIEW_REQUIRED',
      'similarity': 0.8042, 'matched': 2, 'tokens': 3,
      'reason': 'not on page: Sub'}
  ```
- Expected behaviour: value `"  Sub-Registrar of Records, "` is grounded against page `"Issuing Authority: sub registrar of records"` — the config sets `case_sensitive: false`, so the match ignores case.
- Actual behaviour: `grounded: False` — the value's tokens kept their case (`Sub`, `Registrar`, `Records`), so `Sub` found no exact page word; the two long tokens were accidentally rescued by the fuzzy leg (`Registrar`/`registrar` = 0.889, `Records`/`records` = 0.857 ≥ 0.85) but the 3-char `Sub` only scores 0.667 against `sub` and stayed missing.
- Environment: macOS, suite via `../.venv/bin/python -m pytest`.
- Hypotheses tried: (1) tokenisation bug? — no: `_normalise(..., case_sensitive=False)` printed `sub registrar of records` correctly when called directly; (2) threshold too strict for short tokens? — plausible but secondary: the two exact-equivalent tokens should have matched outright; (3) **root cause** — in `ground()` I wrote `case_sensitive = not matching.get("case_sensitive", False)`: the config key `case_sensitive: false` already means "ignore case", and `not false` = `True` meant "preserve case", so `casefold()` never ran. The flag's polarity was inverted at the read site.
- Root cause: inverted boolean interpretation of `matching.case_sensitive` when constructing the normaliser.
- Solution applied: pass the flag through unchanged — `case_sensitive = bool(matching.get("case_sensitive", False))` (True ⇒ preserve case, False ⇒ casefold). Why this way: the config's key name already matches the parameter's meaning, so no negation belongs in the code.
- Verification: `pytest tests/test_fuzzy_grounding.py -q` → the failing test passes; full file **13 passed**; `make lint` clean; `make test` → **717 passed**.
- Regression test: `test_matching_ignores_case_punctuation_and_spacing` (fails on the old polarity, passes now); also covered indirectly by every exact-match test, which would break if casefold were dropped.
- Related: IMPL-0040. Second failure in the same run was test-side — logged as BUG-0021.

### BUG-0021 — first run of the Phase 5.3 suite: the API test read upload warnings from the wrong response key
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), same run as BUG-0020
- Branch / commit: master (work uncommitted; baseline `72163cd`)
- Severity / Area: **S4** (test-side; product behaviour was correct) / test harness
- Status: **Fixed**
- Where it showed up: `test_upload_stores_grounding_and_warns_without_blocking_or_mutating` → `assert any("lessee_name" in str(w) for w in warnings)` failed with `AssertionError: []` — `warnings` came from `body.get("warnings") or body["document"].get("warnings")`, both absent, so the fallback produced `[]`.
- Expected behaviour: the grounding warning is read from where the 201 actually puts extraction warnings.
- Actual behaviour: the 201 body nests them at `body["extraction"]["warnings"]` — the exact path `test_doc_classifier.py` (5.1, lines 265/283) already reads; the warning itself was present and correct.
- Environment: macOS, FastAPI TestClient.
- Hypotheses tried: (1) grounding warning not produced? — no, the field assertions above it passed (`grounding == "REVIEW_REQUIRED"`); (2) **root cause** — I guessed the response shape instead of reusing the existing test's accessor.
- Root cause: test authored against an assumed response key rather than the documented one.
- Solution applied: read `body["extraction"]["warnings"]`, matching the 5.1 test.
- Verification: the assertion passes; suite **13 passed**; full run **717 passed**.
- Regression test: the same assertion in the same test, now against the real shape.
- Related: IMPL-0040, BUG-0018 (same family: compose/read warnings through the existing channel).

### BUG-0022 — re-run of the Phase 5.3 API test: field lookup was not scoped to the uploaded document and hit seeded rows
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), run after fixing BUG-0020/0021
- Branch / commit: master (work uncommitted; baseline `72163cd`)
- Severity / Area: **S4** (test-side) / test harness
- Status: **Fixed**
- Where it showed up: `pytest tests/test_fuzzy_grounding.py -q` → `1 failed, 12 passed`:
  ```
  E   sqlalchemy.exc.MultipleResultsFound:
      Multiple rows were found when exactly one was required
  ```
  at `db.scalars(select(ExtractedField).where(ExtractedField.field_name == "lessee_name")).one()`.
- Expected behaviour: exactly one row — the one just uploaded.
- Actual behaviour: the demo seed also creates `lessee_name` fields (seeded lease evidence), so the unscoped `WHERE field_name = ...` matched ≥2 rows.
- Environment: macOS, seeded test DB (`conftest.database` drops/creates/seeds per test).
- Hypotheses tried: (1) duplicate rows created by the upload? — no, the unique constraint `(document_id, document_version, field_name)` forbids that; (2) **root cause** — forgot the demo data already contains lease fields with the same field names (seeded evidence), so a field-name-only lookup is ambiguous by design.
- Root cause: query keyed on a non-unique natural name in a seeded database.
- Solution applied: scope the lookup to the uploaded document — `where(document_id == body["document"]["id"], field_name == "lessee_name")`.
- Verification: `.one()` resolves; suite **13 passed**; full run **717 passed**.
- Regression test: the same test now proves both that the new row exists on this document and that verification leaves its grounding untouched.
- Related: IMPL-0040.

### BUG-0019 — `make lint` failed after generating the 5.2 migration: unsorted imports in the Alembic file
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), `make lint` gate after `alembic revision --autogenerate` for Phase 5.2
- Branch / commit: master (work uncommitted at time of fix; baseline `4398f07`)
- Severity / Area: **S4** (lint only; no test failed, no behaviour involved) / migrations tooling
- Status: **Fixed**
- Where it showed up: `make lint` → exit 1:
  ```
  I001 [*] Import block is un-sorted or un-formatted
    --> migrations/versions/f7e6eed3fa19_extracted_field_provenance_bbox_engine_.py:16:1
     |
  16 | from __future__ import annotations
  17 |
  18 | from alembic import op
  19 | import sqlalchemy as sa
  ```
- Expected behaviour: `make lint` green (ruff checks `migrations/`).
- Actual behaviour: Alembic's template emits `from alembic import op` before `import sqlalchemy as sa`, which ruff's `I` rule sorts the other way.
- Environment: macOS, repo ruff config `backend/ruff.toml` (`select` includes `"I"`).
- Hypotheses tried: (1) my migration edits broke it? — no: the failure is in the untouched autogenerate header (`revision`/`down_revision` block); (2) an older generated migration has the same shape and passes? — prior migrations were written/adjusted by hand and are sorted; autogenerate's raw output never met the `I` rule before (this is the first migration generated in this session — earlier ones were pre-existing); (3) **root cause** — `alembic revision --autogenerate` writes imports in its own template order, not ruff's isort order.
- Root cause: tool template vs lint config mismatch, not a logic error.
- Solution applied: `ruff check --fix` on just that file (1 fix — reorders the two imports). No hand-rewriting, no config change; the `--fix` output is the canonical isort order.
- Verification: `ruff check app tests migrations scripts` → "All checks passed!"; `make lint` → green; full suite unaffected (**704 passed**).
- Side effects / follow-ups: none. Note for future migrations: run `ruff --fix` (or `make lint`) immediately after `alembic revision --autogenerate` — the generated imports will fail `I001`. Related IMPL-0039.
- Update history: 2026-10-27 — found and fixed in the same session.

### BUG-0018 — first run of the Phase 5.1 classifier suite: filename-only note was swallowed by the mismatch note
- Date found / found by: 2026-10-27 / MiMo (OpenCode agent, MiMo-V2.6), first `pytest tests/test_doc_classifier.py` after writing the suite
- Branch / commit: master (work uncommitted at time of fix; baseline `e0b9dd9`)
- Severity / Area: **S4** (display copy on an advisory response; fields and review flags all correct) / classification note
- Status: **Fixed**
- Where it showed up: `pytest tests/test_doc_classifier.py -q` → 1 failed, 18 passed:
  ```
  E       assert 'file name only' in "Uploaded as 'other' but the content reads more
  like: Affidavit. The recorded type is unchanged — a checker will confirm which it is."
  ```
  (in `test_text_beats_the_file_name_but_still_needs_review` — text matched nothing, the *file name* suggested affidavit, declared `other`)
- Expected behaviour: the note should say the classification rests on the file name only, because that is the weaker half of the evidence a checker needs to see.
- Actual behaviour: the note carried only the mismatch sentence — my `note = mismatch_note or "Classified from the file name only…"` gave the mismatch precedence and dropped the filename caveat whenever both applied.
- Environment: macOS, Python 3.13, SQLite.
- Hypotheses tried: (1) wrong needs_review/agrees values? — no, `agrees_with_declared: false`, `evidence: "file_name"`, `needs_review: true` were all correct; only the composed `note` string was lossy; (2) should the test expect the mismatch note instead? — no: an officer shown "reads more like Affidavit" without knowing the evidence was just the filename would over-trust the prediction.
- Root cause: the note was written as an either/or when the two caveats are independent and can both be true.
- Solution applied: `backend/app/services/doc_classifier.py` — for a `classified` result the note now composes every applicable caveat (filename-only sentence, then the mismatch sentence, in that order); the no_text/unclassified/ambiguous branches are unchanged. Fields (`evidence`, `agrees_with_declared`, `needs_review`) were already right and are untouched.
- Verification: `pytest tests/test_doc_classifier.py -q` → **19 passed** (see IMPL-0038).
- Side effects / follow-ups: none — display copy only, advisory response. Related IMPL-0038.
- Update history: 2026-10-27 — found and fixed in the same session.

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
- Update history: 2026-10-26 — verified on a Tesseract-equipped machine: 0 skipped, status stays `Workaround` (skip path still exists for other hosts). 2026-10-27 (Phase 5.2, IMPL-0039): a **third** `requires_ocr` test added (`test_field_provenance.py`); re-verified on this machine — Tesseract 5.5.3 present since **24 Oct** (symlink date, i.e. before this task, not installed by it), `make test` → **704 passed, 0 skipped**; CONTEXT's "Tesseract is not installed here, so the 2 OCR tests skip" note (added `604fd54` the same day) was wrong for this machine and contradicted this entry's own 2026-10-26 update — corrected in the 5.2 CONTEXT edit. Status stays `Workaround`.

| BUG-0064 | 2026-10-28 | S4 | test harness and lint | Initial Phase 6.8 integration run exposed test fixture, auth matrix expectation and import-sort authoring defects | Fixed | IMPL-0059 |

### BUG-0064 — Initial Phase 6.8 integration run had test authoring defects
- Date found / found by / branch / commit: 2026-10-28 / Codex / master / pending.
- Severity / area: S4 / test harness and lint; no production grant state was written (pytest uses isolated test DBs).
- Status: Fixed.
- Expected: focused grant and exhaustive role/scope tests describe route authorization separately from business outcomes and supply eligible fixture records.
- Actual: the first combined run failed because the malformed-intake test had not arranged grant eligibility; the grant reader returned 404 for an application with no grant (the matrix expected the endpoint to pass authorization); an import edit landed in a specialized-role expected set; `make lint` caught import ordering.
- Reproduction: initial `pytest tests/test_phase6_grants.py tests/test_authz_matrix.py -q -p no:randomly` run during Phase 6.8 implementation.
- Environment: Python 3.13, pytest, SQLite.
- Hypotheses tried: checked whether failures arose from product authz vs fixture/business result; failures pointed to test expectations/setup, not broadened ACL.
- Root cause: test authoring conflated authorization with absence-of-resource semantics, forgot to make the intake candidate eligible, and used broad text replacement in the matrix import/set.
- Solution applied: no published grant now returns an explicit empty result for an in-scope application; test patches eligibility only for input-validation cases; matrix permission expectation is corrected; Ruff sorted imports.
- Verification: focused grant/authz **36 passed, 2 upstream warnings**; subsequent full `make test` **820 passed, 2 upstream warnings**; `make lint` clean.
- Regression test: `test_grant_batch_rejects_non_integer_intake_and_roles_are_narrow`, `test_matrix_lists_every_permission_gated_route`, and in-scope/out-of-scope matrix suite.
- Related: IMPL-0059.
