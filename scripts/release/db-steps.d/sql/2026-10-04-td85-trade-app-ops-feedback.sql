-- OPTIONAL (not part of the default TD-85 run): ops_feedback DML for trade_app_<env>, the plan's
-- §2.2 row. Only needed if api-research's feedback store is pointed at bifrost-<env>-secrets'
-- GOLDEN_SOURCE_* (plan §3). It is not today: api <= 0.7.4 uses ANALYTICS_PG_* (analytics_writer)
-- and api 0.7.5 FEEDBACK_PG_* (feedback_writer, TD-49 D4, Owner 2026-10-03; S/I/U, no DELETE --
-- decision C, 2026-10-04). Same grant set as feedback_writer, so running it widens nothing that
-- decision C narrowed. Idempotent; as postgres, in bifrost_golden_source, after ...-trade-app-gs.sql.
--   psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < this file
\set ON_ERROR_STOP on

SELECT current_database() = 'bifrost_golden_source' AS td85_right_db \gset
\if :td85_right_db
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: run this file in bifrost_golden_source'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';
GRANT USAGE ON SCHEMA ops_feedback TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ops_feedback TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ops_feedback TO trade_app_dev, trade_app_stg, trade_app_prod;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback
  GRANT SELECT, INSERT, UPDATE ON TABLES TO trade_app_dev, trade_app_stg, trade_app_prod;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback
  GRANT USAGE ON SEQUENCES TO trade_app_dev, trade_app_stg, trade_app_prod;
COMMIT;
