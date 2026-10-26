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
