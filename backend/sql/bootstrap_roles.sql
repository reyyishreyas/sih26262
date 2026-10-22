-- Development bootstrap for PostgreSQL roles.
--
-- Mounted into /docker-entrypoint-initdb.d/ by docker-compose.yml, where it runs
-- only when the database volume is first created, as the POSTGRES_USER superuser.
--
-- Passwords come from psql variables so the same file is safe for the demo and for
-- a deployment that injects secrets:
--
--   psql -v migrator_password="$SIH_MIGRATOR_PASSWORD" ... -f bootstrap_roles.sql
--
-- Without variables the committed development credentials are used. NEVER use the
-- defaults outside a local/demo environment.
--
-- Role contract (enforced by sql/roles.sql, which runs after migrations):
--   sih_migrator    owns the schema objects and runs Alembic. Not used by the API.
--   app_rw          operational read/write. No access to the sim schema.
--   sim_prod_ro     operational SELECT only, default_transaction_read_only=on.
--   sim_results_rw  USAGE on sim only; no USAGE on public.

\set ON_ERROR_STOP on

\if :{?migrator_password}
\else
    \set migrator_password 'sih_migrator_dev'
\endif
\if :{?app_rw_password}
\else
    \set app_rw_password 'app_rw_dev'
\endif
\if :{?sim_prod_ro_password}
\else
    \set sim_prod_ro_password 'sim_prod_ro_dev'
\endif
\if :{?sim_results_rw_password}
\else
    \set sim_results_rw_password 'sim_results_rw_dev'
\endif

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sih_migrator') THEN
        CREATE ROLE sih_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sim_prod_ro') THEN
        CREATE ROLE sim_prod_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sim_results_rw') THEN
        CREATE ROLE sim_results_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

ALTER ROLE sih_migrator PASSWORD :'migrator_password';
ALTER ROLE app_rw PASSWORD :'app_rw_password';
ALTER ROLE sim_prod_ro PASSWORD :'sim_prod_ro_password';
ALTER ROLE sim_results_rw PASSWORD :'sim_results_rw_password';

ALTER ROLE sim_prod_ro SET default_transaction_read_only = on;

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT, CREATE ON DATABASE %I TO sih_migrator',
        current_database()
    );
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO app_rw, sim_prod_ro, sim_results_rw',
        current_database()
    );
END
$$;

GRANT USAGE, CREATE ON SCHEMA public TO sih_migrator;
