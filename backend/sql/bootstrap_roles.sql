-- Development bootstrap for PostgreSQL roles.
--
-- Mounted into /docker-entrypoint-initdb.d/ by docker-compose.yml. It runs only when
-- the database volume is first created, as the POSTGRES_USER superuser.
--
-- The passwords below are development credentials committed on purpose so the demo
-- stack is reproducible. NEVER use them outside a local/demo environment. In a real
-- deployment create the roles with a secret manager and run sql/roles.sql separately.
--
-- Role contract (enforced by sql/roles.sql, which runs after migrations):
--   sih_migrator    owns the schema objects and runs Alembic. Not used by the API.
--   app_rw          operational read/write. No access to the sim schema.
--   sim_prod_ro     operational SELECT only, default_transaction_read_only=on.
--   sim_results_rw  USAGE on sim only; no USAGE on public.

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

ALTER ROLE sih_migrator PASSWORD 'sih_migrator_dev';
ALTER ROLE app_rw PASSWORD 'app_rw_dev';
ALTER ROLE sim_prod_ro PASSWORD 'sim_prod_ro_dev';
ALTER ROLE sim_results_rw PASSWORD 'sim_results_rw_dev';

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
