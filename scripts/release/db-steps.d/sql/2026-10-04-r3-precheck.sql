-- Naming R3 precheck (read-only; run with default_transaction_read_only=on). Same file for dev / stg / prod.
-- Before the rename: strategy_instance is a table, trade does not exist, every name the rename touches exists,
-- and the counts the step-8 report compares (expected values are in the db-step file).
SELECT current_database() AS db,
       (SELECT relkind FROM pg_class WHERE oid = to_regclass('public.strategy_instance')) AS strategy_instance_kind,  -- r
       to_regclass('public.trade') AS trade,                                                                           -- null
       (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('brokerage.executions')) AS view_owner; -- dev: postgres; stg / prod: bifrost

-- Names the rename expects (must be 0 missing).
SELECT n AS missing_name
FROM unnest(ARRAY[
  'strategy_instance', 'strategy_instance_strategy_instance_id_seq', 'strategy_instance_pkey', 'strategy_instance_id_account_uq',
  'strategy_instance_opportunity_id', 'strategy_instance_account_opened',
  'strategy_instance_execution', 'strategy_instance_execution_strategy_instance_execution_id_seq',
  'strategy_instance_execution_pkey', 'strategy_instance_execution_uq', 'strategy_instance_execution_whole_uq',
  'strategy_instance_execution_instance_ix', 'strategy_plan_instance', 'trade_review_strategy_instance_id_key'
]) AS n
WHERE to_regclass('public.' || n) IS NULL
UNION ALL
SELECT c AS missing_name
FROM unnest(ARRAY[
  'strategy_instance_strategy_opportunity_id_fkey', 'strategy_instance_execution_instance_fk',
  'strategy_instance_execution_qty_ck', 'strategy_plan_strategy_instance_id_fkey', 'trade_review_strategy_instance_id_fkey'
]) AS c
WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = c);

-- Columns the rename moves (6 rows), and that strategy_instance.notes is gone (0 rows in the second query).
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = 'public' AND (table_name, column_name) IN (
  ('strategy_instance', 'strategy_instance_id'), ('strategy_instance_execution', 'allocated_quantity'),
  ('strategy_plan', 'strategy_instance_id'), ('trade_review', 'strategy_instance_id'),
  ('trade_review', 'tags_added'), ('trade_review', 'tags_dropped'))
ORDER BY 1, 2;
SELECT column_name AS should_be_dropped FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'strategy_instance' AND column_name = 'notes';

-- What depends on the two tables (only the five brokerage views; nothing else may).
SELECT DISTINCT dv.relnamespace::regnamespace || '.' || dv.relname AS dependent_view
FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class dv ON dv.oid = r.ev_class
WHERE d.refobjid IN ('public.strategy_instance'::regclass, 'public.strategy_instance_execution'::regclass)
  AND dv.oid NOT IN ('public.strategy_instance'::regclass, 'public.strategy_instance_execution'::regclass)
ORDER BY 1;

-- The step-8 counts, before.
SELECT (SELECT count(*) FROM public.strategy_instance) AS trade,
       (SELECT count(*) FROM public.strategy_instance_execution) AS trade_execution,
       (SELECT count(*) FROM public.strategy_instance_execution WHERE allocated_quantity IS NOT NULL) AS splits,
       (SELECT count(*) FROM brokerage.executions WHERE strategy_instance_id IS NOT NULL) AS view_attributed,
       (SELECT count(*) FROM brokerage.instance_allocations) AS view_splits;
