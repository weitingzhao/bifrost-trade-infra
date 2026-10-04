-- Rollback of 2026-10-04-td85-dev-fdw-owner.sql: the 20 DEV objects and schema market back to
-- postgres, with bifrost's read grant restored (an owner change moves the old owner's rights
-- to the new owner, so going back leaves bifrost with nothing unless granted again).
--   psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < this file
\set ON_ERROR_STOP on

SELECT current_database() = 'bifrost_dev' AS td85_right_db \gset
\if :td85_right_db
\else
  \echo 'td85: run this file in bifrost_dev'
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';

CREATE TEMP TABLE td85_objs (nsp text, rel text, kind text) ON COMMIT DROP;
INSERT INTO td85_objs VALUES
  ('brokerage', 'account', 'f'), ('brokerage', 'commissions', 'f'), ('brokerage', 'contract_quote_live', 'f'),
  ('brokerage', 'executions_raw_flex', 'f'), ('brokerage', 'executions_raw_journal', 'f'),
  ('brokerage', 'executions_raw_tws', 'f'), ('brokerage', 'open_orders', 'f'), ('brokerage', 'positions', 'f'),
  ('brokerage', 'settings_flex', 'f'), ('brokerage', 'transactions', 'f'),
  ('brokerage', 'executions', 'v'), ('brokerage', 'executions_final', 'v'), ('brokerage', 'executions_fly', 'v'),
  ('brokerage', 'executions_tws', 'v'), ('brokerage', 'instance_allocations', 'v'),
  ('brokerage', 'trade_fill_splits', 'v'),
  ('market', 'ticker', 'f'), ('market', 'ticker_related', 'f'), ('market', 'us_market_holiday', 'f'),
  ('market', 'v_us_equity_universe', 'v');

SELECT 'ALTER SCHEMA market OWNER TO postgres'
 WHERE (SELECT nspowner FROM pg_namespace WHERE nspname = 'market') = 'bifrost'::regrole
\gexec
GRANT USAGE ON SCHEMA market TO bifrost;

SELECT format('ALTER %s %I.%I OWNER TO postgres',
              CASE c.relkind WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'v' THEN 'VIEW' END, n.nspname, c.relname)
  FROM td85_objs o
  JOIN pg_namespace n ON n.nspname = o.nsp
  JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = o.rel AND c.relkind::text = o.kind
 WHERE c.relowner = 'bifrost'::regrole
\gexec

SELECT format('GRANT SELECT ON %I.%I TO bifrost', o.nsp, o.rel) FROM td85_objs o
\gexec

COMMIT;

SELECT n.nspname, c.relkind::text AS kind, pg_get_userbyid(c.relowner) AS owner, c.relacl::text AS acl, count(*)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('brokerage', 'market') AND c.relkind IN ('f', 'v')
 GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3;
