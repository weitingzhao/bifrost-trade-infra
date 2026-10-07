-- Read-only picture of the grants the TD-85 role-matrix step would change.
-- Run as postgres, in bifrost_golden_source, with default_transaction_read_only=on.
-- Before the revoke: the three CREATE flags are true, and the four DML flags are true.
SELECT 'analytics_writer CREATE raw_market' AS check,
       has_schema_privilege('analytics_writer', 'raw_market', 'CREATE') AS value
UNION ALL
SELECT 'analytics_writer CREATE raw_broker',
       has_schema_privilege('analytics_writer', 'raw_broker', 'CREATE')
UNION ALL
SELECT 'analytics_writer CREATE ops_jobs',
       has_schema_privilege('analytics_writer', 'ops_jobs', 'CREATE')
UNION ALL
SELECT 'analytics_writer INSERT data_source_void',
       has_table_privilege('analytics_writer', 'ops_jobs.data_source_void', 'INSERT')
UNION ALL
SELECT 'analytics_writer INSERT symbol_source_void',
       has_table_privilege('analytics_writer', 'ops_jobs.symbol_source_void', 'INSERT')
UNION ALL
SELECT 'analytics_writer INSERT watchlist_cache',
       has_table_privilege('analytics_writer', 'ops_jobs.watchlist_cache', 'INSERT')
UNION ALL
SELECT 'analytics_writer SELECT watchlist_cache',
       has_table_privilege('analytics_writer', 'ops_jobs.watchlist_cache', 'SELECT')
UNION ALL
SELECT 'market_reader INSERT ticker_related',
       has_table_privilege('market_reader', 'raw_market.ticker_related', 'INSERT')
UNION ALL
SELECT 'market_reader SELECT ticker_related',
       has_table_privilege('market_reader', 'raw_market.ticker_related', 'SELECT')
ORDER BY 1;
