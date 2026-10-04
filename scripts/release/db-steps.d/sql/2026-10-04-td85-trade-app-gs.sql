-- TD-85 D1 (Owner 2026-10-04): the three Trade runtime roles and their Golden Source grants.
-- Run once, as postgres, in bifrost_golden_source:
--   psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < this file
-- Idempotent: a second run changes nothing. No password here: a role is created without one,
-- and scripts/trade-app-role.sh password <env> sets it later (a SCRAM verifier on stdin).
--
-- What the Trade runtime does in Golden Source (measured from core 0.45.0 / api 0.7.3 / worker 0.2.4,
-- see the verify file): DML on raw_broker (account, positions, open_orders incl. TRUNCATE,
-- executions_raw_*, commissions, transactions, contract_quote_live). Nothing else: not features,
-- research, journal, dw_stock, raw_market, ops_jobs, ops_dagster, ops_dbt. ops_feedback is not
-- reached with these credentials (api-research uses ANALYTICS_PG_* today and FEEDBACK_PG_* /
-- feedback_writer from api 0.7.5); its grant is the optional file ...-td85-trade-app-ops-feedback.sql.
\set ON_ERROR_STOP on

SELECT current_database() = 'bifrost_golden_source' AS td85_right_db \gset
\if :td85_right_db
\else
  \echo 'td85: run this file in bifrost_golden_source'
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';

-- 1. Roles (cluster-wide). LOGIN, no password yet, NOINHERIT, member of nothing.
SELECT format('CREATE ROLE %I LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', r)
  FROM unnest(ARRAY['trade_app_dev', 'trade_app_stg', 'trade_app_prod']) AS r
 WHERE to_regrole(r) IS NULL
\gexec

COMMENT ON ROLE trade_app_dev IS 'TD-85: Trade runtime (api-*, daemon) of DEV: bifrost_dev DML + Golden Source raw_broker DML. DDL stays with bifrost (db-init).';
COMMENT ON ROLE trade_app_stg IS 'TD-85: Trade runtime (api-*, daemon) of STG: bifrost_stg DML + Golden Source raw_broker DML. DDL stays with bifrost (db-init).';
COMMENT ON ROLE trade_app_prod IS 'TD-85: Trade runtime (api-*, daemon) of PROD: bifrost_prod DML + Golden Source raw_broker DML. DDL stays with bifrost (db-init).';

-- 2. Role-level settings copied from bifrost (statement_timeout, lock_timeout,
--    idle_in_transaction_session_timeout today), so a session behaves as before.
SELECT format('ALTER ROLE %I SET %I = %L', r, split_part(s, '=', 1), substr(s, strpos(s, '=') + 1))
  FROM unnest(ARRAY['trade_app_dev', 'trade_app_stg', 'trade_app_prod']) AS r,
       (SELECT unnest(setconfig) AS s FROM pg_db_role_setting
         WHERE setrole = 'bifrost'::regrole AND setdatabase = 0) AS b
\gexec

-- 3. Golden Source: CONNECT, raw_broker DML.
GRANT CONNECT ON DATABASE bifrost_golden_source TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT USAGE ON SCHEMA raw_broker TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw_broker TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT TRUNCATE ON raw_broker.open_orders TO trade_app_dev, trade_app_stg, trade_app_prod;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA raw_broker TO trade_app_dev, trade_app_stg, trade_app_prod;

-- 4. Default privileges: what db-init (bifrost) creates in raw_broker later is usable at once.
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trade_app_dev, trade_app_stg, trade_app_prod;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO trade_app_dev, trade_app_stg, trade_app_prod;

COMMIT;

SELECT r.rolname, r.rolcanlogin AS login, r.rolinherit AS inherit,
       (a.rolpassword IS NOT NULL) AS has_password,
       (SELECT array_to_string(setconfig, ', ') FROM pg_db_role_setting
         WHERE setrole = r.oid AND setdatabase = 0) AS settings
  FROM pg_roles r JOIN pg_authid a ON a.oid = r.oid
 WHERE r.rolname LIKE 'trade\_app\_%' ORDER BY 1;
