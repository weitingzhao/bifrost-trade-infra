-- Wave 14 (core 0.41.0) rollback: the schema as it was before (core <= 0.40.x). Reversible, no data
-- moves. Only after core is rolled back too: core 0.41.0's _ensure_tables would re-apply Wave 14.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -1 -f - < this file
ALTER TABLE public.strategy_plan
  DROP CONSTRAINT IF EXISTS strategy_plan_filled_instance_ck,
  DROP CONSTRAINT strategy_plan_strategy_instance_id_fkey,
  ADD CONSTRAINT strategy_plan_strategy_instance_id_fkey FOREIGN KEY (strategy_instance_id)
    REFERENCES public.strategy_instance(strategy_instance_id) ON DELETE SET NULL;
ALTER TABLE public.trade_review
  DROP CONSTRAINT trade_review_strategy_instance_id_fkey,
  ADD CONSTRAINT trade_review_strategy_instance_id_fkey FOREIGN KEY (strategy_instance_id)
    REFERENCES public.strategy_instance(strategy_instance_id) ON DELETE CASCADE;
ALTER TABLE public.strategy_opportunity DROP CONSTRAINT IF EXISTS strategy_opportunity_scope_type_ck;
ALTER TABLE public.preference_position_categories DROP CONSTRAINT IF EXISTS preference_position_categories_name_uq;
-- Every category id is <= 6 on every env (read 2026-10-03), so int4 holds them.
ALTER TABLE public.preference_position_category_tags ALTER COLUMN category_id TYPE integer;
ALTER TABLE public.watchlist ALTER COLUMN category_id TYPE integer;
