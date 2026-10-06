-- Expect three rows, each data_type 'double precision', is_nullable 'YES', column_default NULL.
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'account_nav_daily'
  AND column_name IN ('cushion', 'excess_liquidity', 'maint_margin_req')
ORDER BY column_name;
