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
| IMPL-0009 | 2026-10-26 | Implementation | Phase 1.3: one parametrised routing test per Table 2.3 row (21 rows) against the PRD | Tested | Phase 1 1.3 (AGENT-02; FR-07) | MiMo (OpenCode agent) |
| IMPL-0008 | 2026-10-26 | Implementation | Phase 1.2: `services/routing.py` — Table 2.3 category → ordered stage list for the four PRD patterns | Tested | Phase 1 1.2 (AGENT-02; FR-07) | MiMo (OpenCode agent) |
| IMPL-0007 | 2026-10-26 | Implementation | Phase 1.1: all 21 Table 2.3 rows encoded in `workflow_routes.json` as unverified advisory configuration | Tested | Phase 1 1.1 (AGENT-02; FR-07) | MiMo (OpenCode agent) |
| IMPL-0006 | 2026-10-26 | Verification | Phase 0.5 exit check: all four hardening regression suites re-run green; limitations consolidated | Verified | Phase 0.5 exit check (H.1–H.4) | MiMo (OpenCode agent) |
| IMPL-0005 | 2026-10-26 | Implementation | H.4 document versioning: replacement reason recorded, immutability/partial-storage/signature tests | Tested | Phase 0.5 H.4 (AGENT-03; BUG-0006) | MiMo (OpenCode agent) |
| IMPL-0004 | 2026-10-26 | Implementation | H.3 authorisation matrix: every gated route × role × scope; 404-vs-403 policy documented | Tested | Phase 0.5 H.3 (Essentials §2, SYS-AUTH-001) | MiMo (OpenCode agent) |
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

