-- TD-85 D8 (Owner 2026-10-04, each object named): DEV's brokerage / market FDW objects change
-- owner postgres -> bifrost, as in STG and PROD. Run once, as postgres, in bifrost_dev:
--   psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < this file
-- Effect beyond the catalog: a query through a brokerage.* / market.* view reads Golden Source
-- with the view owner's FDW user mapping. Owner postgres -> brokerage_writer (can write
-- raw_broker); owner bifrost -> brokerage_reader (read-only), like STG / PROD.
-- Every statement checks the current owner first, so a second run changes nothing.
\set ON_ERROR_STOP on

SELECT current_database() = 'bifrost_dev' AS td85_right_db \gset
\if :td85_right_db
\else
  \echo 'td85: run this file in bifrost_dev'
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';

-- The 20 objects, each by name (kind as the catalog has it today; read-only 2026-10-04).
SELECT format('ALTER %s %I.%I OWNER TO bifrost',
              CASE c.relkind WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'v' THEN 'VIEW' END, n.nspname, c.relname)
  FROM (VALUES
        ('brokerage', 'account', 'f'),
        ('brokerage', 'commissions', 'f'),
        ('brokerage', 'contract_quote_live', 'f'),
        ('brokerage', 'executions_raw_flex', 'f'),
        ('brokerage', 'executions_raw_journal', 'f'),
        ('brokerage', 'executions_raw_tws', 'f'),
        ('brokerage', 'open_orders', 'f'),
        ('brokerage', 'positions', 'f'),
        ('brokerage', 'settings_flex', 'f'),
        ('brokerage', 'transactions', 'f'),
        ('brokerage', 'executions', 'v'),
        ('brokerage', 'executions_final', 'v'),
        ('brokerage', 'executions_fly', 'v'),
        ('brokerage', 'executions_tws', 'v'),
        ('brokerage', 'instance_allocations', 'v'),
        ('brokerage', 'trade_fill_splits', 'v'),
        ('market', 'ticker', 'f'),
        ('market', 'ticker_related', 'f'),
        ('market', 'us_market_holiday', 'f'),
        ('market', 'v_us_equity_universe', 'v')
       ) AS want(nsp, rel, kind)
  JOIN pg_namespace n ON n.nspname = want.nsp
  JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = want.rel AND c.relkind::text = want.kind
 WHERE c.relowner = 'postgres'::regrole
 ORDER BY (c.relkind = 'v'), n.nspname, c.relname
\gexec

-- Item 21 (schema): market is owned by bifrost in STG / PROD, by postgres in DEV.
-- brokerage stays postgres-owned (as in STG / PROD).
SELECT 'ALTER SCHEMA market OWNER TO bifrost'
 WHERE (SELECT nspowner FROM pg_namespace WHERE nspname = 'market') = 'postgres'::regrole
\gexec

COMMIT;

SELECT n.nspname, c.relkind::text AS kind, pg_get_userbyid(c.relowner) AS owner, count(*)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('brokerage', 'market') AND c.relkind IN ('f', 'v')
 GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
SELECT nspname, pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname IN ('brokerage', 'market') ORDER BY 1;
