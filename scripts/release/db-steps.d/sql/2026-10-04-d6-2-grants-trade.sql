-- D6 step 2 of 4, Trade part (F4; as postgres, in the Trade database flex-query reads). Additive only.
--   psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v db=bifrost_dev -f - < this file
-- flex-query reads ONE Trade database (Secret key trade-pg-db, and the ConfigMap fallback): bifrost_dev,
-- measured 2026-10-04. The file refuses any other database than -v db.
--
-- What flex reads there (read-only since flex 0.7.0):
--   public.settings              flex_*_range_days, the seed / fallback of ops_jobs.flex_settings
--   brokerage.executions         view (owner bifrost -> bifrost's user mapping): Flex execution stats
--   brokerage.settings_flex      postgres_fdw foreign table: query ids. A foreign table read directly uses
--                                the CALLER's user mapping, so flex_writer gets its own, copying the
--                                remote user and password of bifrost's mapping (brokerage_reader, read-only)
--                                server-side; the password never appears in this file, a command line or
--                                psql output (same DO block as TD-85).
-- No CREATE anywhere, no DML, nothing on brokerage's other foreign tables.
--
-- Idempotent. Rollback: sql/2026-10-04-d6-rollback-trade.sql with the same -v db.
\set ON_ERROR_STOP on
\if :{?db}
\else
  \echo 'd6: pass -v db=bifrost_dev (the database flex-query reads)'
  DO $$ BEGIN RAISE EXCEPTION 'd6: db not set'; END $$;
\endif
SELECT current_database() = :'db' AS d6_right_db, to_regrole('flex_writer') IS NOT NULL AS d6_role_exists \gset
\if :d6_right_db
\else
  \echo 'd6: this database is not' :db
  DO $$ BEGIN RAISE EXCEPTION 'd6: wrong database'; END $$;
\endif
\if :d6_role_exists
\else
  \echo 'd6: role flex_writer is missing: run sql/2026-10-04-d6-1-roles.sql first'
  DO $$ BEGIN RAISE EXCEPTION 'd6: role missing'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';

GRANT CONNECT ON DATABASE :"db" TO flex_writer;
GRANT USAGE ON SCHEMA public, brokerage TO flex_writer;
GRANT SELECT ON public.settings, brokerage.executions, brokerage.settings_flex TO flex_writer;

DO $$
DECLARE
  opts  text[];
  ruser text;
  rpw   text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = 'flex_writer') THEN
    RAISE NOTICE 'd6: user mapping for flex_writer exists, left as is';
    RETURN;
  END IF;
  SELECT um.umoptions INTO opts
    FROM pg_user_mapping um
    JOIN pg_foreign_server s ON s.oid = um.umserver
   WHERE s.srvname = 'golden_source_server' AND um.umuser = 'bifrost'::regrole;
  SELECT substr(o, 6) INTO ruser FROM unnest(opts) o WHERE o LIKE 'user=%';
  SELECT substr(o, 10) INTO rpw FROM unnest(opts) o WHERE o LIKE 'password=%';
  IF ruser IS DISTINCT FROM 'brokerage_reader' OR coalesce(rpw, '') = '' THEN
    RAISE EXCEPTION 'd6: bifrost''s mapping on golden_source_server is not brokerage_reader with a password; nothing created';
  END IF;
  BEGIN
    EXECUTE format('CREATE USER MAPPING FOR flex_writer SERVER golden_source_server OPTIONS (user %L, password %L)',
                   ruser, rpw);
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION 'd6: CREATE USER MAPPING for flex_writer failed with SQLSTATE % (statement withheld)', SQLSTATE;
  END;
  RAISE NOTICE 'd6: user mapping flex_writer -> brokerage_reader created';
END
$$;

COMMIT;

SELECT current_database() AS db,
       has_database_privilege('flex_writer', current_database(), 'CONNECT') AS connect,
       has_table_privilege('flex_writer', 'public.settings', 'SELECT') AS settings_select,
       has_table_privilege('flex_writer', 'brokerage.executions', 'SELECT') AS executions_select,
       has_table_privilege('flex_writer', 'brokerage.settings_flex', 'SELECT') AS settings_flex_select,
       (SELECT count(*) FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = 'flex_writer') = 1 AS user_mapping;
