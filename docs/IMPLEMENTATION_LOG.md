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
| IMPL-0017 | 2026-10-26 | Implementation | Phase 2.2: `readiness.py` cut-off check — tag for next AY, never reject (FR-02) | Tested | Phase 2 2.2 (AGENT-08; FR-02) | MiMo (OpenCode agent) |
| IMPL-0016 | 2026-10-26 | Implementation | Phase 2.1: `calendars.json` + `working_calendar.py` — IST, working days, holidays, Public Notice / Academic Calendar lookups (FR-37) | Tested | Phase 2 2.1 (AGENT-08; FR-37) | MiMo (OpenCode agent) |
| IMPL-0015 | 2026-10-26 | Implementation | Phase 1.9: route scoreboard — `GET /workflow/table-2-3-scoreboard` + `RouteScoreboard.tsx` (Phase 1 exit check) | Tested | Phase 1 1.9 (AGENT-02; FR-07) | MiMo (OpenCode agent) |
| IMPL-0014 | 2026-10-26 | Implementation | Phase 1.8: fallback-to-EoA branch after "not approved" (FR-11) — eligible, never auto-issued | Tested | Phase 1 1.8 (AGENT-02; FR-11) | MiMo (OpenCode agent) |
| IMPL-0013 | 2026-10-26 | Implementation | Phase 1.7: "AA" gate — SHC/SAC opens only on a deficiency or negative scrutiny result (FR-10) | Tested | Phase 1 1.7 (AGENT-02; FR-10) | MiMo (OpenCode agent) |
| IMPL-0012 | 2026-10-26 | Implementation | Phase 1.6: additional-EVC actions — random EVC for SD (2.3.5), second EVC after site shift (2.17e) | Tested | Phase 1 1.6 (AGENT-02; FR-19) | MiMo (OpenCode agent) |
| IMPL-0011 | 2026-10-26 | Implementation | Phase 1.5: sequencing rule — Women's conversion must clear before the merger starts (cl. 2.13.1m) | Tested | Phase 1 1.5 (AGENT-02; FR-08) | MiMo (OpenCode agent) |
| IMPL-0010 | 2026-10-26 | Implementation | Phase 1.4: combined applications — `ApplicationItem` (outcome per category), stage union, migration 0009 | Tested | Phase 1 1.4 (AGENT-02; FR-08) | MiMo (OpenCode agent) |
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

