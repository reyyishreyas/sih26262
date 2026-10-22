# Production Deployment Guide

This repository is a **hardened prototype**, not a certified government system. The
code has production-shaped configuration, least-privilege database roles,
non-root containers, structured logs and fail-fast secret validation — but it has
not been security-audited, load-tested, retained under an approved records policy,
or validated against the AICTE Approval Process Handbook by a competent authority.
Treat this guide as a deployment baseline that still needs your organisation's
security, legal and operations sign-off.

---

## 1. What the production profile changes

| Area | Demo (`docker-compose.yml`) | Production (`docker-compose.prod.yml`) |
|---|---|---|
| Secrets | committed development values | required environment values, no defaults for passwords |
| Database | PostgreSQL published on `:5432` | PostgreSQL not published; only Compose network |
| Migrations | `sih_migrator` then grants | same, after a one-shot role-bootstrap job |
| API role | `app_rw` | `app_rw` (no DDL) |
| Rehearsal roles | `sim_prod_ro`, `sim_results_rw` | same |
| Clock | fixed demo clock | real system clock |
| Seed | synthetic demo data on startup | seeding disabled |
| API docs | enabled | disabled by default (`SIH_DOCS_ENABLED=false`) |
| TLS headers | no HSTS (non-production) | HSTS emitted, one-year minimum enforced |
| Images | backend multi-stage/non-root; frontend dev server | backend + nginx production image, both non-root |
| Filesystem | writable | API/worker read-only root with `/tmp` and a storage volume |

The API validates its own configuration at startup. With `SIH_ENV=production` it
refuses to start when any of these are true:

- `SIH_JWT_SECRET` is shorter than 32 characters or is a known development value
- `SIH_DATABASE_URL` is SQLite
- `SIH_SIMULATION_READONLY_URL` or `SIH_SIMULATION_RESULTS_URL` is unset, is not
  PostgreSQL, or reuses the API's database role
- `SIH_SIMULATION_SCHEMA` is unset, `public`, or not a safe lowercase identifier
- `SIH_CORS_ORIGINS` is empty or contains `*`
- `SIH_ALLOWED_HOSTS` is empty or contains `*`
- `SIH_SEED_ON_STARTUP=true`
- `SIH_CLOCK_MODE` is not `system`
- `SIH_DEBUG=true`
- `SIH_HSTS_SECONDS` is below `31536000`
- `SIH_PASSWORD_HASH_ITERATIONS` is below `100000`

---

## 2. Prerequisites

- Docker Engine with Compose v2
- A PostgreSQL backup target and a tested restore procedure
- TLS termination (reverse proxy, load balancer or ingress) for the API and UI
- A secret manager or deployment system that injects environment variables
- A DNS name for the UI and one for the API (or a single origin with path routing)
- Disk for the PostgreSQL volume and the evidence-storage volume

Generate independent URL-safe secrets, never reuse one. Hex avoids characters such
as `/`, `+` and `=` that would break the database URLs assembled by Compose:

```bash
openssl rand -hex 32   # POSTGRES_PASSWORD
openssl rand -hex 32   # SIH_MIGRATOR_PASSWORD
openssl rand -hex 32   # SIH_APP_RW_PASSWORD
openssl rand -hex 32   # SIH_SIM_RO_PASSWORD
openssl rand -hex 32   # SIH_SIM_RW_PASSWORD
openssl rand -hex 32   # SIH_JWT_SECRET
```

If you must use a password containing URL-reserved characters, percent-encode it
in every `SIH_*_URL` value or the connection URL will be parsed incorrectly.

---

## 3. Configure

```bash
cp .env.production.example .env.production
${EDITOR:-vi} .env.production
```

Required values:

| Variable | Meaning |
|---|---|
| `POSTGRES_PASSWORD` | superuser password; used only by the bootstrap/grants jobs |
| `SIH_MIGRATOR_PASSWORD` | schema owner used by Alembic |
| `SIH_APP_RW_PASSWORD` | API/worker operational role |
| `SIH_SIM_RO_PASSWORD` | rehearsal baseline reader (read-only) |
| `SIH_SIM_RW_PASSWORD` | rehearsal results writer (sim schema only) |
| `SIH_SIMULATION_SCHEMA` | dedicated rehearsal schema; defaults to `sim`, never `public` |
| `SIH_JWT_SECRET` | token signing secret, at least 32 random characters |
| `SIH_CORS_ORIGINS` | exact browser origin, e.g. `["https://aicte.example.gov.in"]` |
| `SIH_ALLOWED_HOSTS` | exact API hostnames, e.g. `["api.aicte.example.gov.in"]` |
| `SIH_PUBLIC_API_BASE` | absolute API URL baked into the frontend build |

