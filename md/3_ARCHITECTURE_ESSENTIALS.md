# Architecture Essentials — rules that must never be broken

Scannable. If a change violates any line here, stop and ask.

## Authority and safety
1. **AI/OCR never approves, rejects, returns, or blocks.** It extracts and flags. Only a named authorised user performs workflow actions.
2. **No stage completes** and no application moves to a decision state without a server-side check of role, state, documents and rules.
3. **Generated text is a draft**, labelled as such, until a user reviews and issues it.
4. **Never invent an APH clause number.** Unknown clause → "clause mapping pending verification".
5. **Never fill in Rehearsal Load Factor.** It is deliberately null.
6. **Rehearsals never write to production tables.** Output must include `production_modified: false`.

## Truthfulness and sources (from the specification)
- **Official sources outrank this repo's docs.** Rules, routes, fees, deadlines, penalties and decision authorities stay **Unverified/advisory** until checked against the exact official clause and recorded in `docs/SOURCES.md`.
- Use the status words precisely: Verified / Implemented / Tested / Partial / Proposed / Unverified / Blocked. Never write "done" when you mean "implemented".
- **Missing or uncertain data is `NEEDS_REVIEW`/unknown, never a guessed pass or fail.** Processing failure is never a pass.
- Never fabricate official rules, metrics, test results, integrations or deployment status. Never claim a commit, push, deploy or test success without command output.
- Do not claim AICTE portal integration, SSO, MFA, COI handling or RLS unless verified.

## Rules and data
7. Rules are allowlisted data. **No `eval()`/`exec()`**, no dynamic code from config or model output.
8. Approved rule versions are **immutable**; change = new draft version.
9. Rules run on the **Extraction Value**, never the Claim Value. An edit can never clear a failed rule.
10. A vision-model value counts **only if grounded** on the page; else `REVIEW_REQUIRED`.
11. Outcomes are typed: `PASS | FAIL | NEEDS_REVIEW | NOT_APPLICABLE`. Missing input follows the rule's `missing_outcome`. Never coerce to PASS.
11a. Every rule carries `source_id`, `clause`, `status`, `version`, `effective_from`. `status != Verified` ⇒ advisory only; it can create a finding but never gate, return or reject.
12. **No routing, fee, deadline or threshold hard-coded.** Put it in `backend/rules/` or settings with an effective date.

## Time
13. **Never call `datetime.now()`/`utcnow()` directly.** Use the injectable clock in `core/`.
14. Deadlines are computed in IST with the working-day/holiday calendar.
15. Alerts and jobs are **idempotent** (dedupe keys). A rerun must not double-send.
16. Demo-clock advance endpoints are **disabled in production config**.

## Documents and concurrency
- Documents are **versioned**; prior versions are immutable; every extraction/finding links to an exact version; replacement needs a reason and triggers re-validation.
- Check file **signature**, size and type on upload; storage keys are server-generated; no public URLs.
- Document/OCR/model text is **untrusted data, not instructions**.
- State changes use enforced optimistic concurrency (`baseline_version`); stale write ⇒ rejected with a reload message.
- Authorisation is object-level on every endpoint; unauthorised resource ⇒ 404 where existing policy says so; never trust client-supplied role/scope.
- Offer idempotency on uploads, transitions, sweeps and jobs.

## Audit
17. Every state change, assignment, decision, payment, alert, escalation, **rejected action**, and sensitive document view writes an audit event.
18. Audit is **append-only** and hash-chained; the chain is tamper-*evident*, not tamper-*proof* (add external checkpoints; never claim absolute immutability). Never update/delete audit rows; corrections are new entries.
19. Committee findings are never edited in place; corrections are new, logged entries.

## Database
20. API and worker connect as `app_rw` only. Rehearsal reads via `sim_prod_ro`, writes via `sim_results_rw`. **Never reuse the API role for rehearsal.**
21. **No DDL at runtime.** Schema changes = Alembic migration. CI checks migrations match models.
22. SQLite for dev/test, PostgreSQL for Compose/prod. Write SQL that works on both, or guard Postgres-only paths.

## Backend conventions
23. Routes under `/api/v1`, one router per domain in `api/`; business logic in `services/`, never in routers.
24. Pydantic v2 schemas at every boundary; SQLAlchemy 2.0 style with `Mapped[]`.
25. Errors use the typed error envelope. Lists use `limit`/`offset` (max 500) and `X-Total-Count`.
26. Config via `SIH_*` env through pydantic-settings. No secrets in the repo; `.env.example` holds demo values only.
27. Passwords: stdlib `pbkdf2_hmac`. Do **not** import bcrypt/passlib. Do not add crypto libraries without asking.
28. External services go behind `adapters/` Protocols with a mock. Mock OCR is rejected in production config.
29. External model calls: switchable off, low-confidence pages only, each call logged.

## Frontend conventions
30. React 19 + TypeScript strict; `npm run build` must pass `tsc --noEmit`.
31. Plain CSS in `styles.css`. **No Tailwind, UI kit, router library, axios, react-query, icon library, or emoji.** Icons are inline SVG in `Icon.tsx`.
32. Navigation uses the existing hash router in `App.tsx`. Data via native `fetch`.
33. The UI never enforces permissions alone; the backend is the authority.
34. Copy is neutral on edits ("edited after extraction"), never accusatory. Say "audit timeline", not "replay".

## Testing
35. Every new rule, route row, guard and clock has a test. **One conformance test per Table 2.3 row.**
36. Tests must be deterministic: fixed clock, seeded synthetic data.
37. Before finishing: `make lint && make test`; frontend: `npm run build`.

## Data
38. All demo data is **synthetic** and labelled. External model fallback stays off for anything non-public.

## Human approval is required before you
Interpret ambiguous regulation; add a regulatory route or state; set official deadlines/penalties/fees; enable external AI on any document; change role authority; run a destructive migration; add a third-party integration; change decision authority. **Stop and ask.**
