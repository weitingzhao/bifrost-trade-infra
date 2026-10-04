-- D6 step 4, Trade part (M5b, named item; as postgres, once in bifrost_stg and once in bifrost_prod):
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v db=bifrost_prod -f - < this file
-- data_writer still holds SELECT on public.watchlist in bifrost_stg / bifrost_prod (measured 2026-10-04;
-- nothing else in any Trade database). market-data reads no Trade table since 0.75.0 (the watchlist comes
-- from the Platform union or ops_jobs.watchlist_cache), so the grant goes. Idempotent.
-- Rollback: sql/2026-10-04-d6-rollback-trade.sql with the same -v db.
\set ON_ERROR_STOP on
\if :{?db}
\else
  \echo 'd6: pass -v db=bifrost_stg or -v db=bifrost_prod'
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
BEGIN
  IF to_regclass('public.watchlist') IS NOT NULL THEN
    REVOKE ALL ON public.watchlist FROM data_writer;
  END IF;
END
$d6$;
COMMIT;

SELECT current_database() AS db, n.nspname AS schema, c.relname AS object, a.privilege_type AS data_writer_still_has
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a
WHERE a.grantee = 'data_writer'::regrole;
