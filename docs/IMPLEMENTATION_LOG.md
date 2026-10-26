# docs/IMPLEMENTATION_LOG.md

**Purpose:** the single place where every decision and every piece of implementation work is recorded, by humans and AI agents. Bugs and errors go in `docs/BUG_LOG.md`, not here (link between them by ID).

## Rules
1. **Append-only.** Add new entries at the **top of the Entries section** (newest first). Never edit or delete an old entry. To correct one, add a new entry that says `Supersedes: IMPL-0007` / `Amends: DEC-0003`.
2. **One entry per task or decision**, written when the work is finished (or when the decision is made), before you end your session.
3. **Truthful.** Status words only: Verified, Implemented, Tested, Partial, Proposed, Unverified, Blocked, Deprecated. Paste real command output summaries; never write "tests pass" without counts. Say "not run" when you did not run it.
4. **No secrets, tokens, real personal data or document contents.** Refer to files by path and hash.
5. Decisions that need a human (see Essentials: approval gates) are logged as `Proposed` with `Owner: <human>` until approved; do not implement them first.
6. IDs: `DEC-0001…` decisions, `IMPL-0001…` implementation entries, `BUG-0001…` live in the bug log. Use the next unused number.

## Index (keep updated; one line per entry)
| ID | Date | Type | Title | Status | Task / FR | Agent or author |
|---|---|---|---|---|---|---|
| IMPL-0003 | 2026-10-26 | Implementation | H.2 transaction boundary: one commit per workflow action; audit failure fails the operation | Tested | Phase 0.5 H.2 (Essentials §17, BUG-0004) | MiMo (OpenCode agent) |
| IMPL-0002 | 2026-10-26 | Implementation | H.1 optimistic concurrency: stale transitions/reverts rejected and audited | Tested | Phase 0.5 H.1 (Essentials §14a, SYS-CONCUR-001) | MiMo (OpenCode agent) |
| IMPL-0001 | 2026-10-26 | Implementation | Phase 0 baseline, repo audit and planning-doc set | Tested | 0.1–0.8, AGENT-01 | MiMo (OpenCode agent) |
| DEC-0004 | 2026-10-26 | Decision | Planning documents live in `md/`, not `docs/prd/` | Accepted | 0.3 | reyyishreyas (human) + agent |
| DEC-0003 | 2026-10-26 | Decision | Regulatory values default to Unverified/advisory | Accepted | PRD §0 | Project lead |
| DEC-0002 | 2026-10-26 | Decision | LLM chain Gemini → OpenRouter → more → deterministic; off by default | Accepted | addendum 7 | Project lead |
| DEC-0001 | 2026-10-26 | Decision | Database host = Supabase (managed Postgres only, own JWT auth) | Proposed→Accepted | addendum 7 | Project lead |

## Entry template: decision
```
### DEC-XXXX — <short title>
- Date / author (human or agent name + model):
- Status: Proposed | Accepted | Rejected | Superseded by DEC-XXXX
- Context (what forced the decision; link PRD/FR/OPEN IDs and sources):
- Options considered (A/B/C with one-line pros/cons):
- Decision:
- Rationale:
- Consequences (what it changes, what it blocks, follow-ups):
- Approval needed from / approved by / date:
- Evidence (links to commits, tests, official source IDs):
```

## Entry template: implementation
```
### IMPL-XXXX — <short title>
- Date / agent (name + model) / branch / commit hash:
- Task ID (AGENT-xx or plan item) and PRD IDs (FR-xx):
- Goal:
- What existed before (files/symbols reused, or "search found nothing"):
- What I did (bullet list; plain language):
- Files changed (path — reason):
- Migrations / API / config / rule-file changes:
- Decisions made (link DEC-XXXX; any new decision must also get its own DEC entry):
- Permission and audit effects:
- Verification: exact commands + results (counts, skips and why). Anything not run = "not run".
- Status per requirement touched (status words):
- Limitations / assumptions / manual steps:
- Related bugs (BUG-XXXX):
- Open questions for a human:
- Next suggested task:
```

## Entries (newest first)
<!-- add entries below this line -->

