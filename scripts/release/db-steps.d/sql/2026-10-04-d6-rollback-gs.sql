-- D6 rollback, Golden Source (as postgres, bifrost_golden_source, one transaction). Undoes steps 2-4 from
-- whatever point they reached; idempotent. Switch the plugins back FIRST (scripts/plugin-db-roles.sh
-- rollback market-data / rollback flex): after this file only bifrost owns raw_market / ops_jobs again.
--
-- Restores the state read (read-only) on 2026-10-04 13:xx UTC:
--   * raw_market (schema and every relation) and all eleven ops_jobs tables, the schema ops_jobs and its five
--     helper functions owned by bifrost. Objects data_writer created after D6 (new partitions) go to
--     bifrost too: that is who the pre-D6 plugin needs to own them.
--   * data_writer's direct rights as they were: ALL on every raw_market / ops_jobs table and sequence (the
--     move folded them into the owner entry), USAGE + CREATE on both schemas, EXECUTE on the helpers;
--     S/I/U/D/TRUNCATE on raw_broker's tables and views, SELECT + USAGE on its sequences, USAGE on the
--     schema, and bifrost's raw_broker default privileges for it; ALL on the four
--     features.option_metric_* parents; no USAGE on research / features / dw_stock, no SELECT on
--     research.* or dw_stock.*, no explicit CONNECT / TEMP (PUBLIC has them).
--   * flex_writer: nothing left in this database (the role itself goes with sql/…-rollback-roles.sql).
-- Other grantees' entries (analytics_*, market_reader, brokerage_*) survive every owner change unchanged.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '300s';

DO $d6$
DECLARE
  r     record;
  moved int := 0;
BEGIN
  IF current_database() <> 'bifrost_golden_source' THEN
    RAISE EXCEPTION 'd6: run this in bifrost_golden_source, not %', current_database();
  END IF;
  FOR r IN
    SELECT c.relkind, format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relkind IN ('r', 'p', 'v', 'm')
      AND c.relowner IN (to_regrole('data_writer'), coalesce(to_regrole('flex_writer'), 0::regrole))
    ORDER BY c.relispartition, n.nspname, c.relname
  LOOP
    EXECUTE format('ALTER %s %s OWNER TO bifrost',
                   CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END, r.fq);
    moved := moved + 1;
  END LOOP;
  FOR r IN
    SELECT format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relkind = 'S'
      AND c.relowner IN (to_regrole('data_writer'), coalesce(to_regrole('flex_writer'), 0::regrole))
  LOOP
    EXECUTE format('ALTER SEQUENCE %s OWNER TO bifrost', r.fq);
    moved := moved + 1;
  END LOOP;
  FOR r IN
    SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'ops_jobs' AND p.proowner <> 'bifrost'::regrole
  LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO bifrost', r.sig);
    moved := moved + 1;
  END LOOP;
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market') <> 'bifrost'::regrole THEN
    ALTER SCHEMA raw_market OWNER TO bifrost;
  END IF;
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'ops_jobs') <> 'bifrost'::regrole THEN
    ALTER SCHEMA ops_jobs OWNER TO bifrost;
  END IF;
  RAISE NOTICE 'd6 rollback: % object(s) back to bifrost (schemas too)', moved;
END
$d6$;

-- data_writer: rights folded into the owner entry come back as direct grants.
GRANT USAGE, CREATE ON SCHEMA raw_market, ops_jobs TO data_writer;
GRANT ALL ON ALL TABLES IN SCHEMA raw_market, ops_jobs TO data_writer;
GRANT ALL ON ALL SEQUENCES IN SCHEMA raw_market, ops_jobs TO data_writer;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ops_jobs TO data_writer;

-- data_writer: M5 undone.
GRANT USAGE ON SCHEMA raw_broker TO data_writer;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_broker TO data_writer;
GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA raw_broker TO data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker GRANT SELECT, USAGE ON SEQUENCES TO data_writer;

-- data_writer: M4 and the explicit database grant undone (features parents keep ALL, as before D6).
REVOKE SELECT ON research.option_universe, research.option_pinned_contract, dw_stock.mart_sepa_fundamental_eval FROM data_writer;
GRANT ALL ON features.option_metric_atm_iv_daily, features.option_metric_iv_percentile_daily,
             features.option_metric_max_pain_daily, features.option_metric_pcr_daily TO data_writer;
REVOKE ALL ON SCHEMA research, features, dw_stock FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE analytics_writer IN SCHEMA dw_stock REVOKE SELECT ON TABLES FROM data_writer;
REVOKE ALL ON DATABASE bifrost_golden_source FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE data_writer IN SCHEMA raw_market
  REVOKE SELECT ON TABLES FROM analytics_writer, analytics_reader, market_reader, brokerage_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE data_writer IN SCHEMA ops_jobs
  REVOKE SELECT ON TABLES FROM analytics_reader, market_reader;

-- flex_writer: nothing left here.
DO $d6$
BEGIN
  IF to_regrole('flex_writer') IS NOT NULL THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA raw_broker, ops_jobs FROM flex_writer;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_broker, ops_jobs FROM flex_writer;
    REVOKE ALL ON SCHEMA raw_broker, ops_jobs FROM flex_writer;
    REVOKE ALL ON DATABASE bifrost_golden_source FROM flex_writer;
    ALTER DEFAULT PRIVILEGES FOR ROLE flex_writer IN SCHEMA ops_jobs REVOKE SELECT ON TABLES FROM analytics_reader;
  END IF;
END
$d6$;

DO $d6$
DECLARE
  left_over int;
BEGIN
  SELECT count(*) INTO left_over FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relowner <> 'bifrost'::regrole;
  IF left_over > 0 THEN
    RAISE EXCEPTION 'd6 rollback: % object(s) in raw_market / ops_jobs are not owned by bifrost', left_over;
  END IF;
END
$d6$;

COMMIT;