### IMPL-0009 — Phase 1.3: one routing test per Table 2.3 row (21 rows, against the PRD)
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / fad38c4 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.3** (AGENT-02); PRD **FR-07** and its acceptance criterion "Routing accuracy vs Table 2.3: 100% (one test per row)".
- Goal: prove routing accuracy row by row — each of the 21 Table 2.3 categories resolves to the route pattern, application window and stage order the PRD says it should.
- What existed before: `test_routing.py` pinned the service and the four patterns' stage lists in aggregate, and `test_table_2_3_data.py` pinned the data shape, but nothing checked the 21 rows individually against the PRD table.
- What I did:
  - **Tests** — `backend/tests/test_routing_table_2_3.py` (24 items from 4 functions, first run green):
    - `test_row_routes_and_stages_match_the_prd[×21]`: the PRD's Table 2.3 is transcribed **independently in the test file** (`PRD_TABLE`: row → category_id, route, window), so drift in either the config or the transcription is caught; each row checks its `row` number, `route`, `window` (rows 1–13 `public_notice`, 14–21 `year_round`) and the full stage order from `stages_for_category` against the pattern's expected list (imported from `test_routing`, the single source for the §6/§7 flow).
    - `test_the_fn_oci_gulf_row_runs_scrutiny_without_evc`: row 8 carries `evc_not_applicable` and its SCR stage list contains no `evc`.
    - `test_only_that_row_carries_the_evc_not_applicable_flag`: exactly `["t23-08"]`.
    - `test_every_prd_row_is_present_and_resolvable`: 21 rows in, 21 resolvable, none dropped or renumbered.
  - No product or config change was needed — the data and service from 1.1/1.2 passed every row on the first run (the only fix was ruff's import-sort, `ruff check --fix`).
- Files changed: `backend/tests/test_routing_table_2_3.py` (new, 24), `md/6_IMPLEMENTATION_PLAN.md` (1.3 ticked — untracked), `README.md` + `CONTEXT.md` (221 → 245, suite list), this log.
- Migrations / API / config / rule-file changes: none.
- Decisions made: the expected PRD table is a second, independent transcription inside the test rather than a read-back of the config under test — a test that reads its expectations from the file it validates would pass even if the file were emptied.
- Permission and audit effects: none (pure lookup service; no endpoints touched).
- Verification: exact commands + results:
  - `pytest tests/test_routing_table_2_3.py -q -p no:randomly` → **24 passed** (first run; 21 of them are the per-row parametrisation)
  - `make lint` → first run flagged import sort in the new file → `ruff check --fix` → `All checks passed!`
  - `make test` → **245 passed, 1 warning in 32.73s** (0 skipped; +24 vs 221)
  - Not run: `npm run build` (no frontend change), Alembic, Compose.
- Status per requirement touched: Plan 1.3 "one parametrised test per row (21 passing)" — **Tested**; PRD FR-07 acceptance "routing accuracy 100%" — **Tested** against the PRD transcription (official-APH verification remains the blocked human step).
- Limitations / assumptions / manual steps:
  - Accuracy is proven against the PRD's transcription of Table 2.3, not against the official APH PDF — same blocked verification as 1.1 (docs/SOURCES.md).
  - The stage *behaviours* (running readiness, opening SHC only on deficiencies, appeal timing) are not exercised here; they arrive with the stage graph (Phase 3.1) and the AA gate (1.7).
- Related bugs: none.
- Open questions for a human: none new.
- Next suggested task: Phase 1 **1.4** — combined applications: `ApplicationItem` model + migration; union of stages; per-category outcome (FR-08).

### IMPL-0008 — Phase 1.2: `services/routing.py` — category → ordered stage list
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 0975417 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.2** (AGENT-02); PRD **FR-07** (route from category via configurable table), §6 pattern definitions, §7 end-to-end flow; rules2 SYS-ROUTE-001 (proposed).
- Goal: a routing service that answers — from configuration only — which PRD §6 pattern a Table 2.3 category uses and which stages that pattern runs, in order, marking the conditional ones.
- What existed before: task 1.1 had put the 21 rows and their `route` values in `workflow_routes.json`, but nothing mapped a pattern (SD / SCR / SCR+EVC / SCR+EVC+AA) to stages, and no service read the section.
- What I did:
  - **Config** — extended the `table_2_3` section with `route_patterns`: the four patterns, each with an ordered `stages` list of `{stage, when}` entries transcribed from PRD §6 (pattern definitions) and §7 (flow order): `readiness`, `nil_deficiency_report` (SD only), `scrutiny`, `evc`, `shc` (`when: if_deficiencies` — the §6 "AA" gate, FR-10), `executive_decision`, `appeal_window` (`when: on_decision` — §7), `grant`. Diff vs the 1.1 commit is additive apart from one structural `]` → `],` line.
  - **Tests first** — `backend/tests/test_routing.py` (10 tests): per-pattern stage order for all four patterns; the conditional flags (shc `if_deficiencies`, appeal_window `on_decision`, scrutiny/evc `always`); SD has no scrutiny and SCR has no evc/shc; every route a row uses must be a defined pattern; category lookup returns the row, its pattern and its stages (`t23-08` → SCR with `evc_not_applicable`); unknown category or pattern raises `KeyError` (never a silent default); the section still reports itself advisory. First run: **1 failed, 9 passed** — the drift guard assumed every pattern is used by a row, but the PRD's 21 rows use only SD/SCR/SCR+EVC+AA; no row is plain SCR+EVC (BUG-0007). Test corrected to the true contract (`used ⊆ defined` + all four patterns defined), then all 10 green. No data or product code changed for the fix.
  - **Service** — `backend/app/services/routing.py`: `table_2_3_rows()`, `category(category_id)`, `route_pattern(category_id)`, `route_patterns()`, `stages(pattern)`, `stages_for_category(category_id)`, `is_advisory()`. Unknown category/pattern raises `KeyError` with the id in the message — an unrecognised category must surface as "no route known", never resolve to a guess. Reads through the cached `policy.workflow_routes()`; no new dependency, no hard-coded route or stage.
- Files changed: `backend/rules/workflow_routes.json` (`route_patterns` + note inside `table_2_3`), `backend/app/services/routing.py` (new), `backend/tests/test_routing.py` (new, 10), `md/6_IMPLEMENTATION_PLAN.md` (1.2 ticked — untracked), `README.md` + `CONTEXT.md` (211 → 221, suite list), `docs/BUG_LOG.md` (BUG-0007), this log.
- Migrations / API / config / rule-file changes: config only (`workflow_routes.json`). No endpoint, model, permission or rule-file change.
- Decisions made: stage lists live in the JSON, not in Python, so the admin console (Phase 9) can version them; `when` vocabulary is three values only (always / if_deficiencies / on_decision) — the re-scrutiny loop is modelled by the workflow transitions (existing `returned ⇄ resubmit`), not by a second entry in the linear stage list. Note for humans: plain `SCR+EVC` is defined but used by no current Table 2.3 row (kept for the prototype `new_technical` route and the random-EVC add, 1.6).
- Permission and audit effects: none — the service is pure lookup, not yet called by any endpoint or workflow decision (that is 1.4+/3.1). No audit events.
- Verification: exact commands + results:
  - `pytest tests/test_routing.py -q -p no:randomly` → first run **1 failed, 9 passed** (BUG-0007), after the fix **10 passed**
  - `make lint` → `All checks passed!`
  - `make test` → **221 passed, 1 warning in 26.87s** (0 skipped; +10 vs 211)
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose.
- Status per requirement touched: Plan 1.2 "routing.py: category → ordered stage list; support SD, SCR, SCR+EVC, SCR+EVC+AA" — **Implemented · Tested**.
- Limitations / assumptions / manual steps:
  - Advisory only, like the rows themselves (Unverified until clause verification — same blocked item).
  - Stage names are a new vocabulary (`readiness`, `nil_deficiency_report`, …) that does not yet map to workflow *states* or `StageInstance` (Phase 3.1); no application's state is influenced by this service yet.
  - The SCR⇄compliance re-scrutiny loop and the random-EVC add are not modelled here (tasks 3.1/1.6).
- Related bugs: BUG-0007 (Fixed here).
- Open questions for a human: none new.
- Next suggested task: Phase 1 **1.3** — `test_routing_table_2_3.py`: one parametrised test per row (21 passing).

### IMPL-0007 — Phase 1.1: the 21 Table 2.3 routing rows, encoded as unverified advisory configuration
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 64976d4 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.1** (AGENT-02); PRD **FR-07** (assign route from category via configurable table), PRD §6 Table 2.3; rules2 SYS-ROUTE-001 (proposed).
- Goal: put all 21 APH Table 2.3 routing rows into configuration — category id, route pattern, application window, and the EVC-not-applicable flag on the FN/OCI/Gulf row — so tasks 1.2/1.3 can build the routing service against real data instead of a hard-coded list.
- What existed before: `backend/rules/workflow_routes.json` held only four prototype *state machines* (`new_technical`, `existing_technical`, `evc_only`, `evc_sac_shc`) with transitions/SLAs — no category-to-route mapping, no Table 2.3 rows anywhere in the repo. `grep` across `backend/` and `md/` confirmed the 21 rows existed only as a table inside `md/1_PRD.md` §6 ("routing test source of truth").
- What I did:
  - **Contract test first** — `backend/tests/test_table_2_3_data.py` (5 tests): first run failed exactly as intended (`AssertionError: workflow_routes.json has no table_2_3 section`), then all 5 green. It pins: exactly 21 rows in PRD order (row numbers 1…21); unique stable `category_id`s; `route` ∈ {SD, SCR, SCR+EVC, SCR+EVC+AA} and `window` ∈ {public_notice, year_round} (the PRD's §6 vocabulary); the `evc_not_applicable` flag on exactly one row — "Seats for Foreign Nationals, OCI, Children of Indian Workers in Gulf", shown by the PRD as "SCR (EVC n/a)"; and the honesty contract — section `status == "unverified"`, `advisory_only is True`, the note points at `docs/SOURCES.md`, and every row cites its source.
  - **Data** — added a `table_2_3` section to `backend/rules/workflow_routes.json`, transcribed row-for-row from the PRD table (`git diff` is purely additive: +200 lines, 0 deletions; the existing `routes` section is byte-identical). Each row: `row` (PRD order), `category_id` (`t23-01`…`t23-21`), `category` (PRD wording verbatim), `route`, `window`, `evc_not_applicable`, `source` ("md/1_PRD.md §6 Table 2.3 row N"), plus a `note` on rows 8 and 21 where the PRD has one. Section metadata: `status: "unverified"`, `advisory_only: true`, `recorded_on`, and a note stating the PRD §0 / DEC-0003 rule — advisory only until a named reviewer records the exact clause in `docs/SOURCES.md`, and clause numbers deliberately not guessed (each row cites its PRD table row instead).
- Files changed: `backend/rules/workflow_routes.json` (new `table_2_3` section), `backend/tests/test_table_2_3_data.py` (new, 5 tests), `md/6_IMPLEMENTATION_PLAN.md` (1.1 ticked — untracked), `README.md` + `CONTEXT.md` (206 → 211, suite list), this log.
- Migrations / API / config / rule-file changes: **config only** — `backend/rules/workflow_routes.json` gains a sibling section. `app/services/policy.py::workflow_routes()` loads the file whole and every consumer reads `.get("routes", {})`, so nothing existing changes behaviour (verified by the full suite staying green and by `seed.py`'s route seeding, which iterates `["routes"]`).
- Decisions made: none new — follows DEC-0003 (regulatory values Unverified/advisory) and the PRD §0 default status. The FN/OCI/Gulf row keeps `route: "SCR"` *and* `evc_not_applicable: true` so both facts survive separately, matching the plan line's wording ("EVC-not-applicable flag for FN/OCI/Gulf").
- Permission and audit effects: none (no code, no endpoints; the section is not yet read by any service — that is tasks 1.2/1.3).
- Verification: exact commands + results:
  - `pytest tests/test_table_2_3_data.py -q -p no:randomly` → first run **5 failed** (section absent — the intended red), after adding the data **5 passed**
  - `git diff --stat rules/workflow_routes.json` → `200 insertions(+)`, no deletions
  - `make lint` → `All checks passed!`
  - `make test` → **211 passed, 1 warning in 22.50s** (0 skipped; +5 vs 206)
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose.
- Status per requirement touched: Plan 1.1 "encode all 21 Table 2.3 rows" — **Implemented · Tested** (data + shape contract; routing *behaviour* is 1.2/1.3).
- Limitations / assumptions / manual steps:
  - Rows are transcribed from the PRD, which itself copies the APH — everything here stays **Unverified** until a human checks the exact clause/edition (blocked item; see `docs/SOURCES.md` required action). Clause numbers are deliberately absent rather than guessed.
  - Off-Campus (cl. 2.11e) and Extended EoA have **no** Table 2.3 row (PRD's own "gaps to confirm"); they are not invented here.
  - Window granularity is two values only; row 21's "twice a year per UGC timeline" is kept as a `note`, not a third window value.
  - The four prototype state machines are unchanged; mapping route patterns → state machines/stage lists is task 1.2's job.
- Related bugs: none (the first-run failures were the intended test-first red).
- Open questions for a human: same blocked item — who verifies the 21 rows against the official APH edition and records it in `docs/SOURCES.md`.
- Next suggested task: Phase 1 **1.2** — `services/routing.py`: category → ordered stage list, supporting SD, SCR, SCR+EVC, SCR+EVC+AA.

### IMPL-0006 — Phase 0.5 exit check: four hardening suites re-run; limitations consolidated
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 4f16517
- Task ID and PRD IDs: Phase 0.5 **Exit check** (covers H.1–H.4, AGENT-02 + AGENT-03); PRD core-consistency phase.
- Goal: prove the phase gate — every regression suite from H.1–H.4 still passes on the final tree, and the limitations of all four tasks are written down in one place.
- What existed before: H.1–H.4 each verified at its own commit; no single re-run of all four together on the final tree.
- What I did: re-ran the four suites together, then the full gate, and consolidated the limitations from IMPL-0002…0005 into the plan's exit-check line.
- Files changed: `md/6_IMPLEMENTATION_PLAN.md` (exit check ticked with the limitation summary — untracked user file, not in version control), `docs/IMPLEMENTATION_LOG.md` (this entry).
- Migrations / API / config / rule-file changes: none. Permission and audit effects: none (verification only).
- Verification: exact commands + results:
  - `pytest tests/test_concurrency.py tests/test_transaction_boundary.py tests/test_authz_matrix.py tests/test_document_versioning.py -q -p no:randomly` → **43 passed** (7 + 8 + 21 + 7)
  - `make lint` → `All checks passed!`
  - `make test` → **206 passed, 1 warning in 22.16s** (0 skipped)
  - Not run: `npm run build`, Compose/Postgres (no code changed since the H.4 verification at `b52c838`).
- Status per requirement touched: Phase 0.5 exit check — **Verified**.
- Limitations / assumptions / manual steps: the six consolidated limitations are recorded in `md/6_IMPLEMENTATION_PLAN.md` at the exit-check line (opt-in concurrency guard; matrix asserts authorisation only; H.4 SQLite-only migration verification; other mutation endpoints still lack the version guard; OCR skips without Tesseract; plan ticks not in version control).
- Related bugs: none new.
- Open questions for a human: unchanged from IMPL-0005 — add `make migrate-sqlite` to CI? Plus: may I commit `md/6_IMPLEMENTATION_PLAN.md` (and the rest of `md/`) so plan progress is versioned?
- Next suggested task: Phase 1 **1.1** — encode Table 2.3 rows in `workflow_routes.json` (blocked pending: confirm where the authoritative 21 rows come from, since inventing APH routes is forbidden).

### IMPL-0005 — H.4: document versioning — replacement reason, immutability, partial-storage failure, file signatures
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 271f8db (work uncommitted at implementation; committed and pushed per user instruction)
- Task ID and PRD IDs: Phase 0.5 **H.4** (AGENT-03); PRD document-versioning requirements (replacement creates a new immutable version; extraction linked to a version), `md/3_ARCHITECTURE_ESSENTIALS.md` (evidence immutability, no half-written evidence), rules2 SYS-DEF-001/SYS-REVAL-001 (corrective document versions feed the deficiency loop).
- Goal: prove the versioning contract the plan asks for — a replacement upload creates a **new immutable version with a reason**, every extraction/finding stays linked to the version it came from, a partial storage failure leaves no half-written row or file, and the file-signature check refuses content that contradicts its declared type.
- What existed before: upload already created a new `Document` row per version (`version = max + 1`), stored bytes under a per-version path with `os.replace` atomicity plus rollback cleanup, and linked `ExtractedField.document_version`. **Gaps:** no `reason` on replacement (nobody recorded *why* a version was replaced), and none of the above was covered by tests — `test_hardening` only checked the "not really a pdf" 415 and path-traversal names, `test_deficiency_loop` only `version > old`. Additionally `alembic check` was red (BUG-0006).
- What I did:
  - **Tests first** — `backend/tests/test_document_versioning.py` (7 tests): first run `2 failed, 5 passed` with `KeyError: 'upload_reason'` (reason genuinely absent), then all 7 green after implementation. Coverage:
    1. `test_a_replacement_adds_a_new_version_and_never_rewrites_the_old_one` — two uploads; v1 row snapshot (id, sha, storage_ref, version, uploaded_at, size, every field incl. `document_version`) byte-identical after v2; both files present on disk, both download endpoints return exactly their own sha; v2 `version == v1 + 1`; each extraction linked to its own version; both `document.uploaded` audit events carry the supplied reason; the list endpoint shows both reasons.
    2. `test_upload_without_a_reason_keeps_the_version_readable` — reason optional, upload still 201.
    3. `test_every_extracted_field_points_at_the_version_it_was_read_from` — after replacement, every `ExtractedField.document_version` equals its document's version.
    4. `test_verifying_a_field_changes_the_verdict_never_the_extraction` — officer verify flips `verification_status`, `value` and `document.version` unchanged (immutability of what was read). Uses `admin@demo.local` because `app-draft-0004` is unassigned (scrutiny scope would 404).
    5. `test_a_database_failure_after_the_file_is_stored_leaves_no_row_and_no_file` — monkeypatch `AuditService.append` to raise after the file is on disk → 500, no new row, no new file, no `.tmp` left.
    6. `test_a_failure_while_storing_the_file_leaves_no_row_and_no_temp_file` — monkeypatch `os.replace` in `app.api.documents` → 500, no row, no temp file.
    7. `test_a_declared_type_that_contradicts_the_file_signature_is_refused` — PNG bytes declared as `application/pdf` → 415 "file content is … declared"; empty body → 415 "empty"; no row, no file stored (the two signature branches `test_hardening` did not reach).
  - **Implementation** (smallest change): optional `reason: str = Form("", max_length=512)` on `POST /applications/{id}/documents`, stored on the new row (`documents.upload_reason`, nullable) and as the `document.uploaded` audit event's `reason`; `DocumentOut.upload_reason` exposes it. Deliberately **not** a `status = "superseded"` marker: `Document.status != "rejected"` is read by evidence/deadline/reporting services, so repurposing status would change what those services count.
  - **Migration 0007** — nullable `documents.upload_reason` (Text); existing rows stay NULL. **Migration 0008** — BUG-0006: creates `deficiencies` and `evc_visits` that two earlier feature commits added to the ORM without migrations; a Compose deploy (`alembic upgrade head` only) would have lacked both tables.
- Files changed: `backend/tests/test_document_versioning.py` (new, 7), `backend/app/api/documents.py` (reason param, row + audit), `backend/app/models/application.py` (`Document.upload_reason`), `backend/app/schemas/api.py` (`DocumentOut.upload_reason`), `backend/migrations/versions/0007_document_upload_reason.py` (new), `backend/migrations/versions/0008_deficiencies_and_evc_visits.py` (new, BUG-0006), `md/6_IMPLEMENTATION_PLAN.md` (H.4 ticked), `README.md` + `CONTEXT.md` (199 → 206), this log + `docs/BUG_LOG.md`.
- Migrations / API / config / rule-file changes: two new migrations (see above). API: one optional form field `reason` on the upload endpoint and one optional response field `upload_reason` — backward compatible; no permission, route or rule-file change.
- Permission and audit effects: no permission changes. Audit: `document.uploaded` now records the uploader's stated reason in `reason` (was empty). Two failure-path audit events (malware, scanner unavailable) untouched.
- Verification: exact commands + results:
  - `pytest tests/test_document_versioning.py -q -p no:randomly` → first run **2 failed, 5 passed** (reason missing, as intended), after implementation **7 passed**
  - `make lint` → `All checks passed!`
  - `make test` → **206 passed, 1 warning in 21.76s** (0 skipped; +7 vs the 199 baseline)
  - `make migrate-sqlite` → `alembic upgrade head` (0007 → 0008) then `alembic check` → **`No new upgrade operations detected.` / CHECK_OK**; downgrade to 0007 and re-upgrade both succeed; `ruff check migrations` clean
  - Not run: `npm run build` (no frontend change), Compose stack, Postgres.
- Status per requirement touched:
  - Plan H.4 "replacement creates a new immutable version with reason" — **Implemented · Tested**
  - Plan H.4 "extraction/finding links to a version" — **Tested** (already implemented; now pinned)
  - Plan H.4 "partial-storage-failure test" — **Tested** (both halves: DB failure after file stored; file failure before commit)
  - Plan H.4 "file-signature check" — **Tested** (lying declared type + empty body, the two untested branches)
- Limitations / assumptions / manual steps:
  - `Document.status` has no "superseded" value on purpose (see above); version history is told by `version` + `upload_reason` + the audit chain.
  - The partial-failure tests monkeypatch the exact seams (`AuditService.append`, `os.replace`); if the upload code moves those calls, the tests still pass as long as cleanup works — they assert the *invariant*, not the line number.
  - Migration 0008 was verified on SQLite only; Postgres types used are basic (String/Date/DateTime/JSON) and match the ORM, but `make up` + `make verify-isolation` were not run.
  - `alembic check` is not in CI — flagged in BUG-0006 as a question for a human.
- Related bugs: BUG-0006 (Fixed here).
- Open questions for a human: should CI run `make migrate-sqlite` to catch ORM/migration drift automatically?
- Next suggested task: Phase 0.5 **H.5** — read the next unchecked item in `md/6_IMPLEMENTATION_PLAN.md`.

### IMPL-0004 — H.3: authorisation matrix (every gated route × role × scope) and the 404-vs-403 policy
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 0b4bd11 (work uncommitted at implementation; committed and pushed per user instruction)
- Task ID and PRD IDs: Phase 0.5 **H.3** (AGENT-02); `md/3_ARCHITECTURE_ESSENTIALS.md` §2 (server-side check of role and state on every action), rules2 **SYS-AUTH-001** (only authorised actors decide), AGENTS.md "do not loosen authorisation".
- Goal: prove — for *every* permission-gated route, all six demo roles, and both an in-scope and an out-of-scope case — that the server answers 401 / 403 / 404 in the documented order, and write the 404-vs-403 policy where the repo keeps the role model.
- What existed before: `test_rbac.py` covered a handful of cases (scope of the list endpoints, 404 on an unassigned case, admin-only routes, revocation taking effect) but nothing asserted *all* gates, and nothing stopped a new route from shipping without an authorisation test. The 404 rule was one sentence in `docs/ROLE_MODEL.md`; the ordering of the checks (401 → 403 → 404), why scope failures are 404 rather than 403, and the fact that service-level refusals answer `200 {accepted:false}` rather than 403 were not written down anywhere.
- What I did:
  - **Tests first** — `backend/tests/test_authz_matrix.py` (21 items from 6 functions):
    - The route list is *discovered from the running application*: every route whose dependencies call `require(...)`/`require_any(...)` (54 routes), reading the permission out of the closure the dependency was built with. `test_matrix_lists_every_permission_gated_route` compares that with the matrix written in the file — a new sensitive route, a removed gate, or a changed permission fails the test until the matrix is updated on purpose. A route composing two permission gates fails the discovery assertion rather than being modelled wrongly.
    - `test_every_gated_route_refuses_a_request_without_a_token` → 401 on all 54.
    - `test_role_without_the_permission_is_refused_403_everywhere[×6 roles]` → 403 on every route whose permissions the role lacks, **for both cases** (in-scope and out-of-scope), proving the gate runs before any record is loaded.
    - `test_out_of_scope_case_is_404_not_403_for_a_role_that_may_act[×6]` → `app-second-0002` (Southern Region) answers 404 for the five scoped roles and passes for the global administrator, who is in scope everywhere by design.
    - `test_in_scope_case_passes_authorisation_for_every_role_that_may_act[×6]` → `app-main-0001` never answers 401/403, and on application-only routes never 404 either (a 404 there would mean the scope check wrongly refused a reachable case).
    - `test_permission_errors_map_to_403_and_scope_errors_to_404` pins `translate_permission_error` (`code="not_found"` → 404, otherwise 403); the HTTP-level mapping is covered by the loop tests through the `PermissionDenied` handler in `main.py`.
    - Requests carry **valid bodies** (multipart upload with `pdf_factory`, deficiency/undertaking/rehearsal/EVC-visit payloads, a deliberately unknown transition action so no state moves) so a refusal comes from the permission gate and not from validation.
  - **The tests were proved against broken code before the file was trusted.** Two temporary mutations, each run and then restored (`git diff` on both files empty afterwards):
    - permission gate removed from `require(...)` → `11 failed` (the 403 test for five roles, the out-of-scope test where scope-404 collapsed, and the coverage guard, which also notices a gate that no longer exists);
    - scope check removed from `require_application` → `11 failed` overall (the out-of-scope test for all five non-global roles).
    Restored: `21 passed`.
  - **Policy documented**: `docs/ROLE_MODEL.md` gained a **"404 versus 403"** section — the four statuses in check order (401 token → 403 route gate → 404 scope/lookup → anything else is a business refusal), why scope failures are 404 (an invented id must be indistinguishable from a real one, while "your role lacks `document.upload`" is not a secret), the two traps (service-level refusals answer `200 {accepted:false}`, not 403; `POST /applications` is the single endpoint that answers 403 from inside its body for an out-of-scope institution), and the honest limitation that on routes addressed by a *nested* resource id a 404 proves "refused" rather than specifically "out of scope".
- Files changed: `backend/tests/test_authz_matrix.py` (created), `docs/ROLE_MODEL.md` (policy section), `md/6_IMPLEMENTATION_PLAN.md` (H.3 ticked), `README.md` + `CONTEXT.md` (178 → 199, suite list).
- Migrations / API / config / rule-file changes: **none**. No endpoint, schema, permission or route-table change.
- Permission and audit effects: no permission changes. Note for reviewers: the matrix probes write rejected `workflow.matrix_probe_not_a_real_action` events (and a few `application.created` / sweep / undertaking rows) — **in the per-test database only**, which `conftest.py` drops and re-seeds around every test; nothing is written anywhere in production.
- Verification: exact commands + results:
  - `pytest tests/test_authz_matrix.py -q -p no:randomly` → first run **2 failed, 19 passed** (BUG-0005, two test-authoring defects), after the fix **21 passed**
  - mutation proof (gate removed, then scope removed) → **11 failed** each time; both files restored, `git diff` empty
  - `make lint` → `All checks passed!`
  - `make test` → **199 passed, 1 warning in 21.47s** (0 skipped; +21 vs the 178 baseline)
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose stack.
- Status per requirement touched:
  - Plan H.3 "authorisation matrix test: every sensitive route × role × scope" — **Implemented · Tested** (54 routes × 6 roles × in-scope/out-of-scope, plus anonymous)
  - Plan H.3 "404-vs-403 policy documented" — **Implemented** (`docs/ROLE_MODEL.md` §404 versus 403)
- Limitations / assumptions / manual steps:
  - The matrix asserts *authorisation*, not business outcomes: a request that passes the gate may still be refused by a rule (unknown probe action, placeholder nested id → 404, duplicate sweep) and that is asserted only as "not 401/403/404 where the case is reachable".
  - Roles are read from `ROLE_PERMISSIONS` in code; effective access is the union of a user's assignment rows, and the tests use the six seeded demo users. A *fourth* demo role or a custom grant is not covered.
  - Nested-resource routes (`{document_id}`, `{deficiency_id}`, `{undertaking_id}`, `{alert_id}`, `{assignment_id}`, `{run_id}`) are probed with placeholder ids, so their 404 cannot distinguish scope from missing record — stated in the policy section.
  - PostgreSQL/Compose was not exercised for this change.
- Related bugs: BUG-0005 (fixed here).
- Open questions for a human: none.
- Next suggested task: Phase 0.5 **H.4** — document versioning replacement semantics, partial-storage-failure test, file-signature check.

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
