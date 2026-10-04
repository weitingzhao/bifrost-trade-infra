-- D6 dry-run (read-only; bifrost_golden_source; run with default_transaction_read_only=on).
-- The two Ops plugins stop signing in as bifrost (Owner 2026-10-04, D6 = P1): market-data as data_writer
-- (owner of raw_market and of the market side of ops_jobs), flex-query as the new flex_writer (owner of its
-- four ops_jobs tables, minimal raw_broker DML, read-only on the Trade database it reads).
--
-- 1. Objects and owners the steps move (expected today: raw_market 165 relations + 2 sequences, all bifrost;
--    ops_jobs 7 market + 4 flex tables, 3 sequences, 5 functions, all bifrost; schemas raw_market / ops_jobs
--    owned by bifrost).
-- 2. Phase: which of the four steps look done (roles / grants / ownership / close).
-- 3. Needs matrix: every right the plugins use, held DIRECTLY by the new role now?
-- 4. What data_writer holds today that it will lose in step 4 (raw_broker, features writes, flex tables).

\echo '== 1. objects to move (schema, kind, owner, count)'
SELECT n.nspname AS schema,
       CASE c.relkind WHEN 'r' THEN CASE WHEN c.relispartition THEN 'partition' ELSE 'table' END
                      WHEN 'p' THEN 'partitioned table' WHEN 'v' THEN 'view' WHEN 'S' THEN 'sequence'
                      WHEN 'i' THEN 'index' WHEN 'I' THEN 'partitioned index' ELSE c.relkind::text END AS kind,
       pg_get_userbyid(c.relowner) AS owner,
       CASE WHEN n.nspname = 'ops_jobs' AND c.relname ~ '^(job_flex_ingest|flex_)' THEN 'flex' ELSE 'market' END AS side,
       count(*) AS n
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relkind IN ('r', 'p', 'v', 'S', 'm', 'i', 'I')
GROUP BY 1, 2, 3, 4 ORDER BY 1, 4, 2, 3;

SELECT 'function' AS kind, p.oid::regprocedure AS object, pg_get_userbyid(p.proowner) AS owner,
       p.prosecdef AS security_definer, p.proacl AS acl
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'ops_jobs' ORDER BY 2;

SELECT 'schema' AS kind, nspname AS object, pg_get_userbyid(nspowner) AS owner, nspacl AS acl
FROM pg_namespace WHERE nspname IN ('raw_market', 'ops_jobs', 'raw_broker', 'features', 'research', 'dw_stock')
ORDER BY 2;

\echo '== 2. phase'
WITH r AS (
  SELECT
    (SELECT count(*) FROM pg_roles WHERE rolname = 'flex_writer') = 1 AS flex_writer_exists,
    coalesce((SELECT rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname = 'flex_writer'), false) AS flex_writer_password,
    coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting
               WHERE setrole = 'data_writer'::regrole AND setdatabase = 0), false) AS data_writer_settings,
    has_schema_privilege('data_writer', 'features', 'USAGE')
      AND has_table_privilege('data_writer', 'research.option_universe', 'SELECT') AS step2_data_writer_reads,
    to_regrole('flex_writer') IS NOT NULL
      AND has_table_privilege('flex_writer', 'raw_broker.executions_raw_flex', 'INSERT') AS step2_flex_grants,
    (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'raw_market') = 'data_writer' AS step3_raw_market_owned,
    (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'ops_jobs.job_flex_ingest'::regclass) = 'flex_writer' AS step3_flex_owned,
    (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'ops_jobs') = 'postgres' AS step3_ops_jobs_schema_postgres,
    NOT has_table_privilege('data_writer', 'raw_broker.account', 'SELECT')
      AND NOT has_table_privilege('bifrost', 'raw_market.stock_daily', 'SELECT') AS step4_closed
)
SELECT * FROM r;

