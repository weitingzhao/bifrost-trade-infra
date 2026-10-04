-- D6 rollback, Trade databases (as postgres; once per database the steps touched):
--   psql -U postgres -d bifrost_dev  -X -v ON_ERROR_STOP=1 -v db=bifrost_dev  -f - < this file   (F4)
--   psql -U postgres -d bifrost_stg  -X -v ON_ERROR_STOP=1 -v db=bifrost_stg  -f - < this file   (M5b)
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v db=bifrost_prod -f - < this file   (M5b)
-- Removes everything flex_writer holds in this database (grants, user mapping) and gives data_writer back
-- its SELECT on public.watchlist in bifrost_stg / bifrost_prod (as read 2026-10-04). Idempotent.
\set ON_ERROR_STOP on
\if :{?db}
\else
  \echo 'd6: pass -v db=<the database>'
  DO $$ BEGIN RAISE EXCEPTION 'd6: db not set'; END $$;
\endif
SELECT current_database() = :'db' AS d6_right_db \gset
\if :d6_right_db
\else
  \echo 'd6: this database is not' :db
  DO $$ BEGIN RAISE EXCEPTION 'd6: wrong database'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '5s';
DO $d6$
DECLARE
  db text := current_database();
BEGIN
  IF to_regrole('flex_writer') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = 'flex_writer') THEN
      DROP USER MAPPING FOR flex_writer SERVER golden_source_server;
    END IF;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM flex_writer;
    IF to_regnamespace('brokerage') IS NOT NULL THEN
      REVOKE ALL ON ALL TABLES IN SCHEMA brokerage FROM flex_writer;
      REVOKE ALL ON SCHEMA brokerage FROM flex_writer;
    END IF;
    REVOKE ALL ON SCHEMA public FROM flex_writer;
    -- Only when flex_writer is in the ACL: a REVOKE on a database whose ACL is still the default would
    -- write the default out explicitly (same rights, different catalog text).
    IF EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
               WHERE d.datname = db AND a.grantee = 'flex_writer'::regrole) THEN
      EXECUTE format('REVOKE ALL ON DATABASE %I FROM flex_writer', db);
    END IF;
  END IF;
  IF db IN ('bifrost_stg', 'bifrost_prod') AND to_regclass('public.watchlist') IS NOT NULL THEN
    GRANT SELECT ON public.watchlist TO data_writer;
  END IF;
END
$d6$;
COMMIT;
