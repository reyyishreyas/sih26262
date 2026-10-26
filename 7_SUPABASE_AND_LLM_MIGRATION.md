# Addendum: Supabase database + LLM provider chain

Overrides the matching parts of `2_ARCHITECTURE.md` and `3_ARCHITECTURE_ESSENTIALS.md`. Supabase specifics (pooler ports, username format, Data API behaviour) change over time: **verify against current Supabase docs before each step.**

## A. Supabase as the database

### What stays the same
- It is plain PostgreSQL. SQLAlchemy, Alembic, psycopg, the immutability trigger and the hash-chained audit all work unchanged.
- **We use Supabase only as managed Postgres.** Keep our own auth (PBKDF2 + JWT). Do not adopt Supabase Auth, Realtime or Edge Functions.
- Keep the four-role contract (`sih_migrator`, `app_rw`, `sim_prod_ro`, `sim_results_rw`) and the `sim` schema. `make verify-isolation` must pass against Supabase.

### Connection plan (three connection strings, never the `postgres` superuser at runtime)
| Purpose | Role | Connect via | Notes |
|---|---|---|---|
| Migrations (Alembic) | `sih_migrator` | Direct connection, or session-mode pooler | Direct is IPv6-only on some plans; use session pooler if your network is IPv4 |
| API + worker | `app_rw` | Pooler | Long-running worker: session mode. Serverless/short-lived API: transaction mode |
| Rehearsal baseline | `sim_prod_ro` | Pooler | Read-only |
| Rehearsal results | `sim_results_rw` | Pooler | `sim` schema only |

- Pooler usernames carry the project ref (`role.<project-ref>`). Put full URLs in env only.
- Always `sslmode=require` (or stricter).
- **Transaction-mode pooling does not support server-side prepared statements.** If any URL uses it, set psycopg `prepare_threshold=None` for that engine. Test this before relying on it.
- Size SQLAlchemy pools small (Supabase connection limits are low on small plans); API + worker + rehearsal engines add up.

### Security: do this before anything else
Supabase exposes the `public` schema through its REST Data API using the `anon` and `authenticated` roles. Our tables hold case data.
- [ ] Turn off the Data API for this project, or at minimum `REVOKE ALL` on all `public` and `sim` objects from `anon` and `authenticated`, and set default privileges so new tables stay revoked.
- [ ] Enable RLS on every table as defence in depth (our roles bypass nothing silently: grant the needed policies or use `BYPASSRLS`-free design deliberately, and test).
- [ ] Never ship the service-role key or anon key in the frontend or repo. The frontend talks only to our API.
- [ ] Create roles by running `bootstrap_roles.sql` / `roles.sql` as the Supabase owner; passwords come from env, not the committed dev defaults.
- [ ] Pick the region nearest users (Mumbai if available). Production government data would need AICTE's approval for any third-party host. Prototype stays synthetic-only.

### Files
Local `storage/` will not survive on ephemeral hosting. Options: (1) keep local disk on a persistent volume; (2) Supabase Storage via a new `adapters/storage` Protocol with a local mock. Keep file hashes in the DB either way, and keep virus scanning on the upload path.

### Settings changes
- `SIH_DATABASE_URL` (app_rw), `SIH_MIGRATION_DATABASE_URL` (sih_migrator), `SIH_SIM_BASELINE_URL`, `SIH_SIM_RESULTS_URL`. Reuse the existing variable names where they already exist.
- Production-config validator keeps its rules: non-Postgres rejected, rehearsal roles must differ from the API role. Add: reject URLs without `sslmode=require` in production.
- Docker Compose `db` service stays for local dev; add `docker-compose.supabase.yml` (or an env profile) that removes `db` and points `migrate`/`api`/`worker` at Supabase.

### Data move (prototype data is synthetic, so re-seed instead of dumping)
1. [ ] Create Supabase project; save the connection details in a secret manager/`.env.production` (gitignored).
2. [ ] Run bootstrap SQL to create roles and the `sim` schema.
3. [ ] `alembic upgrade head` as `sih_migrator`; apply `roles.sql` grants.
4. [ ] Seed synthetic data.
5. [ ] Lock down Data API/RLS (checklist above).
6. [ ] `make verify-isolation` and `make smoke` against Supabase.
7. [ ] Add a CI job or documented manual step proving the same checks pass.
If real data ever exists: `pg_dump` data only (schema comes from Alembic), restore as `sih_migrator`, then verify the audit hash chain end to end.