\echo '== 3. needs (direct = held by the role itself, not through a membership)'
WITH need(who, what, ok) AS (VALUES
  -- data_writer (market-data): connection and settings
  ('data_writer', 'CONNECT bifrost_golden_source', has_database_privilege('data_writer', 'bifrost_golden_source', 'CONNECT')),
  ('data_writer', 'TEMP bifrost_golden_source (conditional CREATE OR REPLACE VIEW paths)', has_database_privilege('data_writer', 'bifrost_golden_source', 'TEMPORARY')),
  ('data_writer', 'explicit CONNECT (survives a later REVOKE CONNECT FROM PUBLIC)',
     EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
             WHERE d.datname = 'bifrost_golden_source' AND a.grantee = 'data_writer'::regrole AND a.privilege_type = 'CONNECT')),
  ('data_writer', 'role setting statement_timeout=2s (was bifrost''s)', coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting WHERE setrole = 'data_writer'::regrole AND setdatabase = 0), false)),
  ('data_writer', 'NOT a member of bifrost', NOT pg_has_role('data_writer', 'bifrost', 'MEMBER')),
  -- writes and DDL in its own schemas
  ('data_writer', 'owner of schema raw_market', (SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market') = 'data_writer'::regrole),
  ('data_writer', 'owner of every raw_market relation (migrate Job DDL, partitions)',
     NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'raw_market' AND c.relkind IN ('r', 'p', 'v', 'S', 'm') AND c.relowner <> 'data_writer'::regrole)),
  ('data_writer', 'owner of the 7 market ops_jobs tables',
     (SELECT count(*) FROM pg_class WHERE oid IN ('ops_jobs.job_ingest'::regclass, 'ops_jobs.ingest_freshness'::regclass,
        'ops_jobs.queue_sample'::regclass, 'ops_jobs.coverage_sample'::regclass, 'ops_jobs.data_source_void'::regclass,
        'ops_jobs.symbol_source_void'::regclass, 'ops_jobs.watchlist_cache'::regclass) AND relowner = 'data_writer'::regrole) = 7),
  ('data_writer', 'USAGE, CREATE on schema ops_jobs (CREATE TABLE IF NOT EXISTS coverage_sample)',
     has_schema_privilege('data_writer', 'ops_jobs', 'USAGE, CREATE')),
  ('data_writer', 'EXECUTE ops_jobs.ensure_month_partitions', has_function_privilege('data_writer', 'ops_jobs.ensure_month_partitions(text,text,integer,integer)', 'EXECUTE')),
  ('data_writer', 'EXECUTE ops_jobs.drop_month_partitions_older_than', has_function_privilege('data_writer', 'ops_jobs.drop_month_partitions_older_than(text,text,integer)', 'EXECUTE')),
  -- reads of what Research publishes (M4)
  ('data_writer', 'USAGE schema research / features / dw_stock',
     has_schema_privilege('data_writer', 'research', 'USAGE') AND has_schema_privilege('data_writer', 'features', 'USAGE')
     AND has_schema_privilege('data_writer', 'dw_stock', 'USAGE')),
  ('data_writer', 'SELECT research.option_universe', has_table_privilege('data_writer', 'research.option_universe', 'SELECT')),
  ('data_writer', 'SELECT research.option_pinned_contract', has_table_privilege('data_writer', 'research.option_pinned_contract', 'SELECT')),
  ('data_writer', 'SELECT features.option_metric_{atm_iv,iv_percentile,max_pain,pcr}_daily (4)',
     has_table_privilege('data_writer', 'features.option_metric_atm_iv_daily', 'SELECT')
     AND has_table_privilege('data_writer', 'features.option_metric_iv_percentile_daily', 'SELECT')
     AND has_table_privilege('data_writer', 'features.option_metric_max_pain_daily', 'SELECT')
     AND has_table_privilege('data_writer', 'features.option_metric_pcr_daily', 'SELECT')),
  ('data_writer', 'SELECT dw_stock.mart_sepa_fundamental_eval', has_table_privilege('data_writer', 'dw_stock.mart_sepa_fundamental_eval', 'SELECT')),
  ('data_writer', 'default SELECT on tables analytics_writer creates in dw_stock (dbt table swap)',
     EXISTS (SELECT 1 FROM pg_default_acl d, aclexplode(d.defaclacl) a
             WHERE d.defaclrole = 'analytics_writer'::regrole AND d.defaclnamespace = 'dw_stock'::regnamespace
               AND d.defaclobjtype = 'r' AND a.grantee = 'data_writer'::regrole AND a.privilege_type = 'SELECT')),
  -- flex_writer (flex-query)
  ('flex_writer', 'role exists, LOGIN, NOINHERIT, no memberships',
     coalesce((SELECT rolcanlogin AND NOT rolinherit AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
               FROM pg_roles WHERE rolname = 'flex_writer'), false)
     AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE member = to_regrole('flex_writer'))),
  ('flex_writer', 'role setting statement_timeout=2s', coalesce((SELECT 'statement_timeout=2s' = ANY (setconfig) FROM pg_db_role_setting WHERE setrole = to_regrole('flex_writer') AND setdatabase = 0), false))
)
SELECT who, what, ok FROM need ORDER BY ok, who, what;

