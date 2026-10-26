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

## Workflow for every task
1. State the task and the PRD IDs it satisfies (e.g. FR-07, FR-09).
2. Read the code you will touch before editing. Prefer extending existing services over new ones.
3. Write or update tests **first or alongside**. Use the fixed clock and seeded data.
4. Implement the smallest change that passes. Keep routers thin, logic in `services/`.
5. Run `make lint && make test`. If you touched models: Alembic migration + `alembic check`. If you touched frontend: `npm run build`.
6. Tick the checkbox in the Implementation Plan, add one line to `CONTEXT.md` if repo state changed, and summarise what you did and anything you could not verify.

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

## When requirements are ambiguous
- Check the PRD "Open questions" (§19). If the question is listed there, **implement it as configuration with a clearly labelled placeholder** (e.g. stage-limit days) and move on.
- If it is not listed and the choice changes behaviour users or officers would notice, **stop and ask one specific question** with your recommended default.
- If it only affects internals, choose the simplest option consistent with Essentials and note the assumption in your summary.
- If the PRD and the repo disagree, prefer the repo's safety constraints, flag the conflict, and do not silently rewrite either.

## Definition of done
Tests pass (`make lint`, `make test`, plus `npm run build` if UI), migrations in sync, audit events written, no Essentials rule broken, plan checkbox ticked, summary lists changed files and unverified items.

## Style
Python: ruff config in `backend/ruff.toml`, type hints everywhere, small functions. TypeScript: strict, no `any` without a comment. Comments explain *why*, not *what*. UI copy is plain and neutral.
