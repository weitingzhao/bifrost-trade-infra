-- naming R4 reverse (objects), bifrost_prod, core 0.47.0 (commit)
BEGIN;

SET LOCAL lock_timeout = '5s';

SET LOCAL ROLE bifrost;

DO $r4$ BEGIN
  IF current_database() <> 'bifrost_prod' THEN
    RAISE EXCEPTION 'R4 reverse: connected to %, but this SQL is for bifrost_prod', current_database();
  END IF;
END $r4$;

DO $r4$ BEGIN
  IF to_regclass('public.trade') IS NULL OR to_regclass('public.trade_execution') IS NULL
     OR to_regclass('brokerage.trade_fill_splits') IS NULL THEN
    RAISE EXCEPTION 'R4 reverse: trade / trade_execution / brokerage.trade_fill_splits missing; nothing is created';
  END IF;
END $r4$;

DROP VIEW IF EXISTS public.strategy_instance_execution;

DROP VIEW IF EXISTS public.strategy_instance;

CREATE VIEW public.strategy_instance AS
  SELECT trade_id AS strategy_instance_id, strategy_opportunity_id, account_id, opened_at,
         label, created_at, updated_at
  FROM public.trade;

CREATE VIEW public.strategy_instance_execution AS
  SELECT trade_execution_id AS strategy_instance_execution_id, account_id, exec_id,
         trade_id AS strategy_instance_id, split_quantity AS allocated_quantity, created_at, updated_at
  FROM public.trade_execution;

DROP VIEW IF EXISTS brokerage.instance_allocations;

CREATE VIEW brokerage.instance_allocations AS
  SELECT account_id, account_executions_id, trade_id AS strategy_instance_id,
         quantity AS allocated_quantity, exec_id
  FROM brokerage.trade_fill_splits;

CREATE TABLE IF NOT EXISTS public.account_execution_instance_allocation (
    account_execution_instance_allocation_id bigserial PRIMARY KEY,
    account_id text NOT NULL,
    account_executions_id bigint NOT NULL,
    strategy_instance_id bigint NOT NULL REFERENCES public.trade(trade_id) ON DELETE RESTRICT,
    allocated_quantity double precision NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_executions_id, strategy_instance_id)
);

CREATE INDEX IF NOT EXISTS account_exec_inst_alloc_account_exec_id ON public.account_execution_instance_allocation (account_id, account_executions_id);

CREATE INDEX IF NOT EXISTS account_exec_inst_alloc_strategy_instance_id ON public.account_execution_instance_allocation (strategy_instance_id);

SELECT o AS restored, to_regclass(o) IS NOT NULL AS present FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation']) o;

COMMIT;
