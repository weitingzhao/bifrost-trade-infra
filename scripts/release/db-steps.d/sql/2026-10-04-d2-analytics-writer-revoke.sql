-- D2 step 3 of 3 (as postgres, bifrost_golden_source, one transaction): analytics_writer stops being a
-- member of bifrost. Refuses (and changes nothing) unless step 1 left no gap: every relation in
-- features / research / journal / dw_stock / ops_dbt / ops_dagster owned by analytics_writer, and SELECT
-- held directly on raw_market.*, raw_broker.executions_final and ops_jobs.watchlist_cache.
--
-- Takes effect for NEW sessions at once and for running sessions at their next privilege check
-- (membership is read from the catalog, there is no session cache). Rollback:
-- sql/2026-10-04-d2-analytics-writer-rollback.sql (GRANT bifrost TO analytics_writer).

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
  gaps int;
  sample text;
BEGIN
  WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid),
  rel AS (
    SELECT c.oid, n.nspname, c.relname, c.relowner, coalesce(c.relacl, acldefault('r'::"char", c.relowner)) AS acl
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p', 'v', 'm')
  ),
  g AS (
    SELECT r.nspname || '.' || r.relname AS obj FROM rel r
     WHERE r.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster')
       AND r.relowner <> (SELECT oid FROM aw)
    UNION ALL
    SELECT r.nspname || '.' || r.relname FROM rel r
     WHERE (r.nspname = 'raw_market' OR (r.nspname, r.relname) IN (('raw_broker', 'executions_final'), ('ops_jobs', 'watchlist_cache')))
       AND r.relowner <> (SELECT oid FROM aw)
       AND NOT EXISTS (SELECT 1 FROM aclexplode(r.acl) a WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = 'SELECT')
  )
  SELECT count(*), left(string_agg(obj, ', '), 300) INTO gaps, sample FROM g;
  IF gaps > 0 THEN
    RAISE EXCEPTION 'D2: % need(s) of analytics_writer are not covered directly yet (%); run step 1 first', gaps, sample;
  END IF;
END
$$;

REVOKE bifrost FROM analytics_writer;

DO $$
BEGIN
  IF pg_has_role('analytics_writer', 'bifrost', 'MEMBER') THEN
    RAISE EXCEPTION 'D2: analytics_writer is still a member of bifrost';
  END IF;
END
$$;

COMMIT;
