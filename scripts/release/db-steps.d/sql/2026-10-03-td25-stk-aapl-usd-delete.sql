-- TD-25: delete the one position-category tag keyed 'STK-AAPL-USD' (2026-05-24). That key format
-- is written by no code today and never matches a position (positions key a stock 'AAPL|STK|||'),
-- so the tag tags nothing. Not reversible except from the export taken in the dry-run step.
-- Refuses unless exactly 1 row goes.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -1 -f - < this file
DO $td25$
DECLARE
  n integer;
BEGIN
  DELETE FROM public.preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'expected 1 STK-AAPL-USD tag, found %; nothing deleted', n;
  END IF;
END $td25$;
