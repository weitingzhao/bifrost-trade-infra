-- TD-74 verify (read-only): after the commit both columns are gone (first query: 0 rows), the single
-- settings row is still there, and its other columns are unchanged in shape.
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'settings'
  AND column_name IN ('flex_default_range_days', 'flex_init_range_days');

SELECT count(*) AS settings_rows FROM public.settings;

SELECT string_agg(column_name, ', ' ORDER BY ordinal_position) AS settings_columns
FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'settings';
