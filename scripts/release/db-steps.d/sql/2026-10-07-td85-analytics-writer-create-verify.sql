-- After the revoke: CREATE is gone, write bits are gone, SELECT remains.
-- Read-only. Raises if any row is still wrong. Run in bifrost_golden_source.
\set ON_ERROR_STOP on
DO $td85$
DECLARE
  bad text;
BEGIN
  IF current_database() <> 'bifrost_golden_source' THEN
    RAISE EXCEPTION 'td85: run this in bifrost_golden_source, not %', current_database();
  END IF;
  SELECT string_agg(label, ', ' ORDER BY label) INTO bad
    FROM (
      SELECT 'analytics_writer CREATE raw_market' AS label
       WHERE has_schema_privilege('analytics_writer', 'raw_market', 'CREATE')
      UNION ALL
      SELECT 'analytics_writer CREATE raw_broker'
       WHERE has_schema_privilege('analytics_writer', 'raw_broker', 'CREATE')
      UNION ALL
      SELECT 'analytics_writer CREATE ops_jobs'
       WHERE has_schema_privilege('analytics_writer', 'ops_jobs', 'CREATE')
      UNION ALL
      SELECT 'analytics_writer INSERT ' || c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'ops_jobs'
         AND c.relname IN ('data_source_void', 'symbol_source_void', 'watchlist_cache')
         AND has_table_privilege('analytics_writer', c.oid, 'INSERT')
      UNION ALL
      SELECT 'market_reader INSERT ticker_related'
       WHERE has_table_privilege('market_reader', 'raw_market.ticker_related', 'INSERT')
      UNION ALL
      SELECT 'analytics_writer lost SELECT watchlist_cache'
       WHERE NOT has_table_privilege('analytics_writer', 'ops_jobs.watchlist_cache', 'SELECT')
      UNION ALL
      SELECT 'market_reader lost SELECT ticker_related'
       WHERE NOT has_table_privilege('market_reader', 'raw_market.ticker_related', 'SELECT')
    ) s;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'td85 verify failed: %', bad;
  END IF;
END
$td85$;