### IMPL-0017 — Phase 2.2: readiness cut-off check — tag next AY, never reject (FR-02)
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 3e7796c (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 2 **2.2** (AGENT-08 intake/readiness); PRD **FR-02** (P0) "Reject from processing and tag for next AY any application submitted/paid after cut-off" (APH cl. **2.2, 2.22**); §6 routing rule 7 ("applications after the Public Notice cut-off are queued for the next Academic Year"). Uses the cut-off date lookup built in 2.1 (IMPL-0016).
- Goal: a pure readiness service that answers whether a submission fell after the Public Notice cut-off and, if so, *names* the queue-for-next-AY tag — while never rejecting, blocking or guessing.
- What existed before: **no** `readiness.py` and no readiness/flag/tag persistence anywhere in `backend/` (repo-wide search for `readiness|cut_off|next_ay|tag|queued` returned only unrelated matches — `retention_service` cutoffs, `router` tags, `deadline_service.cycle_key`). `working_calendar` (2.1) already exposed `business_date()` and `public_notice_cutoff()`; `policy.py` had no readiness loader. `Application` has `submitted_at` but **no "paid"/TER field** — FR-02's "submitted/paid" can only be evaluated on `submitted_at` today (TER-paid is FR-01/FR-21 territory, not modelled).
- What I did (tests written alongside the service, per workflow step 3):
  - **Tests** — `backend/tests/test_readiness_cutoff.py` (**14 tests**, all passed on the run after implementation). Coverage: config loads `unverified`+`advisory_only` and cites FR-02/2.2/2.22; **the policy says `reject: false`** and `action_on_after_cutoff: queue_for_next_academic_year`; a **status-vocabulary guard** asserts `rejected`/`blocked` can never appear unnoticed (only `within_window`/`after_cutoff`/`needs_review`); with the real **empty** `calendars.json` every submission answers `needs_review` (not "in window"); a missing submission time is `needs_review`; a year with no recorded cut-off is `needs_review` with `cut_off: None` (never "no cut-off applies"); a loaded year → `within_window` (mid-window and *on* the cut-off date, end-of-day semantics); after the cut-off → `after_cutoff` **with the tag but never the word rejected**; the check is **pure** (two calls → equal dicts, no state); naive datetime read as **UTC not IST**; and a boundary test proving the business date is **IST** (19:00 UTC on 04-30 = 00:30 IST on 05-01 → after a 04-30 cut-off).
  - **Config** — `backend/rules/readiness_policy.json` (new): a `cut_off` rule block `{rule, action_on_after_cutoff, reject: false, reject_note, date_source: calendars.json, date_source_note, status: unverified, advisory_only, source: FR-02 (cl. 2.2, 2.22)}`. The **`reject: false` + `reject_note`** record the central decision (below); `date_source` points at `calendars.json` so there is one source of truth for dates. Deliberately a *new* file (not a key bolted onto `workflow_routes.json`) because 2.3's blocked-application flags (FR-03) will extend it — rule-as-data grouped by domain, matching how routing rules live in `workflow_routes.json`.
  - **Loader** — `policy.readiness_policy()` (existing `_load` + `lru_cache` pattern; third function added alongside `calendars()` in 2.1).
  - **Service** — `backend/app/services/readiness.py` (new): `cut_off_policy()` (raises `KeyError` if the rule block is missing, so a deleted rule fails loudly rather than answering "no cut-off applies") and `cut_off_check(submitted_at, *, calendars_cfg=None, policy_cfg=None) -> dict` returning `{status, cut_off, submitted_on, tag, action, reason, source, advisory_only}`. Uncertainty (`None` submission or no cut-off for the year) is resolved **before** the in/out comparison so absent data cannot fall through into a confident `within_window`. `statuses()` exposes the vocabulary so the guard test can pin it. The `cfg` keywords let tests exercise a *loaded* year without putting a date in the shipped (empty) config — same technique as 2.1.
- Files changed: `backend/rules/readiness_policy.json` (new), `backend/app/services/readiness.py` (new), `backend/app/services/policy.py` (+`readiness_policy()`), `backend/tests/test_readiness_cutoff.py` (new, 14), `md/6_IMPLEMENTATION_PLAN.md` (2.2 ticked), `README.md` + `CONTEXT.md` (318 → 332, suite list), this log.
- Migrations / API / config / rule-file changes: one new rule file; **no** model, endpoint, permission or audit change. The tag is **advice returned to a caller, not persisted** — no column added, no state transition. Persisting the tag onto a case + officer clear/hold is explicitly task 2.3's flag flow; doing it here would have meant a migration before the flag UX exists.
- **Decision (the important one) — FR-02's "reject" half is deliberately NOT implemented:** PRD FR-02 literally says "*Reject from processing* and tag for next AY", but the plan's 2.2 line says "cut-off check → tag next AY, **never reject**", and PRD §0 states Unverified cut-offs "never block, return or reject an application" (Master Prompt §2 rule 3). The plan + §0 override the FR-02 wording: only the tag is implemented, `reject` is pinned `false` in config with a `reject_note` explaining why, and the status vocabulary provably contains no rejected/blocked value. **Flipping `reject: true` for an Unverified cut-off would be a human approval gate** (decision-authority + regulatory interpretation) and needs a verified date first — noted, not done. (Had I implemented FR-02 verbatim it would have been an AI/automation *rejecting* an application — exactly what AGENTS.md §Do-not forbids.)
- Permission and audit effects: none — no endpoint, so no permission applies and no audit event is written. When 2.3 persists the tag (or a future flow queues a case), that action carries its own permission and `application.*` audit event — noted for 2.3.
- Verification: exact commands + results:
  - `pytest tests/test_readiness_cutoff.py -q -p no:randomly` → **14 passed**
  - `make lint` → `All checks passed!`
  - `make test` → **332 passed, 1 warning in 30.47s** (0 skipped; +14 vs 318)
  - `json.load` re-checked on `readiness_policy.json` after writing (valid).
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose/Postgres.
- Status per requirement touched: Plan 2.2 "`readiness.py`: cut-off check → tag next AY, never reject (FR-02)" — **Implemented · Tested**. The check runs end-to-end against the real empty calendar and correctly answers `needs_review`; the "tag" half is implemented as a *returned advisory tag*; the "never reject" half is enforced in config + vocabulary + tests.
- Limitations / assumptions / manual steps:
  - **No cut-off date exists**, so in production today the check always returns `needs_review` — correct, but it means FR-02 is not yet *operational*. Loading an official Public Notice date (2.1's `calendars.json.years`) flips it to real within/after answers. Both are blocked on a human recording a verified date.
  - FR-02's "**paid**" half is not evaluated: the `Application` model has no payment/TER-paid timestamp (only `submitted_at`). A cut-off keyed on payment time needs a schema field + source — open question, not guessed here.
  - The cut-off is looked up by the **submission's calendar year**; a submission whose relevant Public Notice belongs to a *previous* calendar year (e.g. Jan 2027 under a 2026 notice) would find no date and answer `needs_review` rather than matching the prior year's notice. Safe (never a wrong pass), but a real multi-year calendar may need an explicit AY→notice mapping — flagged, not assumed.
  - The tag is advisory and unpersisted; nothing queues, blocks or re-judges a case.
- Related bugs: none (no BUG entry; no failing run this task).
- Open questions for a human: (1) Should FR-02 ever *reject* from processing? Recommended default (implemented): **no** — queue/tag only, per PRD §0 and the plan; rejection would need a verified cut-off + explicit approval. Owner: regulatory reviewer. (2) Should the cut-off also consider the **payment** time (FR-02 says "submitted/paid")? Needs a payment-timestamp field — owner: product. (3) Load an official Public Notice cut-off date for the applicable year into `calendars.json` (unblocks FR-02 operationally) — owner: regulatory reviewer.
- Next suggested task: Phase 2 **2.3** — blocked-application flags: five rules from FR-03, officer can clear or hold.

### IMPL-0016 — Phase 2.1: `calendars.json` + `working_calendar.py` (IST, holidays, Public Notice, Academic Calendar)
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 34c52d4 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 2 **2.1** (AGENT-08 deadlines/calendar, with AGENT-02 read-first); PRD **FR-37** (P0) "Load yearly Public Notice dates and Academic Calendar; apply to all clocks"; source clauses **APH 2.2, 2.25** (cited as the PRD cites them, not independently verified). Feeds FR-02 (cut-off → next AY, task 2.2) and FR-32 (no grant after the Academic Calendar's last date).
- Goal: give every clock a single, configuration-driven notion of *when* — the business timezone (IST), the working-day convention, holidays, and the yearly Public Notice / Academic Calendar windows — as a loadable config plus a pure service, without inventing one date.
- What existed before: `settings.business_timezone = "Asia/Kolkata"` (config.py) and `deadline_service.end_of_day()` already used it; `policy.py` had `_load()` + `@lru_cache` for `compliance_rules`/`workflow_routes`/`deadline_policy` but **no** `calendars.json`; a repo-wide search for holiday/working-day/IST/PN/AC logic found nothing. So the loader and the calendar service were the missing pieces — the timezone itself was already correct and reused.
- What I did:
  - **Tests first** — `backend/tests/test_working_calendar.py` (24 tests). All 24 initially failed at collection (`ImportError: cannot import name 'working_calendar'`), proving the module was genuinely absent; after implementation all 24 passed. Coverage: config loads as `unverified` + `advisory_only` and cites FR-37/2.2/2.25; the shipped `template` is a *shape* with nulls (not a value); **`years` is empty because no official date exists in the PRD or rules files**; timezone is `Asia/Kolkata` **and equals `settings.business_timezone`** (divergence guard); an instant is read as a business date in IST (19:30 UTC → next day in IST, 00:00 UTC → same day) and a **naive** datetime is read as UTC, never as IST; unconfigured years return `None`/`()` (never a guessed date), including against the real empty config for 2026; a loaded year returns its exact configured cutoff/calendar/holidays; a year entry *missing* its `public_notice`/`academic_calendar` block does not crash; working-day maths — weekday working, weekend not, a configured **holiday on a weekday** not (isolated from the weekend rule), the **weekend convention read from config** (move it to Mon+Tue and Saturday becomes working), `add_working_days` skips weekends and skips holidays, `+0` returns the start, negative walks backwards, and a calendar with **no working day at all raises `ValueError` instead of hanging**. (Two of my own test assertions were wrong first — a holiday placed outside the walk's path, and a meaningless `is False or True` — both fixed before the final run; the service was correct in both cases.)
  - **Config** — `backend/rules/calendars.json` (new): `status: unverified`, `advisory_only: true`, `source` citing FR-37 (cl. 2.2/2.25), `timezone: Asia/Kolkata` (with a note that a test keeps it in sync with `settings.business_timezone`), `weekend_days: [5, 6]` (Python weekday, Saturday+Sunday) with a note that it is Unverified until the AICTE/office working week is confirmed, **`years: {}`** with a `years_note` explaining exactly *why* it is empty (PRD records no date; `rules.json` marks them unverified/null; `rules2.json` allows a cut-off "only when the applicable notice and time basis are verified"), and a `template` + `template_note` giving a reviewer the exact shape to fill (`public_notice.closes_on` = FR-02 cut-off; `academic_calendar.last_grant_date` = FR-32; `holidays` = ISO dates) with per-block `status`/`source_refs` so a year can be *partly* verified.
  - **Loader** — `policy.calendars()` (one function, the existing `_load` + `lru_cache` pattern; no new loader invented).
  - **Service** — `backend/app/services/working_calendar.py` (new): `calendars()`, `timezone()`, `business_date()` (naive→UTC→IST, via the existing `core.clock.to_utc`), `public_notice()`, `public_notice_cutoff()`, `academic_calendar()`, `holidays_for()`, `is_working_day()`, `add_working_days()`. Every lookup takes an optional `cfg` keyword so tests can exercise a *loaded* year with a synthetic fixture (a far-future 2099 sample that can never collide with a real application year) while the shipped config stays empty. `add_working_days` is bounded (`_MAX_WORKDAY_STEPS = 3660`) so a no-working-day config raises rather than loops forever.
- Files changed: `backend/rules/calendars.json` (new), `backend/app/services/working_calendar.py` (new), `backend/app/services/policy.py` (+`calendars()`), `backend/tests/test_working_calendar.py` (new, 24), `md/6_IMPLEMENTATION_PLAN.md` (2.1 ticked), `README.md` + `CONTEXT.md` (294 → 318, suite list), this log.
- Migrations / API / config / rule-file changes: one new rule file (`calendars.json`); **no** model, endpoint, permission or audit change. No existing deadline behaviour was altered — `deadline_service` still uses `settings.business_timezone` (which the new config is asserted to match), so this is purely additive.
- Decisions made: (1) **ship `years: {}` rather than invent Public Notice/Academic Calendar dates** — the PRD gives none and both rules files forbid activating unverified windows, so the honest deliverable is the loader + maths with a labelled placeholder (Master Prompt §2 rules 2 & 4; AGENTS.md "implement as configuration with a clearly labelled placeholder"); (2) the weekend convention is config (`[5, 6]`) marked Unverified rather than a code constant, so the "working-day calendar from config" requirement holds and a reviewer can correct it without a deploy; (3) a divergence test binds `calendars().timezone` to `settings.business_timezone` so the two timezone sources cannot silently disagree; (4) `add_working_days` raises `ValueError` when no working day exists instead of hanging — fail loudly beats a stuck sweep; (5) no new DEC entry — follows DEC-0003 (advisory/unverified posture) and the existing policy-as-data pattern from 1.1/1.5–1.8.
- Permission and audit effects: none — no endpoint, so no permission applies and no audit event is written. Pure functions over config; nothing gates a case. When task 2.2 reads the cut-off to *tag the next AY*, that action will need its own permission and audit event (noted for 2.2).
- Verification: exact commands + results:
  - `pytest tests/test_working_calendar.py -q -p no:randomly` → **24 passed** (after implementation; 24 errored first with `ImportError`)
  - `make lint` → `All checks passed!` (first run found 3 real issues: an unused `UTC` import in the service and 2 `timezone.utc` → `UTC` alias suggestions in the tests — all fixed and re-run clean)
  - `make test` → **318 passed, 1 warning in 32.45s** (0 skipped; +24 vs 294)
  - `json.load` re-checked on `calendars.json` after writing (valid).
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose/Postgres.
- Status per requirement touched: Plan 2.1 "`calendars.json` + `working_calendar.py` (IST, holidays, Public Notice dates, Academic Calendar) (FR-37)" — **Implemented · Tested** as configuration + a pure service. FR-37's *load* half is **Partial by design**: the loader and shape are implemented, but **no year is loaded** because no official date exists in any source I may use — loading real dates needs a human to record them (this is the honest state, not a gap I papered over).
- Limitations / assumptions / manual steps:
  - **No Public Notice or Academic Calendar date is loaded.** Every clock that needs a window will answer "not recorded / needs review" until a reviewer fills `calendars.json.years` and records the source in `docs/SOURCES.md`. Nothing here may be treated as an active cut-off.
  - The weekend convention (`Sat`+`Sun`) is **Unverified** — confirm the AICTE/office working week for the applicable year before any deadline depends on it.
  - `business_date()` assumes naive datetimes are UTC (matching `core.clock.to_utc`, i.e. how SQLite values are already normalised) — consistent with existing behaviour, but worth knowing.
  - Timezone divergence is guarded by a test, not by a single source of truth; ideally `settings.business_timezone` would later read from this config. Not changed here (would touch `config.py`/`deadline_service` — out of task scope).
  - The synthetic test fixture uses year 2099 deliberately so it can never be mistaken for real data.
- Related bugs: none (no BUG entry — the 3 lint findings and my 2 wrong test assertions were caught and fixed within the task before the final green run; the service itself never misbehaved).
- Open questions for a human: (1) What are the official Public Notice dates and the Academic Calendar for the applicable year (cl. 2.2, 2.25)? Owner: regulatory reviewer — required before FR-37 can be *loaded*, and before task 2.2 can do anything but answer "needs review". (2) Confirm the AICTE working week (weekend days) for the applicable year. Recommended default (implemented, marked Unverified): Saturday+Sunday.
- Next suggested task: Phase 2 **2.2** — `readiness.py`: cut-off check → tag next AY, never reject (FR-02).

### IMPL-0015 — Phase 1.9: route scoreboard endpoint + UI (the Phase 1 exit check)
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 242d5b5 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.9** (AGENT-02); PRD **FR-07** (Table 2.3 routing) — the scoreboard is the visible proof of the 21/21 encoding; also the Phase 1 **exit check**.
- Goal: expose the 21-row Table 2.3 routing catalogue over HTTP and render it in the UI, with a **coverage** count (encoded/expected) so a missing row is visible instead of silently shrinking the table, and confirm the exit check ("scoreboard shows 21/21; audit events for every routing decision").
- What existed before: `routing.py` could list rows and stage lists but nothing assembled them into a scoreboard; `workflow.py` had `GET /workflow/routes` (the four route *keys*, not the 21 Table 2.3 *rows*); the frontend had three views (cases/monitoring/reports) and no routing-table screen.
- What I did:
  - **Tests first** — `backend/tests/test_route_scoreboard.py` (8 tests; all 8 passed on first run against the implementation, because the service was written to satisfy them): the board reports all 21 rows; coverage is exactly `21/21`; the board is `advisory_only` + `unverified`; a known row (Change of Site t23-14) carries its category/route/window/EVC flag and a stage list that matches `stages_for_category()` (evc + shc present); the FN/OCI/Gulf row (t23-08) keeps `evc_not_applicable: true`; every row cites its PRD source row; the endpoint returns the board to an authenticated user; and the endpoint returns **401** with no token (deny by default).
  - **Config** — `table_2_3.expected_rows: 21` (+ note): the PRD's own documented count ("Table 2.3 (21 rows)"), stored as configuration so coverage is a real check (delete a row → `20/21` and the scoreboard flags it) rather than a number hard-coded in the service.
  - **Service** — `routing.scoreboard()`: assembles `{advisory_only, status, total_rows, expected_rows, coverage, rows[], route_patterns, stage_order}`; each row joins its pattern's ordered stages; the category is looked up via the existing `table_2_3_rows()`.
  - **Endpoint** — `GET /workflow/table-2-3-scoreboard` in `api/workflow.py`, gated by `get_access` (authentication only — it exposes no case data, only the public route catalogue, so no per-case permission applies). Thin: returns `routing.scoreboard()`.
  - **Frontend** — `RouteScoreboard.tsx` (new component, loading/error/empty + coverage pill, plain-language wording "how a case would be routed… a guide, not a decision"); `types.ts` `RouteScoreboard`/`RouteScoreboardRow`; `api.ts` `routeScoreboard()`; wired into `App.tsx` as a fourth view `#/routing` ("Routing table"), gated behind `canMonitor` like the other officer reference views. **Markup matched existing conventions** (`panel`/`heading-row`/`report-list`/`pill`) — the first draft used invented `table`/`sr-only`/`stages` classes that do not exist in `styles.css`, caught by grepping `styles.css` before the build and rewritten (no new CSS added).
- Files changed: `backend/rules/workflow_routes.json` (`expected_rows` + note), `backend/app/services/routing.py` (`scoreboard()`), `backend/app/api/workflow.py` (new GET endpoint + `routing` import), `backend/tests/test_route_scoreboard.py` (new, 8), `frontend/src/types.ts` (2 types), `frontend/src/api.ts` (endpoint + import), `frontend/src/components/RouteScoreboard.tsx` (new), `frontend/src/App.tsx` (4th view: type, hash regex, nav button, render branch, import), `md/6_IMPLEMENTATION_PLAN.md` (1.9 ticked), `README.md` + `CONTEXT.md` (286 → 294, suite list), this log.
- Migrations / API / config / rule-file changes: **one new read-only GET endpoint** (`/workflow/table-2-3-scoreboard`); config `expected_rows`; no model, permission or migration change.
- Decisions made: (1) `expected_rows` in config (not hard-coded) so the coverage count is a real integrity check, and 21 is the PRD's documented count not a guess; (2) the endpoint needs authentication but **no per-case permission** — it exposes only the public route catalogue, consistent with `GET /workflow/routes`; (3) the view is gated behind `canMonitor` (officers) rather than shown to institutions, matching where the other reference views sit — a low-risk choice a reviewer can widen; (4) no new DEC entry — follows DEC-0003 (advisory) and existing patterns.
- Permission and audit effects: read-only endpoint, authentication-gated (`get_access`); no case data, so object-level authorisation is not applicable. **No audit event is written for viewing the scoreboard** (a read of public reference data is not a state change). On the exit-check clause "audit events written for every routing decision": the routing decision that exists today — the `route_key` chosen at case creation — is **already audited** (`application.created` writes `after={category, route_key}`, verified in `api/applications.py`); a dedicated "route and stage list recorded per category" event arrives with the stage graph (task 3.1) and is **not** faked here.
- Verification: exact commands + results:
  - `pytest tests/test_route_scoreboard.py -q -p no:randomly` → **8 passed**
  - `pytest tests/test_authz_matrix.py tests/test_route_scoreboard.py` → **29 passed** (the H.3 coverage guard accepts the new route; it is auth-gated, not permission-gated, so it sits outside the permission matrix by design)
  - `make lint` → `All checks passed!`
  - `make test` → **294 passed, 1 warning in 28.09s** (0 skipped; +8 vs 286)
  - `cd frontend && npm run build` → `tsc --noEmit` clean, `vite build` succeeded (51 modules, built in 708ms)
  - Not run: Alembic (no model change), Compose/Postgres, live browser click-through of the new view (the UI was type-checked and built, not manually clicked — noted as not verified).
- Status per requirement touched: Plan 1.9 "`GET` route-scoreboard endpoint + `RouteScoreboard.tsx`" — **Implemented · Tested** (backend) · **Implemented** (frontend, build-verified, not manually clicked). Phase 1 **exit check**: "scoreboard shows 21/21" — **Tested** (`coverage == "21/21"` asserted, both at service and HTTP level); "audit events for every routing decision" — **Partial**: creation-time route is audited (verified); the per-category route/stage-list decision event is deferred to 3.1, not faked.
- Limitations / assumptions / manual steps:
  - The frontend component builds clean but was **not** manually clicked in a browser this run (no `make dev` session). Say "not verified" for the rendered pixels; the data contract is covered by the backend tests.
  - Coverage compares encoded rows to `expected_rows: 21`; if the APH edition changes the row count, a human must update `expected_rows` (it is configuration, by design).
  - The scoreboard is read-only reference data; it does not yet link a row to live cases using that route (that needs the stage graph, 3.1).
- Related bugs: none (no error hit this run; the invented-CSS-class near-miss was caught pre-build and is recorded here rather than as a BUG, since it never reached a failing build).
- Open questions for a human: should the routing table be visible to institution users too (it is public reference data)? Recommended default (implemented): officers only, matching the other reference views — widen later if desired.
- Next suggested task: Phase 1 exit check is now met (scoreboard 21/21; audit-coverage partial, per above). **Phase 1 complete.** Next is **Phase 2** — `calendars.json` + `working_calendar.py` (IST, holidays) (FR-37), per the plan's top-to-bottom order.

### IMPL-0014 — Phase 1.8: fallback-to-EoA branch after "not approved" (FR-11)
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 469e87a (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.8** (AGENT-02); PRD **FR-11** "After 'not approved', open fallback EoA branch"; §6 routing rule 3; APH cl. **2.7l, 2.14j, 2.15e** (cited as the PRD cites them, as a set — not independently verified; same blocked item).
- Goal: model the fallback-to-EoA branch — after a "not approved" outcome on one of the PRD's three categories (new programme/level, Diploma↔Degree conversion, Women's ↔ Co-ed), an EoA for the existing institution may be issued *if requirements are met* — as advisory configuration, without ever issuing or blocking anything automatically.
- What existed before: nothing expressed this branch; the four route patterns and the earlier 1.5/1.6/1.7 additions did not mention a post-decision fallback. Search for `fallback_eoa` / `2.7l` in `backend/` found nothing.
- What I did:
  - **Tests first** — `backend/tests/test_fallback_eoa.py` (9 tests; all 9 first failed with the service absent, then passed): the rule config exists and is `unverified` + `advisory_only`; it carries the three clause numbers as the PRD gives them (as a set, no remapping); the three qualifying categories are listed; a qualifying category with the `rejected` trigger answers **`review_required`** (never an automatic "issue"); a non-qualifying category (Change of Site t23-14, Closure t23-15) answers `not_applicable`; a qualifying category with a clean (`approved`) outcome answers `not_triggered`; an undecided (`None`) or unrecognised outcome answers `review_required` (uncertain, not a silent "no fallback"); `fallback_eoa_applies()` says which categories qualify; and an unknown category raises `KeyError` from both functions (fails loudly).
  - **Config** — `table_2_3.fallback_eoa` (+ `_note`): `{categories: [t23-03, t23-05, t23-16], trigger_outcome: "rejected", trigger_outcome_note, clauses: [2.7l, 2.14j, 2.15e], requirements_condition: "unevaluated_placeholder", status: unverified, advisory_only: true, source: "md/1_PRD.md FR-11 and §6 routing rule 3 (APH cl. 2.7l, 2.14j, 2.15e)"}`. Two deliberate hedges, both recorded in the config: (1) the PRD's phrase "not approved" is mapped **provisionally** to the workflow's existing `rejected` state name (flagged in `trigger_outcome_note` for a regulatory reviewer); (2) the PRD never says which of the three clauses covers which category, so the clauses are stored **as a set** with no clause→category mapping asserted.
  - **Service** — `routing.fallback_eoa_rule()` (raises `KeyError` if the config is deleted, so a missing rule fails loudly rather than answering "no fallback"), `routing.fallback_eoa_applies(category_id)` (validates the category against the Table 2.3 rows first), and `routing.fallback_eoa_status(category_id, outcome) -> "review_required" | "not_applicable" | "not_triggered"`. The uncertainty branch runs before the clean "no" so a `None`/unknown outcome can never be read as "no fallback".
- Files changed: `backend/rules/workflow_routes.json` (`fallback_eoa` + note, additive), `backend/app/services/routing.py` (`fallback_eoa_rule()`, `fallback_eoa_applies()`, `fallback_eoa_status()`, `_KNOWN_OUTCOMES`), `backend/tests/test_fallback_eoa.py` (new, 9), `md/6_IMPLEMENTATION_PLAN.md` (1.8 ticked), `README.md` + `CONTEXT.md` (277 → 286, suite list), this log.
- Migrations / API / config / rule-file changes: config only. No model, endpoint, permission or audit change. Nothing yet *opens* the branch in the workflow — the decision points and the "requirements are met" check arrive with Phase 6 (decision authority) and the stage graph (3.1).
- Decisions made: (1) three-valued answer again (`review_required`/`not_applicable`/`not_triggered`) — the PRD's unevaluable "if requirements are met" must not become a silent issue or a silent no (rules 1 + 4); (2) provisional `rejected` mapping for "not approved", recorded as config with a note rather than hard-coded, so a reviewer can correct the vocabulary without a code change; (3) clauses kept as a set because the PRD gives no clause→category mapping — inventing one would breach rule 2; (4) no new DEC entry — follows DEC-0003 (advisory) and the established policy-as-data pattern.
- Permission and audit effects: none — no endpoint, so no permission applies and no audit event is written. When the workflow later opens/consumes this branch (Phase 6), that transition must carry its own permission, reason and audit event.
- Verification: exact commands + results:
  - `pytest tests/test_fallback_eoa.py -q -p no:randomly` → **9 passed** (after implementation; 9 failed first, service absent)
  - `make lint` → `All checks passed!`
  - `make test` → **286 passed, 1 warning in 28.51s** (0 skipped; +9 vs 277)
  - JSON re-validated after the config edit (`json.load` OK).
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose/Postgres.
- Status per requirement touched: Plan 1.8 "Fallback-to-EoA branch after 'not approved' (FR-11)" — **Implemented · Tested** as advisory configuration + a three-valued service lookup. The actual issuance decision is deliberately **not** automated (Proposed, needs a human decision point).
- Limitations / assumptions / manual steps:
  - Advisory only: nothing opens the branch, issues an EoA or blocks a case. `review_required` is the ceiling this service will ever answer for a triggered case — the "requirements are met" check is a placeholder pending a human definition.
  - The `rejected` ↔ "not approved" mapping is provisional (PRD wording vs workflow state name) and is flagged in the config note; a regulatory reviewer should confirm it.
  - Clause citations (2.7l, 2.14j, 2.15e) are the PRD's, not independently verified against the APH edition (blocked item, docs/SOURCES.md); no clause→category mapping is asserted.
  - `_KNOWN_OUTCOMES` (approved/rejected) is the small vocabulary the function treats as "decided"; if Phase 6 adds outcome words (e.g. "approved with conditions"), this set must grow with it — noted as follow-up for 6.x.
- Related bugs: none (no error hit this run).
- Open questions for a human: (1) confirm "not approved" maps to the workflow's `rejected` state (recommended provisional default already in config). (2) What are the actual "requirements" whose satisfaction gates the fallback EoA? The PRD does not enumerate them — a regulatory reviewer must supply them before this can ever issue anything. Owner: regulatory reviewer.
- Next suggested task: Phase 1 **1.9** — `GET` route-scoreboard endpoint + `RouteScoreboard.tsx` (the Phase 1 exit check needs the 21/21 scoreboard visible).

### IMPL-0013 — Phase 1.7: the "AA" gate — SHC/SAC opens only on a deficiency or negative outcome
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 2b4411d (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.7** (AGENT-02); PRD **FR-10** "Open SAC/SHC only on deficiency or negative outcome" (Table 2.3); §6 SCR+EVC+AA pattern note ("AA" = as applicable); FR-14 for the result vocabulary.
- Goal: give the SCR+EVC+AA route's `shc` stage (already marked `when: if_deficiencies` by task 1.2) a real answer to "is SHC due for this case?" — open, closed, or needs review — driven by configuration, with missing data never becoming a guessed open or closed.
- What existed before: the four route patterns already carried `shc` with `when: if_deficiencies` (`workflow_routes.json::table_2_3.route_patterns`), and `routing.py` could list/merge stage conditions, but nothing evaluated a condition against a case's actual scrutiny result or open-deficiency count, and no config said what "deficiency or negative outcome" means in words the engine can compare.
- What I did:
  - **Tests first** — `backend/tests/test_aa_gate.py` (8 tests; all 8 first failed with the service absent, then passed once implemented): the gate config exists and is `unverified` + `advisory_only`; it cites FR-10 in its `source`; a clean result (`nil_deficiency`) with zero open deficiencies keeps the gate **closed**; an open deficiency opens it even with a clean result (the two conditions are OR'd, per FR-10's "or"); a negative result (`deficiency`) opens it on its own; an undecided result (`None`) is **never** a guessed open or closed — it answers `needs_review` (both with and without deficiencies); an unrecognised result outside the configured vocabulary is treated as uncertain, not as a pass; and the result vocabulary itself comes from config (`scrutiny_results.clean` / `.negative`), not from a hard-coded assumption.
  - **Config** — `table_2_3.aa_gate` (+ `_note`): `{opens_on: [deficiency, negative_outcome], scrutiny_results: {clean: [nil_deficiency], negative: [deficiency]}, undecided_result: needs_review, unrecognised_result: needs_review, status: unverified, advisory_only: true, source: "md/1_PRD.md FR-10 (Table 2.3) and §6 SCR+EVC+AA pattern note"}`. The `nil_deficiency` / `deficiency` words are PRD FR-14's own wording ("Nil Deficiency / Deficiency"), not invented regulatory vocabulary.
  - **Service** — `routing.aa_gate()` (raises `KeyError` if the config is missing, so a deleted gate fails loudly rather than silently answering "closed") and `routing.aa_stage_is_due(scrutiny_result, deficiencies_remaining) -> "open" | "closed" | "needs_review"`. The uncertainty branch is evaluated **first**, before the open/closed logic, so an unknown or absent result can never fall through into a clean verdict.
- Files changed: `backend/rules/workflow_routes.json` (`aa_gate` + note, additive), `backend/app/services/routing.py` (`aa_gate()`, `aa_stage_is_due()`), `backend/tests/test_aa_gate.py` (new, 8), `md/6_IMPLEMENTATION_PLAN.md` (1.7 ticked), `README.md` + `CONTEXT.md` (269 → 277, suite list), this log.
- Migrations / API / config / rule-file changes: config only. No model, endpoint, permission or audit change. The stage graph that will *consume* this answer arrives with task 3.1; until then this is a lookup, exactly like 1.5/1.6.
- Decisions made: (1) three-valued answer (`open`/`closed`/`needs_review`) rather than a boolean, because rule 4 forbids a guessed pass/fail on missing data and a boolean would force one; (2) the uncertainty branch runs first so an unrecognised result can never be read as "clean" (defensive ordering); (3) no new DEC entry — follows DEC-0003 (advisory) and the existing policy-as-data pattern. The `when: if_deficiencies` marker from 1.2 is unchanged; `aa_stage_is_due` interprets it, it does not replace it.
- Permission and audit effects: none — no endpoint, so no permission applies and no audit event is written. When the stage graph (3.1) consumes this to open/close SHC, that transition must carry its own permission and audit event — noted for 3.1.
- Verification: exact commands + results:
  - `pytest tests/test_aa_gate.py -q -p no:randomly` → **8 passed** (after implementation; 8 failed first, service absent)
  - `make lint` → `All checks passed!`
  - `make test` → **277 passed, 1 warning in 27.41s** (0 skipped; +8 vs 269)
  - JSON re-validated after the config edit (`json.load` OK).
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose/Postgres.
- Status per requirement touched: Plan 1.7 "'AA' gate: SHC/SAC opens only on deficiency or negative outcome (FR-10)" — **Implemented · Tested** as advisory configuration + a three-valued service lookup.
- Limitations / assumptions / manual steps:
  - Advisory only: nothing opens or blocks SHC yet; the stage graph (3.1) must consult this and still needs a human decision point.
  - The gate reads a *scrutiny result* and an *open-deficiency count* supplied by the caller; it does not itself query the database, so correctness of the inputs is the caller's responsibility (kept pure for testability, matching `unmet_prerequisites`).
  - FR-10's "negative outcome" is interpreted here as a negative *scrutiny result* (`deficiency`). Whether other outcomes (e.g. an EVC report flagging problems, cl. 2.3.5b / FR-22) should also open the gate is not decided — that is a regulatory reading a human should confirm.
  - Clause/FR citations are the PRD's, not independently verified against the APH edition (blocked item, docs/SOURCES.md).
- Related bugs: none (no error hit this run).
- Open questions for a human: does a negative **EVC** finding (FR-22, fraudulent-document flag) count as a "negative outcome" that opens the AA gate, or only the scrutiny result? Recommended default (not implemented): keep it scrutiny-only until a human confirms, to avoid widening the gate on unverified reading. Owner: regulatory reviewer.
- Next suggested task: Phase 1 **1.8** — fallback-to-EoA branch after "not approved" (FR-11).

### IMPL-0012 — Phase 1.6: additional-EVC actions — random EVC for SD, second EVC after site shift
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / fd9affa (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.6** (AGENT-02); PRD **FR-19** (authorised user adds random EVC; schedule second EVC after site shift); §6 routing rules 1 and 5; APH cl. **2.3.5** and **2.17e** (cited as the PRD cites them; not independently verified — same blocked item as 1.5).
- Goal: model the two ways a case reaches an EVC visit *outside* its route's standard stages — an authorised user pulling a self-disclosure (SD) case into the EVC queue (2.3.5), and a second EVC judged needed after movable property is shifted on a Change of Site (2.17e) — as advisory configuration a future workflow can consult, without inventing an authority or letting anything gate a case.
- What existed before: `table_2_3` had the 21 rows, the four PRD §6 patterns, `stage_order` and `sequencing_rules` (1.5); `routing.py` answered stage lists, unions and sequencing prerequisites. Nothing expressed "this case could get an extra EVC visit"; the `evc` stage simply appears in a route's list when the pattern says so.
- What I did:
  - **Tests first** — `backend/tests/test_additional_evc.py` (9 tests, all passed on first run against the implementation): the two action ids exist; `random_evc` applies to both SD categories (t23-01, t23-02) via the route pattern; `second_evc_after_site_shift` applies to Change of Site (t23-14) via an explicit category id; a category with neither action answers `[]` (never a guess); an unknown category raises `KeyError` from the lookup (fails loudly, matching `prerequisites_for`); both actions are `unverified` + `advisory_only`; each cites its clause (2.3.5 / 2.17e) so no clause can be invented silently; the second EVC's trigger is the property shift; and — critically — **no role is silently authorised**: `authorised_roles` is `[]` with `authorised_roles_status: unverified_placeholder` because PRD open question #4 ("Which roles may add a random EVC?") has no recorded answer. (All 9 initially failed with the service absent, then passed — failure-then-pass, not a first-try miracle.)
  - **Config** — `table_2_3.additional_evc_actions` (+ `_note`): two policy-as-data rows, each `{action_id, title, applies_to{route_pattern | category_ids}, trigger, authorised_roles, authorised_roles_status, status, advisory_only, source, note}`. `random_evc` keys off the **route pattern** `SD` (so it covers both SD rows, not one hard-coded id); the second EVC keys off the **category id** `t23-14`. Both carry `status: unverified`, `advisory_only: true`, and a note explaining the empty-authority placeholder.
  - **Service** — `routing.additional_evc_actions()` (the configured list) and `routing.evc_actions_for_category(category_id)` (which actions apply), with a small `_evc_action_applies` helper; the category is validated via `route_pattern()` first so an unknown id raises `KeyError` rather than answering "no actions".
- Files changed: `backend/rules/workflow_routes.json` (`additional_evc_actions` + note; 33-line additive diff, no reformatting), `backend/app/services/routing.py` (two public functions + helper), `backend/tests/test_additional_evc.py` (new, 9), `md/6_IMPLEMENTATION_PLAN.md` (1.6 ticked), `README.md` + `CONTEXT.md` (260 → 269, suite list), this log.
- Migrations / API / config / rule-file changes: config only. **No** model, endpoint, permission or audit change — the workflow still cannot *execute* either action; this is the same advisory posture as 1.5 (DEC-0003: nothing from Table 2.3 may gate a case until a human verifies the clause and, here, the authority).
- Decisions made: (1) route-pattern matching for the random EVC rather than a hard-coded category list, so all SD rows inherit it and a future SD row is covered automatically; (2) `authorised_roles` left empty with an explicit `unverified_placeholder` status rather than guessing "regional officer" — PRD §19 #4 is an open question, and inventing an authority would breach Master Prompt §2 rule 2 and AGENTS.md ("who may add a random EVC" → labelled placeholder, move on); (3) no new DEC entry needed — follows DEC-0003 (advisory) and the established policy-as-data pattern from 1.1/1.5.
- Permission and audit effects: none — no endpoint exists, so no permission applies and no audit event is written for a lookup. When the workflow later consumes these actions (a real "add EVC" transition), that transition must carry its own permission, reason and audit event — noted as follow-up for Phase 6.1/6.2.
- Verification: exact commands + results:
  - `pytest tests/test_additional_evc.py -q -p no:randomly` → **9 passed** (after implementation; 9 failed first, service absent)
  - `make lint` → `All checks passed!`
  - `make test` → **269 passed, 1 warning in 26.36s** (0 skipped; +9 vs 260)
  - JSON validity re-checked after the config edit (`json.load` OK); diff is 33 added lines, nothing removed.
  - Not run: `npm run build` (no frontend change), Alembic (no model change), Compose/Postgres.
- Status per requirement touched: Plan 1.6 "Random EVC add for SD (2.3.5) and second EVC after site shift (2.17e) as authorised actions" — **Implemented · Tested** as advisory configuration and a service lookup. The "authorised" half is **Unverified/Proposed** on purpose: the authority is a placeholder pending a human answer (open question).
- Limitations / assumptions / manual steps:
  - Advisory only: nothing schedules or blocks a visit; this records *eligibility for an authorised action*, never the action itself. Enforcement arrives with Phase 6.1/6.2 once a human records who may act.
  - The clause citations (2.3.5, 2.17e) are the PRD's, not independently verified against the APH edition (blocked item, docs/SOURCES.md).
  - `authorised_roles` is empty by design. If a reviewer fills it in, a matching server-side permission and an audit event must be added with it — do not treat the placeholder as "any officer may act".
  - Related PRD item deliberately not done here: **FR-21** (block an additional EVC until the additional TER fee is paid, cl. 2.3.2c) is P1 and needs `fee_engine.py` (Phase 9.3) — no fee is modelled or hard-coded in this task.
- Related bugs: none (no error hit this run).
- Open questions for a human: (1) PRD §19 #4 — which roles may add a random EVC / order a second EVC? Owner: regulatory reviewer. (2) Should the second EVC be *required* or *optional* after a site shift (PRD says "may be needed")? Recommended default: optional, officer-judged, recorded with a reason.
- Next suggested task: Phase 1 **1.7** — "AA" gate: SHC/SAC opens only on deficiency or negative outcome (FR-10).

### IMPL-0011 — Phase 1.5: sequencing rule — Women's conversion clears before the merger starts
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / d766bba (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.5** (AGENT-02); PRD **FR-08** sequencing rules; §6 routing rule 4, APH cl. **2.13.1m** (clause cited as the PRD cites it; not independently verified — same blocked item).
- Goal: on a combined application that asks for both a Women's Institution ↔ Co-ed conversion (t23-16) and a Merger of Institutions (t23-06), the merger category reports itself blocked until the conversion category has a clearing outcome.
- What existed before: `ApplicationItem.outcome` (1.4) stored per-category outcomes, but nothing expressed "this category waits for that one".
- What I did:
  - **Tests first** — `backend/tests/test_sequencing.py` (7 tests, all passed on first run): the merger's prerequisites are exactly `[t23-16]`; categories without a rule (SD, the conversion itself, Change of Site, ODL) have none; the merger is blocked while the conversion is undecided, clears when its outcome is `approved`, and stays blocked on any other outcome (e.g. `rejected`); a prerequisite missing from the outcome map counts as not cleared; a single-category case is never blocked by absent items; an unknown category raises `KeyError` from both functions; the rule itself cites cl. 2.13.1m so no clause can be invented silently.
  - **Config** — `table_2_3.sequencing_rules`: one rule `{category: t23-06, requires: t23-16, clears_with: "approved", source: "md/1_PRD.md §6 routing rule 4 (APH cl. 2.13.1m)", note}` plus a note explaining that `clears_with` is provisional vocabulary until Phase 6 defines the decision points. Policy-as-data, like everything else in the section.
  - **Service** — `routing.sequencing_rules()`, `routing.prerequisites_for(category_id)` (validates the id against the table first, so an unknown category fails loudly instead of answering "no prerequisites"), `routing.unmet_prerequisites(category_id, outcomes)` (a prerequisite counts as cleared only when its recorded outcome equals the rule's `clears_with`; undecided or any other outcome keeps the successor blocked).
- Files changed: `backend/rules/workflow_routes.json` (`sequencing_rules` + note), `backend/app/services/routing.py` (three functions), `backend/tests/test_sequencing.py` (new, 7), `md/6_IMPLEMENTATION_PLAN.md` (1.5 ticked — untracked), `README.md` + `CONTEXT.md` (253 → 260, suite list), this log.
- Migrations / API / config / rule-file changes: config only. No model, endpoint, permission or audit change — the workflow does not yet *enforce* the block (the answer is advisory input for the stage graph in 3.1, per DEC-0003 nothing from Table 2.3 may gate a case yet).
- Decisions made: `clears_with: "approved"` reuses the workflow's existing state name rather than inventing a new outcome value; the rule is data, so a second sequencing rule (e.g. for 2.17e's second EVC, task 1.6) is a config row, not code. Flagged as provisional in the config note and below.
- Permission and audit effects: none (pure lookup; no endpoint).
- Verification: exact commands + results:
  - `pytest tests/test_sequencing.py -q -p no:randomly` → **7 passed** (first run)
  - `make lint` → `All checks passed!`
  - `make test` → **260 passed, 1 warning in 26.40s** (0 skipped; +7 vs 253)
  - Not run: `npm run build`, Alembic (no model change), Compose.
- Status per requirement touched: Plan 1.5 "Sequencing: Women's conversion before merger (2.13.1m)" — **Implemented · Tested** (as advisory configuration; enforcement arrives with the stage graph).
- Limitations / assumptions / manual steps:
  - Advisory only: nothing yet stops an officer from advancing a merger — the check is a service answer, not a workflow gate (by design until the clause is verified; PRD §0).
  - `clears_with: "approved"` is provisional — Phase 6 (decision authority) must confirm the outcome vocabulary; a human should confirm whether "approved with conditions" also counts as clearing.
  - The clause 2.13.1m citation is the PRD's, not independently verified against the APH edition (blocked item, docs/SOURCES.md).
- Related bugs: none.
- Open questions for a human: should "approved with conditions" (once defined) count as clearing for sequencing? Owner: regulatory reviewer.
- Next suggested task: Phase 1 **1.6** — random EVC add for SD (2.3.5) and second EVC after site shift (2.17e) as authorised actions.

### IMPL-0010 — Phase 1.4: combined applications — `ApplicationItem`, stage union, per-category outcome
- Date / agent / branch / commit: 2026-10-26 / MiMo (OpenCode agent, MiMo-V2.6) / master / 1c50cd0 (work uncommitted at implementation)
- Task ID and PRD IDs: Phase 1 **1.4** (AGENT-02); PRD **FR-08** (combined applications, per-category outcomes, sequencing rules) and routing rule 2 ("route = union of needed stages; outcome recorded per category").
- Goal: let one case carry several Table 2.3 categories — each with its own recorded outcome — and compute the union of the stages its categories need, in the PRD's flow order.
- What existed before: `Application.category` holds a single string; nothing modelled multiple categories per case; `routing.py` answered per one category only.
- What I did:
  - **Tests first** — `backend/tests/test_combined_applications.py` (8 tests): SD+SCR union interleaves `nil_deficiency_report` and `scrutiny` in canonical flow order; single-category union is that category's list; duplicate categories don't duplicate stages; conditional stages keep their gate in the union (`shc` stays `if_deficiencies`); unknown category raises `KeyError`; per-category outcome rows are independent (one approved, one still None); the same category cannot be added to one application twice (unique constraint → `IntegrityError`); deleting an application removes its items (FK `ON DELETE CASCADE` + ORM `delete-orphan`). All 8 passed on first run.
  - **Model** — `ApplicationItem` in `app/models/application.py`: `application_id` (FK CASCADE), `category_id` (`t23-01`…), `route` (copied from the category's pattern so a case history survives later table edits), `outcome` + `outcome_recorded_at` (nullable — per-category verdict, None until that category is decided), `created_at`; unique `(application_id, category_id)`; exported from `app.models`.
  - **Migration 0009** — autogenerate draft restyled to house conventions (revision `0009_application_items`, dated docstring). `sql/roles.sql` needs no change: grants are `ON ALL TABLES IN SCHEMA public`.
  - **Union** — `routing.stages_for_categories(category_ids)`: stages from every category, merged by name, ordered by the new config key `table_2_3.stage_order` (readiness → nil_deficiency_report → scrutiny → evc → shc → executive_decision → appeal_window → grant, transcribed from PRD §7); if categories disagree about a stage's condition the **most restrictive** wins (a gate one category requires must not be widened by another category listing the same stage); a `stage_order` that is missing a used stage raises `KeyError` rather than producing a wrong order.
- Files changed: `backend/app/models/application.py` (`ApplicationItem`, `Application.items`), `backend/app/models/__init__.py` (export), `backend/app/services/routing.py` (`stages_for_categories`, `stage_order`, `_WHEN_RANK`), `backend/rules/workflow_routes.json` (`stage_order` + note), `backend/migrations/versions/0009_application_items.py` (new), `backend/tests/test_combined_applications.py` (new, 8), `md/6_IMPLEMENTATION_PLAN.md` (1.4 ticked — untracked), `README.md` + `CONTEXT.md` (245 → 253, suite list), this log.
- Migrations / API / config / rule-file changes: migration 0009 (new table); config `stage_order`; **no API change** — nothing yet creates items or reads the union through HTTP (that comes with the stage graph in 3.1 and the workflow wiring); no permission/route change.
- Decisions made: `route` is denormalised onto the item so the category→route decision is frozen at case creation (audit-friendly, survives config edits); union condition-merge is "most restrictive wins" — conservative by design for an advisory engine. No new DEC entry needed: both follow DEC-0003 (advisory) and the existing policy-as-data pattern.
- Permission and audit effects: none — the table is not exposed by any endpoint yet, so no permission applies and no audit event is written for item creation (endpoint + audit come when the workflow consumes items; noted for 3.1).
- Verification: exact commands + results:
  - `pytest tests/test_combined_applications.py -q -p no:randomly` → **8 passed** (first run)
  - `alembic upgrade head` (fresh `/tmp/sih26262-migrate.db`) → 0008 → 0009 applied; `alembic check` → **`No new upgrade operations detected.`**; downgrade to 0008 and re-upgrade both succeed
  - `make lint` → `All checks passed!`
  - `make test` → **253 passed, 1 warning in 26.58s** (0 skipped; +8 vs 245)
  - Not run: `npm run build` (no frontend change), Compose/Postgres (migration uses only String/DateTime/unique-constraint primitives; Postgres run is Phase 10.1).
- Status per requirement touched: Plan 1.4 "`ApplicationItem` model + migration" — **Implemented · Tested**; "union of stages" — **Implemented · Tested**; "per-category outcome (FR-08)" — **Implemented · Tested** (storage + independence; the *recording* endpoint arrives later).
- Limitations / assumptions / manual steps:
  - No endpoint yet to add categories to a case or record a per-category outcome; seeded single-category cases have no items (the workflow's consumption of items is 3.1+). Sequencing rules (1.5) are not yet applied to the union order beyond the canonical flow order.
  - `outcome` vocabulary is an unconstrained string until the decision points exist (Phase 6); the column is deliberately nullable, not defaulted.
  - Migration verified on SQLite only; Postgres in Phase 10.1.
- Related bugs: none.
- Open questions for a human: none new (per-category outcome *values* will need the Phase 6 decision-authority gate).
- Next suggested task: Phase 1 **1.5** — sequencing: Women's conversion before merger (2.13.1m).

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
