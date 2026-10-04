-- Naming R4 precheck (read-only; run with default_transaction_read_only=on), any env.
-- Expect (2026-10-04, all three envs): env_views_with_compat_column = 5 and instance_allocations_view = t --
-- db-init does not rebuild the env views (its FDW step is skipped), the R4 step does; the 9 objects owned by
-- bifrost; legacy_rows = 2 = legacy_rows_in_trade_execution; no other view depending on them; core_version
-- of the env = 0.47.0 (checked over HTTP, see the step file). TD-85: role_exists = t, bifrost may use
-- TEMP and CREATE in brokerage (the step creates a temp table and the views as bifrost), bifrost's
-- default privileges in brokerage name trade_app_<env> (the step also grants explicitly), and
-- trade_app_<env> reads the five env views today (runtime_select = t).
SELECT current_database() AS db, now() AS read_at;

SELECT o AS object, c.relkind, pg_get_userbyid(c.relowner) AS owner
FROM unnest(ARRAY['public.strategy_instance', 'public.strategy_instance_execution',
                  'brokerage.instance_allocations', 'public.account_execution_instance_allocation',
                  'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly',
                  'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o
LEFT JOIN pg_class c ON c.oid = to_regclass(o)
ORDER BY 1;

SELECT count(*) AS env_views_with_compat_column
FROM information_schema.columns c JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema = 'brokerage' AND c.column_name = 'strategy_instance_id' AND t.table_type = 'VIEW';

SELECT to_regclass('brokerage.instance_allocations') IS NOT NULL AS instance_allocations_view;

SELECT (SELECT count(*) FROM public.account_execution_instance_allocation) AS legacy_rows,
       (SELECT count(*) FROM public.account_execution_instance_allocation a
         WHERE EXISTS (SELECT 1 FROM public.trade_execution te
                       JOIN brokerage.executions x ON x.account_id = te.account_id AND x.exec_id = te.exec_id
                       WHERE x.account_executions_id = a.account_executions_id
                         AND te.account_id = a.account_id AND te.trade_id = a.strategy_instance_id
                         AND te.split_quantity = a.allocated_quantity::numeric)) AS legacy_rows_in_trade_execution;

-- Views that depend on the 9 objects, other than the 9 themselves: expect 0 rows (the rebuild uses CASCADE).
WITH s(o) AS (SELECT to_regclass(x) FROM unnest(ARRAY['public.strategy_instance', 'public.strategy_instance_execution',
                  'brokerage.instance_allocations', 'public.account_execution_instance_allocation',
                  'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly',
                  'brokerage.executions_tws', 'brokerage.trade_fill_splits']) x)
SELECT DISTINCT d.refobjid::regclass AS depended_on, c.oid::regclass AS dependent, c.relkind
FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class c ON c.oid = r.ev_class
WHERE d.refobjid IN (SELECT o FROM s) AND c.oid <> d.refobjid AND c.oid NOT IN (SELECT o FROM s WHERE o IS NOT NULL);

-- The counts the commit's report compares (they must not move across the drop).
SELECT (SELECT count(*) FROM public.trade) AS trade,
       (SELECT count(*) FROM public.trade_execution) AS trade_execution,
       (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS splits,
       (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS view_attributed,
       (SELECT count(*) FROM brokerage.trade_fill_splits) AS view_splits;

-- TD-85 (runtime role trade_app_<env>, derived from the database name; read-only).
SELECT 'trade_app_' || substr(current_database(), 9) AS runtime_role,
       to_regrole('trade_app_' || substr(current_database(), 9)) IS NOT NULL AS role_exists,
       has_database_privilege('bifrost', current_database(), 'TEMP') AS bifrost_temp,
       has_schema_privilege('bifrost', 'brokerage', 'CREATE') AS bifrost_create_brokerage;
SELECT pg_get_userbyid(d.defaclrole) AS for_role, n.nspname AS in_schema, d.defaclobjtype AS objtype, d.defaclacl
FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace
WHERE n.nspname = 'brokerage' ORDER BY 1, 3;
SELECT v AS env_view,
       CASE WHEN to_regrole('trade_app_' || substr(current_database(), 9)) IS NULL THEN NULL
            ELSE has_table_privilege('trade_app_' || substr(current_database(), 9), v, 'SELECT') END AS runtime_select
FROM unnest(ARRAY['brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly',
                  'brokerage.executions_tws', 'brokerage.trade_fill_splits']) v
WHERE to_regclass(v) IS NOT NULL
ORDER BY 1;
