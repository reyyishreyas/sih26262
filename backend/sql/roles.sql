-- Least-privilege grants for PostgreSQL deployments.
--
-- The Approval Rehearsal Engine promises that a rehearsal cannot touch production.
-- This file is how that promise is enforced by PostgreSQL rather than by good
-- intentions:
--
--   sih_migrator    owns schema objects; runs Alembic; not used by the API.
--   app_rw          operational read/write on public tables. No access to sim.
--   sim_prod_ro     SELECT only on public tables, read-only by default.
--   sim_results_rw  USAGE on the sim schema only; INSERT/SELECT/UPDATE/DELETE on
--                   sim_* tables. It has no USAGE on public, so it cannot resolve
--                   operational table names at all.
--
-- A rehearsal baseline is read through sim_prod_ro and results are written through
-- sim_results_rw. Even a bug in application code cannot turn the baseline connection
-- into a production writer, or the results writer into a production reader.
--
-- Order of operations:
--   1. Create roles with sql/bootstrap_roles.sql (or a secret manager).
--   2. Run `alembic upgrade head` as sih_migrator.
--   3. Run this file as a superuser (docker compose does this in the migrate job):
--        psql -d sih26262 -v ON_ERROR_STOP=1 -f sql/roles.sql
--
-- Re-run after future migrations: grants are not retroactive for new tables (default
-- privileges handle objects created by sih_migrator, but review every migration).

BEGIN;

-- Safe for manual deployment where bootstrap_roles.sql was not used.
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

-- Start from nothing rather than inheriting PUBLIC's defaults. The baseline reader
-- and results writer never receive USAGE on public.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM sim_results_rw;

-- ---------------------------------------------------------------- migrations
GRANT USAGE, CREATE ON SCHEMA public TO sih_migrator;

ALTER DEFAULT PRIVILEGES FOR ROLE sih_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE sih_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE sih_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO sim_prod_ro;

-- ---------------------------------------------------------------- operations
GRANT USAGE ON SCHEMA public TO app_rw, sim_prod_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;

-- The baseline reader can never write, at the role level and at the transaction
-- level. Belt and braces: both are set.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sim_prod_ro;
ALTER ROLE sim_prod_ro SET default_transaction_read_only = on;

-- ---------------------------------------------------------------- simulation
-- The schema is created by migration 0002 when SIH_SIMULATION_SCHEMA=sim. This
-- statement is a safety net for manual deployments and keeps the owner correct.
CREATE SCHEMA IF NOT EXISTS sim AUTHORIZATION sih_migrator;

REVOKE ALL ON SCHEMA sim FROM PUBLIC;
REVOKE ALL ON SCHEMA sim FROM app_rw, sim_prod_ro;
GRANT USAGE, CREATE ON SCHEMA sim TO sih_migrator;
GRANT USAGE ON SCHEMA sim TO sim_results_rw;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sim TO sim_results_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA sim TO sim_results_rw;

ALTER DEFAULT PRIVILEGES FOR ROLE sih_migrator IN SCHEMA sim
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sim_results_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE sih_migrator IN SCHEMA sim
    GRANT USAGE, SELECT ON SEQUENCES TO sim_results_rw;

COMMIT;
