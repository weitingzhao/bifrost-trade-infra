-- TD-56: delete the 3 'Option Pool' symbol-order rows (2026-04-23) that match no position category.
-- Not reversible except from the export taken in the dry-run step. Refuses unless exactly 3 rows go.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -1 -f - < this file
DO $td56$
DECLARE
  n integer;
BEGIN
  IF EXISTS (SELECT 1 FROM public.preference_position_categories WHERE name = 'Option Pool') THEN
    RAISE EXCEPTION 'a category named Option Pool exists now: these rows are not orphans, nothing deleted';
  END IF;
  DELETE FROM public.preference_market_streams_symbol_order WHERE category_name = 'Option Pool';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 3 THEN
    RAISE EXCEPTION 'expected 3 Option Pool rows, found %; nothing deleted', n;
  END IF;
END $td56$;
