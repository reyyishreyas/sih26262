-- Role bootstrap for PostgreSQL deployments.
--
-- The Approval Rehearsal Engine promises that a rehearsal cannot touch production.
-- This file is how that promise is enforced by PostgreSQL rather than by good
-- intentions:
--
--   app_rw          operational read/write on public tables.
--   sim_prod_ro     SELECT only on public tables, read-only by default.
--   sim_results_rw  INSERT/SELECT on the sim_* tables only; no access to any
--                   operational table.
--
-- A rehearsal baseline is read through sim_prod_ro and results are written through
-- sim_results_rw. Even a bug in application code cannot turn the baseline connection
-- into a production writer.
--
-- Implementation note: this prototype stores the sim_* tables in the same schema as
-- operational tables (SQLite has no schemas), so isolation is expressed as
-- table-level grants. Moving sim_* into a dedicated `sim` schema is listed as a
-- deployment step in docs/REHEARSAL_ENGINE.md, not claimed as done.
--
-- Run once, as a superuser, after `CREATE DATABASE sih26262;` and
-- `alembic upgrade head`:
--   psql -d sih26262 -f sql/roles.sql
--
-- Passwords are supplied separately from a secret manager; never commit them.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sim_prod_ro') THEN
        CREATE ROLE sim_prod_ro LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sim_results_rw') THEN
        CREATE ROLE sim_results_rw LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sih_migrator') THEN
        CREATE ROLE sih_migrator LOGIN;
    END IF;
END
$$;

-- Start from nothing rather than inheriting PUBLIC's defaults.
REVOKE ALL ON SCHEMA public FROM PUBLIC;

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
-- No schema usage for sim_results_rw, so it cannot even resolve operational
-- table names. It receives explicit grants on the simulation tables only.
REVOKE ALL ON SCHEMA public FROM sim_results_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    sim_runs,
    sim_input_snapshots,
    sim_rule_results,
    sim_metrics
TO sim_results_rw;

COMMIT;

-- Re-run after any future migration, because grants for new tables are not
-- retroactive:
--   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE <new_sim_table> TO sim_results_rw;
--   GRANT SELECT ON TABLE <new_operational_table> TO sim_prod_ro;
