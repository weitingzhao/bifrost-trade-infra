-- Wave 14 (core 0.41.0) pre-check, read-only. Every *_violations count must be 0 before the
-- deliver (a non-zero count does not fail db-init: the CHECK stays NOT VALID / the UNIQUE is
-- skipped with a WARNING -- but report it to the Owner instead of shipping that).
-- Read 2026-10-03: 0 / 0 / 0 on DEV / STG / PROD for every row below.
SELECT 'td43_plan_filled_instance_violations' AS check_name, count(*) AS n
  FROM strategy_plan WHERE (status = 'filled') IS DISTINCT FROM (strategy_instance_id IS NOT NULL)
UNION ALL
SELECT 'td43_plan_instance_missing_violations', count(*)
  FROM strategy_plan p WHERE p.strategy_instance_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM strategy_instance i WHERE i.strategy_instance_id = p.strategy_instance_id)
UNION ALL
SELECT 'td56_duplicate_category_name_violations', count(*)
  FROM (SELECT name FROM preference_position_categories GROUP BY name HAVING count(*) > 1) d
UNION ALL
SELECT 'td56_category_id_over_int4_violations', count(*)
  FROM preference_position_category_tags WHERE category_id > 2147483647
UNION ALL
SELECT 'td71_scope_type_violations', count(*)
  FROM strategy_opportunity WHERE NOT (scope_type IS NULL OR scope_type IN ('watchlist_stk', 'explicit_symbols'))
UNION ALL
SELECT 'info_strategy_plan_rows', count(*) FROM strategy_plan
UNION ALL
SELECT 'info_trade_review_rows', count(*) FROM trade_review
UNION ALL
SELECT 'info_watchlist_watchlist_stk_without_symbols', count(*)
  FROM strategy_opportunity WHERE scope_type = 'watchlist_stk' AND jsonb_array_length(symbols_json) = 0
UNION ALL
SELECT 'info_category_named_uncategorized', count(*) FROM preference_position_categories WHERE lower(name) = 'uncategorized';
