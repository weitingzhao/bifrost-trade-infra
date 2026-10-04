-- Naming R3 verify (read-only; run with default_transaction_read_only=on), after the commit. Same file for every env.
-- (pack §5.3, plus the compatibility objects and DEV's grants)
SELECT to_regclass('public.trade') AS trade, to_regclass('public.trade_execution') AS trade_execution,   -- both non-null
       (SELECT relkind FROM pg_class WHERE oid = 'public.strategy_instance'::regclass) AS strategy_instance_kind,             -- v
       (SELECT relkind FROM pg_class WHERE oid = 'public.strategy_instance_execution'::regclass) AS sie_kind,                -- v
       to_regclass('brokerage.trade_fill_splits') AS fill_splits, to_regclass('brokerage.instance_allocations') AS compat_splits;

-- The step-8 counts, after (must equal the expected values in the db-step file).
SELECT (SELECT count(*) FROM public.trade) AS trade,
       (SELECT count(*) FROM public.trade_execution) AS trade_execution,
       (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS splits,
       (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS view_attributed,
       (SELECT count(*) FROM brokerage.trade_fill_splits) AS view_splits,
       (SELECT count(*) FROM public.strategy_instance) AS compat_strategy_instance,
       (SELECT count(*) FROM brokerage.instance_allocations) AS compat_instance_allocations;

-- 4 rows: trade_id, ib_trade_id, ib_related_trade_id, strategy_instance_id
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'brokerage' AND table_name = 'executions'
  AND column_name IN ('trade_id', 'ib_trade_id', 'ib_related_trade_id', 'strategy_instance_id', 'related_trade_id')
ORDER BY ordinal_position;

-- 1 row only: the frozen table's FK (account_execution_instance_allocation_strategy_instance_id_fkey, goes in R4)
SELECT conrelid::regclass AS on_table, conname FROM pg_constraint WHERE conname ~ 'strategy_instance' ORDER BY 2;

-- The renamed sequences, and the env views' owner and grants (dev: postgres with bifrost=r; stg / prod: bifrost)
SELECT relname FROM pg_class WHERE relkind = 'S' AND relname IN ('trade_trade_id_seq', 'trade_execution_trade_execution_id_seq');
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.relacl
FROM pg_class c WHERE c.relnamespace = 'brokerage'::regnamespace AND c.relkind = 'v' ORDER BY 1;
