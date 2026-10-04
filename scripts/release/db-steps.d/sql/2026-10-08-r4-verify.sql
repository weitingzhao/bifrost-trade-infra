-- Naming R4 verify (read-only; run with default_transaction_read_only=on), any env, after the commit.
-- Expect: the four objects absent (all present = f); strategy_instance_id only on the three
-- Golden Source foreign tables (frozen columns, D10'-A), on no view; the counts as the precheck printed.
SELECT o AS object, to_regclass(o) IS NOT NULL AS present
FROM unnest(ARRAY['public.strategy_instance', 'public.strategy_instance_execution',
                  'brokerage.instance_allocations', 'public.account_execution_instance_allocation']) o
ORDER BY 1;

SELECT c.table_name, t.table_type
FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema IN ('public', 'brokerage') AND c.column_name = 'strategy_instance_id'
ORDER BY 1;

SELECT count(*) AS sequences_left FROM pg_class
WHERE relkind = 'S' AND relname LIKE 'account_execution_instance_al%';

SELECT (SELECT count(*) FROM public.trade) AS trade,
       (SELECT count(*) FROM public.trade_execution) AS trade_execution,
       (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS splits,
       (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS view_attributed,
       (SELECT count(*) FROM brokerage.trade_fill_splits) AS view_splits;

-- TD-85: the runtime role trade_app_<env> (derived from the database name) reads the five rebuilt
-- env views. Expect role_exists = t and every select = t.
SELECT 'trade_app_' || substr(current_database(), 9) AS runtime_role,
       to_regrole('trade_app_' || substr(current_database(), 9)) IS NOT NULL AS role_exists;
SELECT v AS env_view, pg_get_userbyid(c.relowner) AS owner,
       CASE WHEN to_regrole('trade_app_' || substr(current_database(), 9)) IS NULL THEN NULL
            ELSE has_table_privilege('trade_app_' || substr(current_database(), 9), v, 'SELECT') END AS runtime_select
FROM unnest(ARRAY['brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly',
                  'brokerage.executions_tws', 'brokerage.trade_fill_splits']) v
JOIN pg_class c ON c.oid = to_regclass(v)
ORDER BY 1;