Also review:

- `SIH_ACCESS_TOKEN_MINUTES` — default 480. Shorter is safer; users must sign in
  again after expiry or a password change.
- `SIH_LOGIN_*` — persisted account/address throttling. Defaults: five failures per
  account/address in fifteen minutes, twenty-five per address, fifteen-minute
  lockout.
- `SIH_DB_*` — pool size, overflow, connection timeout and statement timeout.
- `SIH_DOCS_ENABLED` — keep `false` unless the API is on a restricted network.
- `SIH_TRUST_PROXY_HEADERS` — only `true` when a trusted proxy overwrites
  `X-Forwarded-For`; otherwise clients can choose their throttle key.
- `SIH_SIMULATION_SCHEMA` — Compose sets `sim`. Do not unset it in production.

`.env.production` contains secrets. It is git-ignored; do not copy it into images,
tickets or logs. `docker-compose.prod.yml` passes an explicit application-only
environment to the API and worker; the superuser and migrator passwords are used
only by the one-shot `bootstrap` and `migrate` services and are not present in the
runtime containers.

Validate the rendered Compose file before starting:

```bash
make prod-config
```

---

## 4. Deploy

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f api worker
```

Startup order:

1. `db` becomes healthy.
2. `bootstrap` creates the four least-privilege roles with the injected passwords.
3. `migrate` runs `alembic upgrade head` as `sih_migrator`, then applies
   `backend/sql/roles.sql` as the superuser (a role cannot grant what it does not
   own).
4. `api` and `worker` start as `app_rw`; the API also opens read-only
   `sim_prod_ro` and write-only `sim_results_rw` connections for rehearsals.
5. `frontend` starts after the API is healthy.

Check readiness and the database role:

```bash
curl -fsS https://api.example.gov.in/health/ready
curl -fsS https://api.example.gov.in/health
```

`/health/ready` returns `503` if the operational database, rehearsal baseline
reader or rehearsal writer cannot execute a probe query. Use it for load-balancer
health checks. Use `/health/live` for process liveness (for example, a container
restart policy).

---

## 5. TLS and reverse proxy

Terminate TLS in front of the API and UI. The API emits HSTS in production; browsers
ignore HSTS over plain HTTP, so do not rely on it instead of TLS.

If the reverse proxy is the only route to the API:

- Bind Compose to localhost (`API_BIND=127.0.0.1:8000`,
  `WEB_BIND=127.0.0.1:8080`) and let the proxy expose `443`.
- Keep `SIH_ALLOWED_HOSTS` restricted to the public hostnames.
- Set `SIH_CORS_ORIGINS` to the exact UI origin, not `*`.
- Enable `SIH_TRUST_PROXY_HEADERS` only if the proxy **overwrites**
  `X-Forwarded-For`; never trust a client-supplied value.
- Do not expose PostgreSQL or the storage volume to the public network.

Example nginx location (the frontend container already serves the SPA with
`nginx.conf`):

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

If the API and UI share one origin, set `SIH_PUBLIC_API_BASE=/api/v1` at frontend
build time and route `/api/` to the backend.

---

## 6. Backups and restore

Two stateful volumes matter:

- `pgdata` — operational and simulation tables, audit chain, users, alerts
- `storage` — uploaded evidence files

Back up the database with `pg_dump` (or your managed PostgreSQL service) and snapshot
the storage volume on the same schedule. Keep the audit chain and evidence files
together; a database restore without the matching files leaves document metadata
pointing at missing bytes.

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec -T db pg_dump -U postgres -Fc sih26262 > sih26262-$(date +%F).dump
```

Restore into a **new** database first and run the API test suite or smoke script
against it. Never restore over the live database without a verified backup and a
maintenance window.

After a restore, verify the audit chain:

```bash
# Authenticate as an administrator, then:
curl -fsS -H "Authorization: Bearer $TOKEN" \
  https://api.example.gov.in/api/v1/audit/verify
```

---

## 7. Monitoring and incident response

