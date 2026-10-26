# AGENTS.md  (copy to repo root; also save as CLAUDE.md or make CLAUDE.md contain `@AGENTS.md`)

House rules for any coding agent working in `sih26262`.

## Read first, in this order
1. `CONTEXT.md` (repo state, demo logins, current build order) and `things.md` (next feature).
2. `docs/prd/1_PRD.md` — what to build.
3. `docs/prd/3_ARCHITECTURE_ESSENTIALS.md` — rules you must not break.
4. `docs/prd/2_ARCHITECTURE.md` — how it fits together.
5. `docs/prd/6_IMPLEMENTATION_PLAN.md` — pick the **first unchecked task**. Do only that.

## Commands
```
make setup            # one-time: venv, packages, config, demo SQLite DB (safe to re-run)
make dev              # API :8000 + UI :5173
make lint             # ruff check app tests migrations scripts
make test             # backend pytest
make seed             # idempotent demo data
make up / make reset  # Docker: Postgres + API + worker + frontend
make smoke            # end-to-end API check against Compose stack
make verify-isolation # Postgres role contract proof
cd frontend && npm run build   # tsc --noEmit + vite build
# Migrations
cd backend && ../.venv/bin/alembic revision --autogenerate -m "msg"
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic upgrade head
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic check
```
Demo password for all seeded accounts: `DemoPassw0rd!` (synthetic only).

## Before editing anything (mandatory)
Confirm repo root and branch; read README, `CONTEXT.md`, this file; inspect manifests, lockfiles, tests; **search for existing behaviour** before adding code; inspect routes, services, models, schemas and migrations; run baseline tests if possible; report what exists and what the gaps are *first*. Never invent dependency versions: read the manifests. Recheck every "reported" path in the docs: `backend/app/api/workflow.py`, `services/workflow_service.py`, `services/case_assignment_service.py`, `services/deadline_service.py`, `core/permissions.py`, `services/authorization_service.py`, `rules/workflow_routes.json`, `rules/deadline_policy.json`, `frontend/src/components/EvidencePanel.tsx`. Some may be named differently in the repo.

## Task IDs (use these in plans and reports)
`AGENT-01` repository audit (prefer no code changes; deliver a gap matrix) · `AGENT-02` workflow hardening · `AGENT-03` document access/versioning · `AGENT-04` OCR adapter · `AGENT-05` compliance engine · `AGENT-06` deficiency/resubmission · `AGENT-07` assignment/COI (only if approved) · `AGENT-08` deadlines/notifications · `AGENT-09` dashboards/reports · `AGENT-10` audit/observability · `AGENT-11` frontend integration · `AGENT-12` E2E/demo. Full acceptance and tests per task are in `6_IMPLEMENTATION_PLAN.md`.

## Logging (mandatory, every task)
Two append-only files, newest entry first, never edit or delete old entries (add an Amends/Supersedes/Update line):
- **`docs/IMPLEMENTATION_LOG.md`**: every decision (`DEC-####`) and every piece of implementation work (`IMPL-####`): task and FR IDs, what existed, what you did, files changed, migrations/API/config changes, permission and audit effects, exact verification commands and results, limitations, open questions, next task.
- **`docs/BUG_LOG.md`**: every error, failed test or command, regression or environment problem (`BUG-####`), logged **when it happens**: expected vs actual, trimmed redacted error text, repro steps, environment, hypotheses tried (including failed ones), **root cause, solution applied and why**, verification, and the regression test added. `Fixed` needs a root cause and a passing test; otherwise `Workaround` or `Open`.
Read both files before starting a task. Link IMPL ↔ BUG ↔ DEC by ID. No secrets, tokens, connection strings, personal data or document contents. Templates: `docs/prd/8_IMPLEMENTATION_LOG_TEMPLATE.md`, `docs/prd/9_BUG_LOG_TEMPLATE.md`. S1 bugs (audit integrity, authz, secrets, wrong regulatory outcome, model changing state) must also be reported to a human immediately.

