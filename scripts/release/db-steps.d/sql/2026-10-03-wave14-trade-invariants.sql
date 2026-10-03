-- core 0.41.0 Wave 14 (TD-43 / TD-56 / TD-71): wave14_migrations.wave14_statements(), verbatim.
-- db-init (_ensure_tables) runs exactly this on every deliver; running it by hand first is the same,
-- and running it twice changes nothing. Generated from bifrost-trade-core 0.41.0; do not edit by hand.
-- Run as postgres or bifrost, in one transaction: psql -v ON_ERROR_STOP=1 -1 -f - < this file

DO $w14$
BEGIN
  IF to_regclass('public.strategy_plan') IS NOT NULL
     AND EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'public.strategy_plan'::regclass AND conname = 'strategy_plan_strategy_instance_id_fkey'
                   AND contype = 'f' AND confdeltype <> 'r') THEN
    ALTER TABLE public.strategy_plan
      DROP CONSTRAINT strategy_plan_strategy_instance_id_fkey,
      ADD CONSTRAINT strategy_plan_strategy_instance_id_fkey FOREIGN KEY (strategy_instance_id)
        REFERENCES public.strategy_instance(strategy_instance_id) ON DELETE RESTRICT;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF to_regclass('public.trade_review') IS NOT NULL
     AND EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'public.trade_review'::regclass AND conname = 'trade_review_strategy_instance_id_fkey'
                   AND contype = 'f' AND confdeltype <> 'r') THEN
    ALTER TABLE public.trade_review
      DROP CONSTRAINT trade_review_strategy_instance_id_fkey,
      ADD CONSTRAINT trade_review_strategy_instance_id_fkey FOREIGN KEY (strategy_instance_id)
        REFERENCES public.strategy_instance(strategy_instance_id) ON DELETE RESTRICT;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF to_regclass('public.strategy_plan') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint
                     WHERE conrelid = 'public.strategy_plan'::regclass AND conname = 'strategy_plan_filled_instance_ck') THEN
    ALTER TABLE public.strategy_plan ADD CONSTRAINT strategy_plan_filled_instance_ck CHECK ((status = 'filled') = (strategy_instance_id IS NOT NULL)) NOT VALID;
  END IF;
  IF to_regclass('public.strategy_plan') IS NOT NULL
     AND EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'public.strategy_plan'::regclass AND conname = 'strategy_plan_filled_instance_ck'
                   AND NOT convalidated) THEN
    BEGIN
      ALTER TABLE public.strategy_plan VALIDATE CONSTRAINT strategy_plan_filled_instance_ck;
    EXCEPTION WHEN check_violation THEN
      RAISE WARNING 'strategy_plan_filled_instance_ck left NOT VALID: rows of strategy_plan break it (new writes are checked)';
    END;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF to_regclass('public.strategy_opportunity') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint
                     WHERE conrelid = 'public.strategy_opportunity'::regclass AND conname = 'strategy_opportunity_scope_type_ck') THEN
    ALTER TABLE public.strategy_opportunity ADD CONSTRAINT strategy_opportunity_scope_type_ck CHECK (scope_type IS NULL OR scope_type IN ('watchlist_stk', 'explicit_symbols')) NOT VALID;
  END IF;
  IF to_regclass('public.strategy_opportunity') IS NOT NULL
     AND EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'public.strategy_opportunity'::regclass AND conname = 'strategy_opportunity_scope_type_ck'
                   AND NOT convalidated) THEN
    BEGIN
      ALTER TABLE public.strategy_opportunity VALIDATE CONSTRAINT strategy_opportunity_scope_type_ck;
    EXCEPTION WHEN check_violation THEN
      RAISE WARNING 'strategy_opportunity_scope_type_ck left NOT VALID: rows of strategy_opportunity break it (new writes are checked)';
    END;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'preference_position_category_tags'
               AND column_name = 'category_id' AND data_type = 'integer') THEN
    ALTER TABLE public.preference_position_category_tags ALTER COLUMN category_id TYPE bigint;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'watchlist'
               AND column_name = 'category_id' AND data_type = 'integer') THEN
    ALTER TABLE public.watchlist ALTER COLUMN category_id TYPE bigint;
  END IF;
END $w14$;

DO $w14$
BEGIN
  IF to_regclass('public.preference_position_categories') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint
                     WHERE conrelid = 'public.preference_position_categories'::regclass
                       AND conname = 'preference_position_categories_name_uq') THEN
    BEGIN
      ALTER TABLE public.preference_position_categories
        ADD CONSTRAINT preference_position_categories_name_uq UNIQUE (name);
    EXCEPTION WHEN unique_violation THEN
      RAISE WARNING 'preference_position_categories_name_uq not added: two position categories share a name';
    END;
  END IF;
END $w14$;
