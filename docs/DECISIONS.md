# docs/DECISIONS.md — code-verified answers and decision log

Answers to plan item **0.8** ("Answer from code"), plus the running decision
list. Every answer below was produced by **inspecting code this run**
(2026-10-26, master @ `a3477cb`), not from documentation claims.
Implementation decisions live in `docs/IMPLEMENTATION_LOG.md` (DEC-####);
this file holds the short operational answers and pointers.

## The six plan-0.8 questions

### D-0001 — Is `baseline_version` enforced?
**No — Partial. Present and incremented, but not enforced as optimistic concurrency.**
- `Application.baseline_version` exists (`models/application.py:59`), is incremented on every transition (`workflow_service.py:252,563`), field verification and deficiency/undertaking mutations (`api/documents.py:254,431`, `api/deficiencies.py`, `api/undertakings.py`).
- The rehearsal engine uses it correctly for staleness (`rehearsal_service.py:344-346` marks a run computed from a stale baseline; `api/applications.py:141-144` flags stale compliance findings).
- **But** `TransitionRequest` (`schemas/api.py:80-82`) carries only `action` + `reason` — no expected-version field — and `workflow_service` never compares a client-supplied version. A stale client can therefore transition from an out-of-date view (the state guard catches wrong-state moves, but two rapid same-action requests are not distinguished from a deliberate repeat).
- → **Gap = Phase 0.5 H.1.** Needs: optional `expected_baseline_version` in the request, `409` + reload message on mismatch, concurrent/duplicate-request tests, no partial write on rejection.
- **Resolved 2026-10-26 (IMPL-0002):** optional `expected_baseline_version` implemented on transition + revert; mismatch → audited rejection in the standard 200 `{accepted:false, reasons:[...]}` envelope (409 deliberately not used — open question logged for a human), reload message, no partial write; `test_concurrency.py` (7 tests). Partial remains: other mutation endpoints (field verify, deficiencies, undertakings) do not yet accept an expected version.

### D-0002 — Is the alert sweep scheduled or manual?
**Both.**
- Scheduled: persistent worker `app/workers/scheduler.py` ticks `deadline_jobs.run_once()` + `retry_pending()` every `--interval` (default 60 s); runs as the `worker` service in both Compose files.
- Manual: `POST /internal/deadline-sweep` and `GET /internal/deadline-preview` (`api/alerts.py:222,232`).
- Note (honesty rule): the *worker process* is scheduled by Docker; on plain `make dev` (SQLite) nothing sweeps unless the worker or the manual endpoint is used.

### D-0003 — Which notification channels are tested?
**In-app only, via the mock adapter.**
- `adapters/notifications/mock.py` writes a JSON line with `channel: "in_app"` to `storage/notifications.log`; `adapters/notifications/base.py` documents email/SMS as future work behind the same Protocol.
- Real delivery (email/SMS) is on the deferred list (plan "Deferred" section); do not claim otherwise.

### D-0004 — Is manual reassignment present?
**No per-case reassignment.** Search for `reassign` in `backend/app` → 0 hits.
- What exists: automatic hand-off `case_assignment_service.assign_next_actors()` (in-transaction on every transition), and admin role-scope management `POST /admin/assignments` + `POST /admin/assignments/{id}/revoke` (`api/admin_access.py:72,117`) which changes *who may act in scope*, not *who holds a specific case*.
- Building explicit reassignment needs an approved assignment policy first (rules2 SYS-ASSIGN-001; PRD OPEN question 4/5) → Phase 4.1, human decision required.

### D-0005 — Is conflict-of-interest present?
**No.** Search `conflict|coi` in `backend/app` → no COI declarations, exclusions or hiding logic (only unrelated HTTP 409 "CONFLICT" constants). Must not be claimed; rules2 SYS-COI-001 keeps it Blocked until an approved policy exists.

### D-0006 — Is Tesseract required or optional?
**Optional by design; the host binary is a soft dependency.**
- Runtime: `adapters/ocr/real.py` degrades with an honest warning when the binary is absent; PDFs with a text layer still extract.
- Tests: `tests/test_document_extraction.py:20-24` — `requires_ocr = skipif(shutil.which("tesseract") is None)`; OCR-path tests skip without it.
- Verified this run on this machine: Tesseract present → `163 passed, 0 skipped`.

## Decision list (short form; full entries in docs/IMPLEMENTATION_LOG.md)
| ID | Decision | Status |
|---|---|---|
| DEC-0001 | Database host = Supabase (managed Postgres only, own JWT auth) | Accepted |
| DEC-0002 | LLM chain Gemini → OpenRouter → more → deterministic; master switch off by default | Accepted |
| DEC-0003 | Regulatory values default to Unverified/advisory | Accepted |
| DEC-0004 | Planning documents live in `md/`, not `docs/prd/` | Accepted (user layout) |

## Open governance questions (from PRD §19a, unresolved — human owners needed)
- Who approves regulatory interpretations, role/route/deadline changes, and rule-config updates (four-eyes approval is planned in Phase 9.4 but no approver is named).
- Which repo/remote is authoritative and who may push (master prompt: never change remotes or push without confirmation).
- Acceptance date and sign-off authority for the evaluation build.