## Workflow for every task
1. State the task and the PRD IDs it satisfies (e.g. FR-07, FR-09).
2. Read the code you will touch before editing. Prefer extending existing services over new ones.
3. Write or update tests **first or alongside**. Use the fixed clock and seeded data.
4. Implement the smallest change that passes. Keep routers thin, logic in `services/`.
5. Run `make lint && make test`. If you touched models: Alembic migration + `alembic check`. If you touched frontend: `npm run build`.
6. Write the IMPL/DEC entries and any BUG entries (see Logging), then tick the checkbox in the Implementation Plan, add one line to `CONTEXT.md` if repo state changed, and summarise what you did and anything you could not verify.

## Do
- Follow `3_ARCHITECTURE_ESSENTIALS.md` exactly.
- Keep the change small and reviewable; one plan task per commit.
- Match existing naming and file layout. Search for an existing pattern before inventing one.
- Put new rules/routes/deadlines/fees in `backend/rules/` or settings as dated configuration.
- Write audit events for every state change and rejected action.
- Use `adapters/` Protocols for anything external, with a mock.

## Do not
- Do not let AI/OCR decide, approve, reject, return or block anything.
- Do not hard-code routes, fees, deadlines, thresholds or clause numbers. Do not invent APH clauses.
- Do not use `eval`/`exec`, `datetime.now()`, raw runtime DDL, or the API DB role for rehearsal.
- Do not edit or delete audit rows, or edit approved rule versions.
- Do not populate Rehearsal Load Factor.
- Do not add dependencies (Python or npm) without asking. Specifically no Tailwind, UI kit, react-router, axios, react-query, icon library, bcrypt/passlib usage.
- Do not commit secrets, real institution documents or real personal data.
- Do not turn on ClamAV, external model fallback, or a non-mock notifier by default.
- Do not refactor unrelated code or reformat files you are not changing.
- Do not claim something works unless you ran it. Say "not verified" instead.
- Do not activate placeholder rules (RULE-E01…SITE/LEASE) as official; mark them Unverified until a clause is recorded.
- Do not make files public or loosen authorisation "for convenience"; do not trust client-supplied role/scope.

## When requirements are ambiguous
- Check the PRD "Open questions" (§19). If the question is listed there, **implement it as configuration with a clearly labelled placeholder** (e.g. stage-limit days) and move on.
- If it is not listed and the choice changes behaviour users or officers would notice, **stop and ask one specific question** with your recommended default.
- If it only affects internals, choose the simplest option consistent with Essentials and note the assumption in your summary.
- If the PRD and the repo disagree, prefer the repo's safety constraints, flag the conflict, and do not silently rewrite either.

## Human approval gates (stop and ask)
Ambiguous regulatory interpretation · new regulatory routes/states · official deadlines/penalties/fees · external AI processing · role authority changes · destructive migrations · third-party integrations · decision-authority changes. Never send real documents to an external service. Never autonomously approve or reject. Never change remotes or push without confirming repository ownership and access.

## Completion report (every task)
Task ID · summary · log entry IDs · files changed · existing code reused · API/schema/config changes · permission and audit effects · **exact test commands and results** · skipped tests and why (skipped ≠ passed) · limitations · manual steps · open questions · **actual `git status`**.

## Multi-agent coordination
Agree shared interfaces **before** parallel work: states/actions, role/scope vocabulary, document/version IDs, finding/deficiency schema, error format, audit schema, rule format, API contracts. One branch per coherent task; focused commits; one designated owner for shared interfaces; never let two agents redefine a shared schema. Resolve conflicts by behaviour and tests, not by accepting a side. Targeted tests after each merge, full regression before release. A feature counts as integrated only when API, schema and UI agree, migrations apply, authz and audit are tested, failure paths work, tests/build pass, docs match, limitations are recorded.

## Definition of done
Tests pass (`make lint`, `make test`, plus `npm run build` if UI), migrations in sync, audit events written, **IMPL/DEC/BUG log entries written**, no Essentials rule broken, plan checkbox ticked, summary lists changed files and unverified items.

## Style
Python: ruff config in `backend/ruff.toml`, type hints everywhere, small functions. TypeScript: strict, no `any` without a comment. Comments explain *why*, not *what*. UI copy is plain and neutral.
