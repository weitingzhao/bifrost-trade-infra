-- D6 verify, Golden Source (read-only; bifrost_golden_source; default_transaction_read_only=on). The state
-- after step 4. Every line names its expected value; the dry-run file is the full needs matrix.

SELECT check_name, actual, expected, actual = expected AS ok FROM (VALUES
  -- data_writer (market-data): what it needs
  ('data_writer explicit CONNECT on the database',
     EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a WHERE d.datname = current_database()
             AND a.grantee = 'data_writer'::regrole AND a.privilege_type = 'CONNECT')::text, 'true'),
  ('data_writer statement_timeout=2s', coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting WHERE setrole = 'data_writer'::regrole AND setdatabase = 0), false)::text, 'true'),
  ('owner of schema raw_market', pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market')), 'data_writer'),
  ('raw_market objects not owned by data_writer',
     (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'raw_market' AND c.relowner <> 'data_writer'::regrole)::text, '0'),
  ('owner of ops_jobs.job_ingest', pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'ops_jobs.job_ingest'::regclass)), 'data_writer'),
  ('owner of ops_jobs.watchlist_cache', pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = 'ops_jobs.watchlist_cache'::regclass)), 'data_writer'),
  ('market ops_jobs tables owned by data_writer',
     (SELECT count(*) FROM pg_class WHERE relowner = 'data_writer'::regrole AND oid IN ('ops_jobs.job_ingest'::regclass,
        'ops_jobs.ingest_freshness'::regclass, 'ops_jobs.queue_sample'::regclass, 'ops_jobs.coverage_sample'::regclass,
        'ops_jobs.data_source_void'::regclass, 'ops_jobs.symbol_source_void'::regclass, 'ops_jobs.watchlist_cache'::regclass))::text, '7'),
  ('data_writer USAGE, CREATE on ops_jobs', has_schema_privilege('data_writer', 'ops_jobs', 'USAGE, CREATE')::text, 'true'),
  ('data_writer EXECUTE ensure_month_partitions', has_function_privilege('data_writer', 'ops_jobs.ensure_month_partitions(text,text,integer,integer)', 'EXECUTE')::text, 'true'),
  ('data_writer SELECT research.option_universe', has_table_privilege('data_writer', 'research.option_universe', 'SELECT')::text, 'true'),
  ('data_writer SELECT research.option_pinned_contract', has_table_privilege('data_writer', 'research.option_pinned_contract', 'SELECT')::text, 'true'),
  ('data_writer SELECT features.option_metric_atm_iv_daily', has_table_privilege('data_writer', 'features.option_metric_atm_iv_daily', 'SELECT')::text, 'true'),
  ('data_writer SELECT features.option_metric_pcr_daily', has_table_privilege('data_writer', 'features.option_metric_pcr_daily', 'SELECT')::text, 'true'),
  ('data_writer SELECT dw_stock.mart_sepa_fundamental_eval', has_table_privilege('data_writer', 'dw_stock.mart_sepa_fundamental_eval', 'SELECT')::text, 'true'),
  -- data_writer: what it must not have
  ('data_writer member of bifrost', pg_has_role('data_writer', 'bifrost', 'MEMBER')::text, 'false'),
  ('data_writer may SET ROLE bifrost', pg_has_role('data_writer', 'bifrost', 'SET')::text, 'false'),
  ('data_writer SELECT raw_broker.account', has_table_privilege('data_writer', 'raw_broker.account', 'SELECT')::text, 'false'),
  ('data_writer INSERT raw_broker.executions_raw_flex', has_table_privilege('data_writer', 'raw_broker.executions_raw_flex', 'INSERT')::text, 'false'),
  ('data_writer USAGE schema raw_broker', has_schema_privilege('data_writer', 'raw_broker', 'USAGE')::text, 'false'),
  ('data_writer INSERT features.option_metric_pcr_daily', has_table_privilege('data_writer', 'features.option_metric_pcr_daily', 'INSERT')::text, 'false'),
  ('data_writer INSERT research.option_universe', has_table_privilege('data_writer', 'research.option_universe', 'INSERT')::text, 'false'),
  ('data_writer CREATE in schema research', has_schema_privilege('data_writer', 'research', 'CREATE')::text, 'false'),
  ('data_writer SELECT ops_jobs.job_flex_ingest', has_table_privilege('data_writer', 'ops_jobs.job_flex_ingest', 'SELECT')::text, 'false'),
  ('data_writer SELECT ops_feedback.report', has_table_privilege('data_writer', 'ops_feedback.report', 'SELECT')::text, 'false'),
  ('data_writer CREATE in schema public', has_schema_privilege('data_writer', 'public', 'CREATE')::text, 'false'),
  -- flex_writer (flex-query): what it needs
  ('flex_writer LOGIN NOINHERIT, no memberships',
     ((SELECT rolcanlogin AND NOT rolinherit FROM pg_roles WHERE rolname = 'flex_writer')
      AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE member = 'flex_writer'::regrole))::text, 'true'),
  ('flex_writer statement_timeout=2s', coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting WHERE setrole = 'flex_writer'::regrole AND setdatabase = 0), false)::text, 'true'),
  ('flex ops_jobs tables owned by flex_writer',
     (SELECT count(*) FROM pg_class WHERE relowner = 'flex_writer'::regrole AND oid IN ('ops_jobs.job_flex_ingest'::regclass,
        'ops_jobs.flex_ingest_freshness'::regclass, 'ops_jobs.flex_worker_heartbeat'::regclass, 'ops_jobs.flex_settings'::regclass))::text, '4'),
  ('flex_writer USAGE, CREATE on ops_jobs', has_schema_privilege('flex_writer', 'ops_jobs', 'USAGE, CREATE')::text, 'true'),
  ('flex_writer S/I/U raw_broker.executions_raw_flex', has_table_privilege('flex_writer', 'raw_broker.executions_raw_flex', 'SELECT, INSERT, UPDATE')::text, 'true'),
  ('flex_writer S/I/U raw_broker.commissions', has_table_privilege('flex_writer', 'raw_broker.commissions', 'SELECT, INSERT, UPDATE')::text, 'true'),
  ('flex_writer S/I/U raw_broker.transactions', has_table_privilege('flex_writer', 'raw_broker.transactions', 'SELECT, INSERT, UPDATE')::text, 'true'),
  ('flex_writer S/I/D raw_broker.settings_flex', has_table_privilege('flex_writer', 'raw_broker.settings_flex', 'SELECT, INSERT, DELETE')::text, 'true'),
  ('flex_writer SELECT raw_broker.positions', has_table_privilege('flex_writer', 'raw_broker.positions', 'SELECT')::text, 'true'),
  ('flex_writer USAGE executions_raw_flex sequence', has_sequence_privilege('flex_writer', 'raw_broker.executions_raw_flex_executions_raw_flex_id_seq', 'USAGE')::text, 'true'),
  -- flex_writer: what it must not have (F3: no tws / journal)
  ('flex_writer SELECT raw_broker.executions_raw_tws', has_table_privilege('flex_writer', 'raw_broker.executions_raw_tws', 'SELECT')::text, 'false'),
  ('flex_writer INSERT raw_broker.executions_raw_journal', has_table_privilege('flex_writer', 'raw_broker.executions_raw_journal', 'INSERT')::text, 'false'),
  ('flex_writer UPDATE raw_broker.positions', has_table_privilege('flex_writer', 'raw_broker.positions', 'UPDATE')::text, 'false'),
  ('flex_writer INSERT raw_broker.account', has_table_privilege('flex_writer', 'raw_broker.account', 'INSERT')::text, 'false'),
  ('flex_writer DELETE raw_broker.executions_raw_flex', has_table_privilege('flex_writer', 'raw_broker.executions_raw_flex', 'DELETE')::text, 'false'),
  ('flex_writer TRUNCATE raw_broker.settings_flex', has_table_privilege('flex_writer', 'raw_broker.settings_flex', 'TRUNCATE')::text, 'false'),
  ('flex_writer CREATE in schema raw_broker', has_schema_privilege('flex_writer', 'raw_broker', 'CREATE')::text, 'false'),
  ('flex_writer SELECT ops_jobs.job_ingest', has_table_privilege('flex_writer', 'ops_jobs.job_ingest', 'SELECT')::text, 'false'),
  ('flex_writer USAGE schema raw_market', has_schema_privilege('flex_writer', 'raw_market', 'USAGE')::text, 'false'),
  ('flex_writer SELECT ops_feedback.report', has_table_privilege('flex_writer', 'ops_feedback.report', 'SELECT')::text, 'false'),
  ('flex_writer may SET ROLE bifrost', pg_has_role('flex_writer', 'bifrost', 'SET')::text, 'false'),
  -- the shared schema, bifrost, and everyone else who reads these schemas
  ('owner of schema ops_jobs', pg_get_userbyid((SELECT nspowner FROM pg_namespace WHERE nspname = 'ops_jobs')), 'postgres'),
  ('ops_jobs functions not owned by postgres',
     (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
       WHERE n.nspname = 'ops_jobs' AND p.proowner <> 'postgres'::regrole)::text, '0'),
  ('objects bifrost owns in raw_market / ops_jobs',
     (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relowner = 'bifrost'::regrole)::text, '0'),
  ('bifrost SELECT raw_market.stock_daily (bridge removed)', has_table_privilege('bifrost', 'raw_market.stock_daily', 'SELECT')::text, 'false'),
  ('bifrost USAGE schema ops_jobs (bridge removed)', has_schema_privilege('bifrost', 'ops_jobs', 'USAGE')::text, 'false'),
  ('analytics_writer SELECT raw_market.stock_daily', has_table_privilege('analytics_writer', 'raw_market.stock_daily', 'SELECT')::text, 'true'),
  ('analytics_writer SELECT ops_jobs.watchlist_cache', has_table_privilege('analytics_writer', 'ops_jobs.watchlist_cache', 'SELECT')::text, 'true'),
  ('analytics_writer EXECUTE ensure_month_partitions', has_function_privilege('analytics_writer', 'ops_jobs.ensure_month_partitions(text,text,integer,integer)', 'EXECUTE')::text, 'true'),
  ('market_reader SELECT ops_jobs.job_ingest', has_table_privilege('market_reader', 'ops_jobs.job_ingest', 'SELECT')::text, 'true'),
  ('brokerage_reader SELECT raw_market.ticker (Trade market.* FDW)', has_table_privilege('brokerage_reader', 'raw_market.ticker', 'SELECT')::text, 'true'),
  ('analytics_reader SELECT ops_jobs.job_flex_ingest', has_table_privilege('analytics_reader', 'ops_jobs.job_flex_ingest', 'SELECT')::text, 'true')
) AS t(check_name, actual, expected)
ORDER BY ok, check_name;

