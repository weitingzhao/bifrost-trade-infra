-- TD-85 D1 (Owner 2026-10-04): trade_app_<env> on its own Trade database. Run after
-- ...-td85-trade-app-gs.sql (which creates the role), as postgres, once per env, in that env's database:
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < this file
-- Idempotent. The file refuses to run in another database than bifrost_<env>.
--
-- Grants = what the runtime does (verify file): DML on every public table, sequences for
-- their defaults, SELECT on the FDW schemas brokerage / market. No CREATE on any schema, no
-- TRUNCATE, nothing on another env's database. The FDW user mapping copies the remote user
-- and password of bifrost's mapping (brokerage_reader, read-only) server-side: the password is
-- never in this file, on a command line or in psql output.
\set ON_ERROR_STOP on

\if :{?env}
\else
  \echo 'td85: pass -v env=dev|stg|prod'
  DO $$ BEGIN RAISE EXCEPTION 'td85: env not set'; END $$;
\endif
\set role 'trade_app_' :env
\set db 'bifrost_' :env
SELECT current_database() = :'db' AS td85_right_db, to_regrole(:'role') IS NOT NULL AS td85_role_exists \gset
\if :td85_right_db
\else
  \echo 'td85: this database is not' :db
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif
\if :td85_role_exists
\else
  \echo 'td85: role' :role 'is missing: run ...-td85-trade-app-gs.sql first'
  DO $$ BEGIN RAISE EXCEPTION 'td85: role missing'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';
SELECT set_config('td85.role', :'role', true) AS td85_role \gset

-- 1. CONNECT on this env's database only.
GRANT CONNECT ON DATABASE :"db" TO :"role";

-- 2. Schemas: USAGE, never CREATE.
GRANT USAGE ON SCHEMA public, brokerage, market TO :"role";

-- 3. public: DML on tables (and the compatibility views), sequences for serial / identity.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"role";

-- 4. brokerage / market (postgres_fdw foreign tables and the views over them): read-only.
GRANT SELECT ON ALL TABLES IN SCHEMA brokerage, market TO :"role";

-- 5. Default privileges: objects db-init (bifrost) creates later, and FDW objects the Owner
--    re-imports as postgres (fdw_reimport_pipeline_schemas.py), are usable at once.
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA brokerage, market
  GRANT SELECT ON TABLES TO :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA brokerage, market
  GRANT SELECT ON TABLES TO :"role";

-- 6. FDW user mapping: same remote identity as bifrost's mapping (brokerage_reader). Copied
--    server-side; an error is re-raised without the statement text (it would carry the password).
DO $$
DECLARE
  r    text := current_setting('td85.role');
  opts text[];
  ruser text;
  rpw   text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = r) THEN
    RAISE NOTICE 'td85: user mapping for % exists, left as is', r;
    RETURN;
  END IF;
  SELECT um.umoptions INTO opts
    FROM pg_user_mapping um
    JOIN pg_foreign_server s ON s.oid = um.umserver
   WHERE s.srvname = 'golden_source_server' AND um.umuser = 'bifrost'::regrole;
  SELECT substr(o, 6) INTO ruser FROM unnest(opts) o WHERE o LIKE 'user=%';
  SELECT substr(o, 10) INTO rpw FROM unnest(opts) o WHERE o LIKE 'password=%';
  IF ruser IS DISTINCT FROM 'brokerage_reader' OR coalesce(rpw, '') = '' THEN
    RAISE EXCEPTION 'td85: bifrost''s mapping on golden_source_server is not brokerage_reader with a password; nothing created';
  END IF;
  BEGIN
    EXECUTE format('CREATE USER MAPPING FOR %I SERVER golden_source_server OPTIONS (user %L, password %L)',
                   r, ruser, rpw);
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION 'td85: CREATE USER MAPPING for % failed with SQLSTATE % (statement withheld)', r, SQLSTATE;
  END;
  RAISE NOTICE 'td85: user mapping % -> brokerage_reader created', r;
END
$$;

COMMIT;

SELECT :'role' AS role, current_database() AS db,
       has_database_privilege(:'role', current_database(), 'CONNECT') AS connect,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
           AND has_table_privilege(:'role', c.oid, 'SELECT, INSERT, UPDATE, DELETE')) AS public_tables_dml,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('brokerage', 'market') AND c.relkind IN ('f', 'v')
           AND has_table_privilege(:'role', c.oid, 'SELECT')) AS fdw_relations_select,
       (SELECT umoptions IS NOT NULL FROM pg_user_mappings
         WHERE srvname = 'golden_source_server' AND usename = :'role') AS user_mapping;