- Ship JSON logs to your log platform. Every request log line includes
  `request_id`, method, path, status, duration and client address.
- Alert on `/health/ready` returning non-200, container restarts, database
  connection-pool exhaustion and a rising `429` rate.
- `GET /api/v1/audit/verify` checks the hash chain; run it after restores and on a
  schedule.
- Accepted and rejected logins are audit events (`auth.login`); password changes are
  `auth.password_changed`.
- The `X-Request-ID` response header lets a user report map to the exact server log
  line. A safe client-supplied id is echoed; anything else is replaced.
- There is **no Prometheus metrics endpoint** in this repository. Add one before
  claiming full observability.

---

## 8. Scaling and availability

- The API is stateless (JWT bearer tokens, database-backed throttling), so multiple
  replicas can sit behind a load balancer. Give each replica the same secret and
  database URLs.
- Run **one worker** unless you have verified scheduler locking under your database
  isolation level. Deadline dedupe keys make repeated sweeps idempotent, but this is
  not a substitute for a job-lock design.
- The audit chain serialises appends through a row lock. Throughput is therefore
  bounded by write latency; measure it before promising high concurrency.
- The rehearsal baseline and results use the same PostgreSQL instance but different
  roles and the `sim` schema. A separate database instance would be a stronger
  isolation boundary; it is not implemented.
- Uploaded files live on a local volume. For multi-node deployments, replace the
  storage path with shared object storage and keep the same metadata contract.

---

## 9. Security boundaries that remain

The following are **not** implemented or not validated. Do not describe them as
done in a review:

- MFA, SSO/government identity, password reset by email, and account recovery
- Segregation of duties / four-eyes approval
- Database-level trigger for rule-version immutability (the ORM guard is tested, the
  trigger is not)
- Retention, archival, partitioning, legal hold and right-to-erasure workflows
- Malware scanning of uploaded files (signature and size checks exist, not AV)
- External object storage with signed URLs; files are not served to clients
- Real OCR, LLM explanations or notification delivery (mock adapters only)
- Load, soak, failover and disaster-recovery tests
- Independent penetration test, dependency audit and secret scan in CI
- Historical state replay (chronological audit timeline only)
- Load Factor (intentionally `null` until formula, units, edge cases and test matrix
  are validated)

See [DEFERRALS.md](DEFERRALS.md) for the complete list.

---

## 10. Upgrade and rollback

1. Back up the database and storage volume.
2. Pull/build the new images.
3. Run the migration job separately and capture its logs:
   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml run --rm migrate
   ```
4. Check `alembic check` as `sih_migrator` in a staging copy; it must report no
   drift.
5. Deploy the API and worker, then the frontend.
6. Verify `/health/ready`, login, a rehearsal (assert `production_modified:false`)
   and `/audit/verify`.

Migration `0002_sim_schema` moves the simulation tables into the `sim` schema;
migration `0003_auth_hardening` adds `users.password_changed_at` and
`login_attempts`. Test both upgrade and downgrade paths on a database copy before a
production rollout. There is no automated zero-downtime migration guarantee.

Rolling back code without rolling back the schema is only safe if the previous
release tolerates the new nullable column/table. Treat schema changes as
forward-compatible unless you have tested the downgrade.

---

## 11. Release gate

A release is only eligible when CI passes:

- Ruff lint and import order
- Python syntax compilation
- SQLite `alembic upgrade head` + `alembic check`
- 99 backend tests
- PostgreSQL role-isolation job (including `alembic check` as `sih_migrator` and the
  live role contract)
- Frontend `tsc --noEmit` + Vite production build

Then run, against the deployed stack:

```bash
SIH_BASE_URL=https://api.example.gov.in make smoke
```

`make verify-isolation` is a local/Compose check; the CI PostgreSQL job runs the
same script. It is not a production read-only probe.

---

## 12. Known operational limitations

- The demo data is synthetic. Real student/institution data brings privacy,
  consent, retention and access-request obligations that this repository does not
  implement.
- Notification delivery is mocked; alert rows and delivery attempts are real, but no
  SMS/email leaves the system.
- The rehearsal engine isolates by schema and role, not by a separate database
  instance.
- The fixed-clock mode is for demos and tests only; production validation rejects it.
- There is no built-in metrics endpoint, log shipper or backup scheduler.
- The frontend has no end-to-end browser test suite; CI type-checks and builds it.