### Backups and ops
Know your plan's backup/PITR coverage; take a periodic `pg_dump` too. Monitor connections and storage. Keep `/health/ready` probing all three roles.

---

## B. LLM provider chain: Gemini → OpenRouter → more

### Principle
The model is only a reader. **Failover must never weaken grounding, schema validation, or the human-decides rule.** Switching provider changes who reads the page, nothing else.

### Design
- Implement the existing unwired `adapters/llm` Protocol with: `GeminiProvider`, `OpenRouterProvider`, and further providers added the same way. A `FallbackLLM` wrapper takes an ordered list from config.
- Config (settings, not code): `SIH_LLM_ENABLED` (master switch, default **off**), `SIH_LLM_PROVIDERS=gemini,openrouter,...`, per-provider model name, API key env var, timeout, max retries. Keys live in env only.
- Candidate backups beyond OpenRouter (pick 1–2, each behind the same Protocol): another direct vendor API (e.g. Anthropic, OpenAI) or a fast-inference host. OpenRouter already fronts many models, so give it a *different* model family than Gemini so a single vendor outage doesn't take both down.
- Last link in the chain is always the **deterministic parser / OCR-only path**, producing `REVIEW_REQUIRED`. The system must work with every LLM down.

### Failover rules
1. Fail over **only** on: timeout, network error, 429, 5xx, auth failure, or output that fails JSON-schema validation. Never fail over because an answer is "unwanted".
2. Per provider: bounded retries with backoff, then a circuit breaker (skip a provider for N minutes after repeated failures). Whole chain has a total time budget.
3. Same prompt, temperature 0, same JSON schema for every provider.
4. **Grounding runs after any provider.** A value not found on the page is `REVIEW_REQUIRED` regardless of which model returned it.
5. Do not ask two providers and "vote" to resolve conflicts silently. If a disagreement check is ever wanted, mark disagreement as `REVIEW_REQUIRED`.
6. Store on every extracted field: provider, model, model version/identifier returned, attempt number, and which providers failed first.
7. `ExternalCallLog` row for every call (provider, model, pages sent, latency, status, error class). No document text in logs.
8. Send only low-confidence pages (default threshold 0.75). Honour the off-switch and a per-document "public/synthetic only" flag: non-public documents never leave the system.
9. Rate-limit and per-day cost cap in config; exceeding it falls through to the deterministic path, with an alert.
10. Do not hard-code model names; pin them in config and record them in the audit/extraction record. Re-run the labelled extraction test set whenever a model name changes or a provider is added.

### Tests
- Provider A times out → B used; both fail → deterministic path, `REVIEW_REQUIRED`.
- Schema-invalid output triggers fallover; grounded-fail value is flagged regardless of provider.
- Circuit breaker opens and recovers (fixed clock).
- Master switch off → zero external calls (assert on the adapter mock).
- Production config rejects the mock LLM and missing keys only when `SIH_LLM_ENABLED=true`.

### Plan tasks (insert after 5.8 in `6_IMPLEMENTATION_PLAN.md`; replaces 5.9)
- [ ] 5.9a Wire `adapters/llm` Protocol and `FallbackLLM` with config-driven provider list and a deterministic last link.
- [ ] 5.9b `GeminiProvider` (move the call out of `grounded_lease_extractor.py` behind the Protocol).
- [ ] 5.9c `OpenRouterProvider` (different model family from Gemini).
- [ ] 5.9d One additional backup provider.
- [ ] 5.9e Circuit breaker, time budget, cost cap.
- [ ] 5.9f `ExternalCallLog` model + migration; per-field provider/model recording.
- [ ] 5.9g Failover test suite above.

### Plan tasks for Supabase (new Phase 2.5, before Phase 3)
- [ ] S.1 Add the settings and production validator changes (SSL required, four URLs).
- [ ] S.2 Engine factory option for pooler mode (`prepare_threshold=None`, small pools).
- [ ] S.3 Data API/RLS lockdown SQL in `backend/sql/supabase_lockdown.sql` and a test that `anon`/`authenticated` cannot read any table.
- [ ] S.4 `docker-compose.supabase.yml` (or profile) and `docs/PRODUCTION.md` update.
- [ ] S.5 Run migrate, seed, `make smoke`, `make verify-isolation` against Supabase.
- [ ] S.6 Decide storage: persistent volume vs `adapters/storage` + Supabase Storage.