-- Rights outside each role's set (expected: no rows).
SELECT 'data_writer' AS who, n.nspname AS schema, c.relname AS object, a.privilege_type
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a
WHERE a.grantee = 'data_writer'::regrole AND c.relowner <> 'data_writer'::regrole
  AND NOT (a.privilege_type = 'SELECT' AND c.oid IN ('research.option_universe'::regclass, 'research.option_pinned_contract'::regclass,
        'features.option_metric_atm_iv_daily'::regclass, 'features.option_metric_iv_percentile_daily'::regclass,
        'features.option_metric_max_pain_daily'::regclass, 'features.option_metric_pcr_daily'::regclass))
  AND NOT (a.privilege_type = 'SELECT' AND n.nspname = 'dw_stock')
UNION ALL
SELECT 'flex_writer', n.nspname, c.relname, a.privilege_type
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a
WHERE a.grantee = 'flex_writer'::regrole AND c.relowner <> 'flex_writer'::regrole
  AND NOT (n.nspname = 'raw_broker' AND (c.relname, a.privilege_type) IN (
        ('executions_raw_flex', 'SELECT'), ('executions_raw_flex', 'INSERT'), ('executions_raw_flex', 'UPDATE'),
        ('commissions', 'SELECT'), ('commissions', 'INSERT'), ('commissions', 'UPDATE'),
        ('transactions', 'SELECT'), ('transactions', 'INSERT'), ('transactions', 'UPDATE'),
        ('settings_flex', 'SELECT'), ('settings_flex', 'INSERT'), ('settings_flex', 'DELETE'),
        ('positions', 'SELECT'),
        ('executions_raw_flex_executions_raw_flex_id_seq', 'USAGE'),
        ('transactions_account_transactions_id_seq', 'USAGE'),
        ('settings_flex_id_seq', 'USAGE')))
ORDER BY 1, 2, 3, 4;
