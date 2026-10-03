-- Wave 14 (core 0.41.0) verify, read-only: expected after db-init (or the by-hand apply).
--   strategy_plan_strategy_instance_id_fkey / trade_review_strategy_instance_id_fkey: confdeltype r
--   strategy_plan_filled_instance_ck / strategy_opportunity_scope_type_ck / preference_position_categories_name_uq: validated t
--   preference_position_category_tags.category_id / watchlist.category_id: bigint
SELECT conname, contype, confdeltype, convalidated
  FROM pg_constraint
 WHERE conname IN ('strategy_plan_strategy_instance_id_fkey', 'trade_review_strategy_instance_id_fkey',
                   'strategy_plan_filled_instance_ck', 'strategy_opportunity_scope_type_ck',
                   'preference_position_categories_name_uq')
 ORDER BY conname;
SELECT table_name, column_name, data_type
  FROM information_schema.columns
 WHERE table_schema = 'public' AND column_name = 'category_id'
   AND table_name IN ('preference_position_category_tags', 'watchlist')
 ORDER BY table_name;
