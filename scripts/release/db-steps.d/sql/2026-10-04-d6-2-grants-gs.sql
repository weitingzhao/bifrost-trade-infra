-- D6 step 2 of 4, Golden Source part (as postgres, bifrost_golden_source, one transaction). Additive only:
-- nothing bifrost or anyone else holds is taken away, so the running plugins (still bifrost) are untouched.
-- After it the two roles hold every right their plugin uses EXCEPT ownership (step 3).
--
-- data_writer (market-data):
--   * CONNECT, TEMPORARY on the database, explicit (today it has them through PUBLIC only).
--   * M4 (Owner: plugins may read what Research publishes, read-only): USAGE on research / features /
--     dw_stock; SELECT on research.option_universe, research.option_pinned_contract,
--     features.option_metric_{atm_iv,iv_percentile,max_pain,pcr}_daily, dw_stock.mart_sepa_fundamental_eval.
--     dw_stock marts are dbt tables rebuilt nightly (create + rename), so a table grant dies with the old
--     table: the read comes from analytics_writer's default privileges in dw_stock, the same way bifrost's
--     does today (bifrost=r/analytics_writer). SELECT only on future dw_stock tables, nothing else.
--   (It already holds every DML right on raw_market and on the market tables of ops_jobs, plus USAGE /
--    CREATE on both schemas and EXECUTE on the partition helpers.)
--
-- flex_writer (flex-query):
--   * CONNECT on the database; USAGE, CREATE on ops_jobs (its ensure path runs CREATE TABLE IF NOT EXISTS,
--     which checks CREATE before it checks existence).
--   * S/I/U/D on its four ops_jobs tables + the job sequence. Step 3 makes it their owner; until then
--     these grants let it run if the Owner switches before step 3 (the plan's order is 3 before switch).
--   * F3 (Owner: no tws / journal tables): raw_broker USAGE; S/I/U on executions_raw_flex, commissions,
--     transactions (INSERT … ON CONFLICT DO UPDATE); S/I/D on settings_flex (delete-all + insert);
--     SELECT on positions (coverage); USAGE on the three sequences behind those inserts.
--
-- Idempotent. Rollback: sql/2026-10-04-d6-rollback-gs.sql.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $d6$
BEGIN
  IF to_regrole('flex_writer') IS NULL THEN
    RAISE EXCEPTION 'd6: role flex_writer is missing: run sql/2026-10-04-d6-1-roles.sql first';
  END IF;
  IF current_database() <> 'bifrost_golden_source' THEN
    RAISE EXCEPTION 'd6: run this in bifrost_golden_source, not %', current_database();
  END IF;
END
$d6$;

-- data_writer
GRANT CONNECT, TEMPORARY ON DATABASE bifrost_golden_source TO data_writer;
GRANT USAGE ON SCHEMA research, features, dw_stock TO data_writer;
GRANT SELECT ON research.option_universe, research.option_pinned_contract,
                features.option_metric_atm_iv_daily, features.option_metric_iv_percentile_daily,
                features.option_metric_max_pain_daily, features.option_metric_pcr_daily,
                dw_stock.mart_sepa_fundamental_eval
  TO data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE analytics_writer IN SCHEMA dw_stock GRANT SELECT ON TABLES TO data_writer;

-- flex_writer
GRANT CONNECT ON DATABASE bifrost_golden_source TO flex_writer;
GRANT USAGE, CREATE ON SCHEMA ops_jobs TO flex_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ops_jobs.job_flex_ingest, ops_jobs.flex_ingest_freshness,
                                        ops_jobs.flex_worker_heartbeat, ops_jobs.flex_settings
  TO flex_writer;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE ops_jobs.job_flex_ingest_id_seq TO flex_writer;
GRANT USAGE ON SCHEMA raw_broker TO flex_writer;
GRANT SELECT, INSERT, UPDATE ON raw_broker.executions_raw_flex, raw_broker.commissions, raw_broker.transactions
  TO flex_writer;
GRANT SELECT, INSERT, DELETE ON raw_broker.settings_flex TO flex_writer;
GRANT SELECT ON raw_broker.positions TO flex_writer;
GRANT USAGE ON SEQUENCE raw_broker.executions_raw_flex_executions_raw_flex_id_seq,
                        raw_broker.transactions_account_transactions_id_seq,
                        raw_broker.settings_flex_id_seq
  TO flex_writer;

COMMIT;