### IMPL-0003 — H.2: transaction boundary — one commit per workflow action; audit failure fails the operation
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / a3477cb (work uncommitted at implementation; pushed later per user instruction)
- Task ID and PRD IDs: Phase 0.5 **H.2** (AGENT-02); Essentials §17 (audit for every state change) and the plan's transaction-boundary item ("state + transition + assignment + required audit commit together; audit-write failure fails the operation"); rules2 SYS-ASSIGN-001 (assignment atomicity with the move).
- Goal: one workflow action = one transaction. A failure anywhere in it — including the audit write itself — must leave the database exactly as it was, never half-moved.
- What existed before: the main transition path already committed state + transition + assignment + audit in a single `db.commit()` (good by construction, untested). Two genuine two-transaction windows existed (BUG-0004): `_complete_evc_visits` and `_cancel_visits_on_revert` each ran **after** the main commit with their own commit — a failure between them left the case and its EVC booking contradictory.
- What I did:
  - **Tests first** (`backend/tests/test_transaction_boundary.py`, 8 tests): the four effects commit together (state/transition/assignment/audit visible after one call); audit-write failure fails the transition and the revert leaving no partial write (state, version, transition rows, assignment rows and audit count all unchanged, chain still verifies); the same guarantee at the HTTP boundary (broken audit store ⇒ 500, case untouched); EVC completion and its visit update are one step; visit-cancellation failure rolls back the whole revert. The two window tests were run against the old code first and **failed** (`'evc_completed' == 'evc_scheduled'`), proving the bug before the fix.
  - Moved `_complete_evc_visits(db, application.id)` and `_cancel_visits_on_revert(db, application, from_state, target_state)` **before** the single `db.commit()` in `request_transition` / `revert_last_transition`.
  - Removed both helpers' internal `db.commit()`; docstrings now state "runs inside the caller's transaction — it must not commit on its own".
  - No API/schema/config/migration change; no permission change; audit coverage unchanged (the `evc.visit_cancelled` event is now written in the same transaction as `workflow.revert` instead of a separate one — same events, one commit).
