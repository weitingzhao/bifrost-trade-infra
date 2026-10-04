-- D2 verify (read-only; bifrost_golden_source; default_transaction_read_only=on). Run after step 3 (and
-- after step 1 alone: then rows 1-2 still show the membership). Every line names its expected value.
-- The dry-run file is the full matrix; this is the short yes / no list.

SELECT check_name, actual, expected, actual = expected AS ok FROM (VALUES
  ('analytics_writer member of bifrost', pg_has_role('analytics_writer', 'bifrost', 'MEMBER')::text, 'false'),
  ('analytics_writer can SET ROLE bifrost', pg_has_role('analytics_writer', 'bifrost', 'SET')::text, 'false'),
  -- what Research needs
  ('own features.option_metric_pcr_daily (partition parent)',
     (pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'features.option_metric_pcr_daily'::regclass)) = 'analytics_writer')::text, 'true'),
  ('own research.hypothesis',
     (pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'research.hypothesis'::regclass)) = 'analytics_writer')::text, 'true'),
  ('own features.v_atm_iv_unified',
     (pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'features.v_atm_iv_unified'::regclass)) = 'analytics_writer')::text, 'true'),
  ('bifrost-owned relations left in features / research',
     (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname IN ('features', 'research') AND c.relowner = 'bifrost'::regrole)::text, '0'),
  ('SELECT raw_broker.executions_final', has_table_privilege('analytics_writer', 'raw_broker.executions_final', 'SELECT')::text, 'true'),
  ('SELECT ops_jobs.watchlist_cache', has_table_privilege('analytics_writer', 'ops_jobs.watchlist_cache', 'SELECT')::text, 'true'),
  ('SELECT raw_market.stock_daily', has_table_privilege('analytics_writer', 'raw_market.stock_daily', 'SELECT')::text, 'true'),
  ('INSERT features.stock_signal_scan_daily', has_table_privilege('analytics_writer', 'features.stock_signal_scan_daily', 'INSERT')::text, 'true'),
  ('TRUNCATE features.stock_signal_canonical_pnl_daily', has_table_privilege('analytics_writer', 'features.stock_signal_canonical_pnl_daily', 'TRUNCATE')::text, 'true'),
  ('INSERT dw_stock.mart_sepa_screener_wide', has_table_privilege('analytics_writer', 'dw_stock.mart_sepa_screener_wide', 'INSERT')::text, 'true'),
  ('INSERT journal.note', has_table_privilege('analytics_writer', 'journal.note', 'INSERT')::text, 'true'),
  ('CREATE in schema features', has_schema_privilege('analytics_writer', 'features', 'CREATE')::text, 'true'),
  ('EXECUTE ops_jobs.ensure_month_partitions', has_function_privilege('analytics_writer', 'ops_jobs.ensure_month_partitions(text,text,integer,integer)', 'EXECUTE')::text, 'true'),
  -- what it loses (inherited only before D2)
  ('SELECT raw_broker.account', has_table_privilege('analytics_writer', 'raw_broker.account', 'SELECT')::text, 'false'),
  ('INSERT raw_broker.executions_raw_flex', has_table_privilege('analytics_writer', 'raw_broker.executions_raw_flex', 'INSERT')::text, 'false'),
  ('INSERT raw_market.stock_daily', has_table_privilege('analytics_writer', 'raw_market.stock_daily', 'INSERT')::text, 'false'),
  ('SELECT ops_jobs.job_ingest', has_table_privilege('analytics_writer', 'ops_jobs.job_ingest', 'SELECT')::text, 'false'),
  ('SELECT ops_feedback.report', has_table_privilege('analytics_writer', 'ops_feedback.report', 'SELECT')::text, 'false'),
  ('CREATE in schema public', has_schema_privilege('analytics_writer', 'public', 'CREATE')::text, 'false'),
  -- the market-data plugin (still bifrost) keeps reading Research's features
  ('bifrost SELECT features.option_metric_atm_iv_daily', has_table_privilege('bifrost', 'features.option_metric_atm_iv_daily', 'SELECT')::text, 'true'),
  ('bifrost SELECT research.option_universe', has_table_privilege('bifrost', 'research.option_universe', 'SELECT')::text, 'true'),
  ('bifrost USAGE on schema features', has_schema_privilege('bifrost', 'features', 'USAGE')::text, 'true'),
  ('market_reader SELECT features.option_metric_pcr_daily', has_table_privilege('market_reader', 'features.option_metric_pcr_daily', 'SELECT')::text, 'true')
) AS t(check_name, actual, expected)
ORDER BY ok, check_name;

-- Inherited-only DML left (expected: no rows).
WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid)
SELECT n.nspname AS schema, p AS priv, count(*) AS objects_inherited_only
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) p
WHERE c.relkind IN ('r', 'p', 'v', 'm') AND n.nspname !~ '^(pg_|information_schema)'
  AND has_table_privilege((SELECT oid FROM aw), c.oid, p)
  AND c.relowner <> (SELECT oid FROM aw)
  AND NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(c.relacl, acldefault('r'::"char", c.relowner))) a
                  WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = p)
GROUP BY 1, 2
ORDER BY 1, 2;