-- flex_writer needs (only meaningful once the role exists; NULL before step 1).
SELECT 'flex_writer' AS who, what, ok FROM (VALUES
  ('CONNECT bifrost_golden_source (explicit)', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE
     EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a WHERE d.datname = 'bifrost_golden_source'
             AND a.grantee = to_regrole('flex_writer') AND a.privilege_type = 'CONNECT') END),
  ('USAGE, CREATE on schema ops_jobs (ensure_flex_ops_schema: CREATE TABLE IF NOT EXISTS)', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE has_schema_privilege('flex_writer', 'ops_jobs', 'USAGE, CREATE') END),
  ('owner of ops_jobs.job_flex_ingest / flex_ingest_freshness / flex_worker_heartbeat / flex_settings (ALTER … ADD COLUMN IF NOT EXISTS)',
     CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE
     (SELECT count(*) FROM pg_class WHERE oid IN ('ops_jobs.job_flex_ingest'::regclass, 'ops_jobs.flex_ingest_freshness'::regclass,
        'ops_jobs.flex_worker_heartbeat'::regclass, 'ops_jobs.flex_settings'::regclass) AND relowner = to_regrole('flex_writer')) = 4 END),
  ('S/I/U raw_broker.executions_raw_flex, commissions, transactions (upserts)', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE
     has_table_privilege('flex_writer', 'raw_broker.executions_raw_flex', 'SELECT, INSERT, UPDATE')
     AND has_table_privilege('flex_writer', 'raw_broker.commissions', 'SELECT, INSERT, UPDATE')
     AND has_table_privilege('flex_writer', 'raw_broker.transactions', 'SELECT, INSERT, UPDATE') END),
  ('S/I/D raw_broker.settings_flex (replace the query rows)', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE has_table_privilege('flex_writer', 'raw_broker.settings_flex', 'SELECT, INSERT, DELETE') END),
  ('SELECT raw_broker.positions (coverage)', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE has_table_privilege('flex_writer', 'raw_broker.positions', 'SELECT') END),
  ('USAGE on the 3 raw_broker sequences', CASE WHEN to_regrole('flex_writer') IS NULL THEN NULL ELSE
     has_sequence_privilege('flex_writer', 'raw_broker.executions_raw_flex_executions_raw_flex_id_seq', 'USAGE')
     AND has_sequence_privilege('flex_writer', 'raw_broker.transactions_account_transactions_id_seq', 'USAGE')
     AND has_sequence_privilege('flex_writer', 'raw_broker.settings_flex_id_seq', 'USAGE') END)
) AS t(what, ok) ORDER BY ok NULLS FIRST, what;

\echo '== 4. data_writer today, outside raw_market and the market ops_jobs tables (step 4 revokes these)'
SELECT n.nspname AS schema, c.relname AS object, c.relkind,
       string_agg(a.privilege_type, ',' ORDER BY a.privilege_type) AS privileges
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a
WHERE a.grantee = 'data_writer'::regrole AND c.relowner <> 'data_writer'::regrole
  AND n.nspname <> 'raw_market'
  AND NOT (n.nspname = 'ops_jobs' AND c.relname IN ('job_ingest', 'job_ingest_id_seq', 'ingest_freshness', 'queue_sample',
          'coverage_sample', 'coverage_sample_coverage_sample_id_seq', 'data_source_void', 'symbol_source_void', 'watchlist_cache'))
  AND NOT (n.nspname IN ('features', 'research', 'dw_stock') AND a.privilege_type = 'SELECT')
GROUP BY 1, 2, 3 ORDER BY 1, 2;

SELECT 'default acl' AS kind, pg_get_userbyid(d.defaclrole) AS for_role, d.defaclnamespace::regnamespace AS schema,
       d.defaclobjtype, a.privilege_type
FROM pg_default_acl d, aclexplode(d.defaclacl) a
WHERE a.grantee = 'data_writer'::regrole AND d.defaclnamespace = 'raw_broker'::regnamespace
ORDER BY 2, 3, 4, 5;

\echo '== 5. sessions by user right now (the plugins sign in as bifrost until the switch)'
SELECT usename, datname, count(*) FROM pg_stat_activity
WHERE usename IN ('bifrost', 'data_writer', 'flex_writer') GROUP BY 1, 2 ORDER BY 1, 2;