- Files changed: `backend/app/services/workflow_service.py` (call order + two helper bodies), `backend/tests/test_transaction_boundary.py` (created).
- Migrations / API / config / rule-file changes: none.
- Permission and audit effects: no permission changes. Audit events themselves are unchanged in content; rejection path untouched (rollback-then-audit-in-new-transaction remains the deliberate design for rejections, documented in audit_service's docstring — a rejection has no business transaction left to protect once it is refused).
- Verification: exact commands + results:
  - `pytest tests/test_transaction_boundary.py -q` before the fix → **2 failed** (the window tests, bug proven), 6 passed; after the fix → **8 passed**
  - `make lint` → `All checks passed!`
  - `make test` → **178 passed, 1 warning in 17.43s** (0 skipped; +8 vs the 170 baseline)
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose stack.
- Status per requirement touched:
  - Plan H.2 "state + transition + assignment + required audit commit together" — **Implemented · Tested**
  - Plan H.2 "audit-write failure fails the operation" — **Implemented · Tested** (service + HTTP boundary; the API returns 500 and the case is untouched)
- Limitations / assumptions / manual steps:
  - Fault injection replaces the failing write with one that raises — an honest stand-in for a DB/storage failure, but not a real killed-connection test; the Postgres/Compose stack was not exercised for this change.
  - `schedule_visit` in `api/evc.py` intentionally remains two transactions (booking first, auto-transition second) — the code documents that the booking stands even when the case cannot move; that is a product decision, not a partial write, and was left as-is.
- Related bugs: BUG-0004 (fixed here).
- Open questions for a human: none.
- Next suggested task: Phase 0.5 **H.3** — authorisation matrix test; 404-vs-403 policy documented.

### IMPL-0002 — H.1: optimistic concurrency enforced on transitions and reverts
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / a3477cb (work uncommitted)
- Task ID and PRD IDs: Phase 0.5 **H.1** (AGENT-02); Essentials §14a (Concurrency); rules2 **SYS-CONCUR-001**; DECISIONS D-0001 gap.
- Goal: a write based on a stale view of a case must be refused with a reload message and audited, leaving no partial write — two officers working from the same snapshot can never silently overwrite each other.
- What existed before: `Application.baseline_version` incremented on every mutation but never compared against a caller-supplied value (`TransitionRequest` = {action, reason}); D-0001 recorded the gap.
- What I did:
  - Added optional `expected_baseline_version` to `TransitionRequest` and `RevertRequest` (schema; optional = backward compatible, the UI adopts it in AGENT-11).
  - `workflow_service.request_transition` / `revert_last_transition`: new guard **1a**, right after the scope check and before all other guards — a mismatched version returns the existing audited-rejection path (`_reject` → rollback → `workflow.<action>` rejected event) with a "reload the case and try again" message naming both versions. Documented as step 1a in the module docstring (the original 8-step order is unchanged).
  - New `tests/test_concurrency.py` (7 tests): matching version accepted; stale version rejected + reload message + audited + chain still verifies; duplicate same-version request cannot double-advance (exactly one transition row); omitted field keeps the legacy contract; invalid action with current version leaves no partial write; stale revert rejected then current version reverts; HTTP-level test proving the field flows through the endpoint.
- Files changed:
  - `backend/app/schemas/api.py` — `TransitionRequest.expected_baseline_version`
  - `backend/app/api/workflow.py` — `RevertRequest.expected_baseline_version`; both endpoints pass it through
  - `backend/app/services/workflow_service.py` — `_stale_version_reasons()` helper; guard 1a in both functions; docstring updated
  - `backend/tests/test_concurrency.py` — created
- Migrations / API / config / rule-file changes: **no migration** (no model change). API change: two POST bodies gain an **optional** field; response shape unchanged (rejections remain the 200 `{accepted: false, reasons:[...]}` envelope used by every other guard — kept for contract consistency; a 409 variant was considered and rejected to avoid breaking the frontend/smoke script, noted here for future decision).
- Decisions made: none new beyond the above; consistent with DEC-0003 (no regulatory values involved).
- Permission and audit effects: no permission changes. Stale rejections now write a `workflow.<action>` rejected audit event (same as every other rejection) — audit coverage increased, nothing removed. Rejections roll back before auditing, so no partial state persists.
- Verification: exact commands + results:
  - `pytest tests/test_concurrency.py -q` → first run 6 passed, 1 failed (BUG-0003, test-harness staleness); after fix → **7 passed**
  - `make lint` → `All checks passed!`
  - `make test` → **170 passed, 1 warning in 15.72s** (0 skipped; +7 vs the 163 baseline)
  - Not run: `npm run build` (no frontend change — the UI simply omits the optional field), Alembic check (no model change), Compose stack.
- Status per requirement touched:
  - Essentials §14a optimistic concurrency on transitions — **Implemented · Tested** (service + HTTP)
  - SYS-CONCUR-001 (rules2) — **Partial → Tested for the transition/revert paths**; field-verify/deficiency/undertaking mutations bump the version but do not yet accept an expected version (follow-up below)
- Limitations / assumptions / manual steps:
  - The check is **opt-in per request**: clients that omit the field keep today's behaviour (deliberate, to avoid breaking the UI and `scripts/smoke.sh`; making it mandatory is an AGENT-11 task).
  - Concurrency is tested deterministically (two sequential calls sharing one observed version), not with real threads — honest equivalent on SQLite; the Compose/Postgres stack was not exercised for this change.
  - Other mutation endpoints (field verify, deficiencies, undertakings) remain unprotected — same mechanism can be extended there later.
- Related bugs: BUG-0003 (test-harness session staleness, fixed).
- Open questions for a human: should stale writes return HTTP 409 instead of the 200 rejection envelope? (Current choice keeps the existing contract; a change would need the frontend + smoke script updated together.)
- Next suggested task: Phase 0.5 **H.2** — transaction boundary: audit-write failure must fail the operation.

### IMPL-0001 — Phase 0 baseline, repository audit and planning-doc set
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / a3477cb
- Task ID and PRD IDs: plan 0.1–0.8, AGENT-01 (repository audit). Covers FR-07…FR-11 scope mapping (audit only), no functional requirement implemented this run.
- Goal: orient, establish the verified baseline, inventory rules-as-data, answer the six code questions (plan 0.8), produce the gap matrix, and stand up the mandatory log/traceability/source files so later tasks can start from facts.
- What existed before:
  - Repo docs: `README.md`, `CONTEXT.md`, `things.md`, `docs/*.md` (11 files). **No** `docs/IMPLEMENTATION_LOG.md`, `docs/BUG_LOG.md`, `AGENTS.md`, `docs/SOURCES.md`, `docs/TRACEABILITY.md`, `docs/DECISIONS.md` — search found nothing; created this run from the `md/8_…` and `md/9_…` templates.
  - Planning set present in `md/` (user moved the six PRD docs + PDFs there; git shows them deleted from root, `md/` untracked). See DEC-0004.
  - Re-reported paths confirmed to exist: `services/workflow_service.py`, `services/case_assignment_service.py`, `services/deadline_service.py`, `core/permissions.py`, `services/authorization_service.py`, `rules/workflow_routes.json`, `rules/deadline_policy.json`, `rules/compliance_rules.json`, `workers/scheduler.py`, `api/admin_access.py`.
- What I did (plain language):
  - Ran the baseline gates and recorded counts (below).
  - Inventoried the three rules-as-data files (plan 0.4) and wrote `md/GAP_NOTES.md` with a FEAT-01…18 gap matrix citing files/symbols or confirmed absence (plan 0.5, AGENT-01).
  - Answered the six plan-0.8 questions **from code**, recorded in `docs/DECISIONS.md`.
  - Seeded `docs/SOURCES.md` (URLs copied from `things.md` §References, attributed, marked for human verification — none invented) and `docs/TRACEABILITY.md`.
  - Created `AGENTS.md` + `CLAUDE.md` at repo root (paths adapted from `md/4_AGENTS.md` to the `md/` layout).
  - Fixed stale doc drift: README repository-map said 155 tests (actual 163) — see BUG-0002.
- Files changed:
  - `docs/IMPLEMENTATION_LOG.md` — created (this file)
  - `docs/BUG_LOG.md` — created from template
  - `AGENTS.md`, `CLAUDE.md` — created at repo root
  - `md/GAP_NOTES.md` — created (rules inventory + gap matrix)
  - `docs/SOURCES.md`, `docs/TRACEABILITY.md`, `docs/DECISIONS.md` — created, seeded
  - `README.md` — 155 → 163 test count in the repository map (BUG-0002)
  - `md/6_IMPLEMENTATION_PLAN.md` — Phase 0 boxes ticked with notes
- Migrations / API / config / rule-file changes: **none** (audit-only run; no backend or frontend code touched).
- Decisions made: DEC-0004 (planning docs live in `md/`).
- Permission and audit effects: none (no code paths changed).
- Verification (exact commands + results):
  - `make lint` → `All checks passed!`
  - `make test` → `163 passed, 1 warning in 16.59s` (0 skipped; Tesseract present on this host). The warning is a third-party `StarletteDeprecationWarning` from `fastapi/testclient.py` (httpx deprecation), not ours.
  - `git status` → branch master, up to date with origin/master; unstaged deletions of the root planning docs (moved by the user) + untracked `md/` (see DEC-0004). No code modifications besides the README count fix.
  - Not run this session: `make build` (no UI change), Alembic check (no model change), `make up` / `make smoke` / `make verify-isolation` (no Docker stack started).
- Status per requirement touched:
  - Phase 0 baseline — **Tested** (163 passed recorded, skips: none)
  - FEAT-02 workflow state machine — **Implemented** (code inspected: `workflow_service.py` guard order scope→permission→role→route→state→reason→documents→rules, audited rejections)
  - FEAT-14 audit chain — **Implemented** (hash-chain append verified in code paths; tamper test not re-run this session)
  - Optimistic concurrency on transitions (Essentials §14a) — **Partial**: `baseline_version` exists, is incremented and used for rehearsal staleness, but `TransitionRequest` carries no expected-version field, so stale writes are not rejected → Phase 0.5 H.1
  - Manual per-case reassignment — **not present** (only automatic `assign_next_actors` + admin role-scope grant/revoke)
  - COI handling — **not present** (confirmed by search; do not claim)
  - ExternalCallLog / external-call switch — **not present** (search found nothing)
  - `adapters/llm` — Protocol + mock exist, **unwired** (no OpenRouter adapter file)
- Limitations / assumptions / manual steps:
  - The gap matrix cites files inspected this run; entries marked "(reported, spot-checked)" lean on CONTEXT.md/README and should be re-verified by the owning task.
  - `docs/SOURCES.md` URLs are copied from repo research notes, **not independently fetched/verified** by this agent — human must confirm each against the live official page (plan 0.6 is explicitly a human task).
  - Planning-doc location deviates from plan 0.3 (`docs/prd/`); see DEC-0004.
- Related bugs: BUG-0001 (Tesseract skip, updated), BUG-0002 (README test-count drift, fixed).
- Open questions for a human:
  - Confirm DEC-0004: keep `md/` as the planning-doc home (no `docs/prd/` copy), or restore `docs/prd/`?
  - Plan 0.6: verify the APH 2024-27 URL + 2026-27 addendum in `docs/SOURCES.md` and record the exact PS 26262 official URL.
- Next suggested task: Phase 0.5 H.1 — enforce `baseline_version` on transitions (stale write rejected, concurrent-transition test).
