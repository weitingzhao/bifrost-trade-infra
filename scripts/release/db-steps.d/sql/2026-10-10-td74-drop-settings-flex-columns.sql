-- TD-74: drop settings.flex_default_range_days and settings.flex_init_range_days (bifrost_dev / stg / prod).
-- The Flex Query plugin keeps the range in Golden Source ops_jobs.flex_settings (plugin >= 0.7.0); core
-- has not read the columns since 0.39.0, and from the TD-74 core commit its DDL no longer declares them.
-- Export the values first (the .md's export command). One transaction: prints the values it drops,
-- refuses (RAISE, nothing dropped) if anything depends on the columns, then drops. Idempotent.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -f - < this file   (it has its own BEGIN / COMMIT)
BEGIN;
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.settings IN ACCESS EXCLUSIVE MODE;
DO $td74$
DECLARE
  r record;
  n bigint;
BEGIN
  SELECT count(*) INTO n
  FROM pg_attribute a
  JOIN pg_depend d ON d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
  WHERE a.attrelid = 'public.settings'::regclass
    AND a.attname IN ('flex_default_range_days', 'flex_init_range_days')
    AND d.deptype <> 'i'
    AND d.classid <> 'pg_attrdef'::regclass;
  IF n > 0 THEN
    RAISE EXCEPTION 'td74: % object(s) depend on settings.flex_*_range_days; nothing dropped', n;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
             AND table_name = 'settings' AND column_name = 'flex_default_range_days')
     AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                 AND table_name = 'settings' AND column_name = 'flex_init_range_days') THEN
    FOR r IN EXECUTE 'SELECT id, flex_default_range_days, flex_init_range_days FROM public.settings ORDER BY id' LOOP
      RAISE NOTICE 'td74: dropping settings id=% flex_default_range_days=% flex_init_range_days=%',
        r.id, r.flex_default_range_days, r.flex_init_range_days;
    END LOOP;
  ELSE
    RAISE NOTICE 'td74: one or both columns already gone; dropping what is left';
  END IF;
END $td74$;
ALTER TABLE public.settings DROP COLUMN IF EXISTS flex_default_range_days;
ALTER TABLE public.settings DROP COLUMN IF EXISTS flex_init_range_days;
COMMIT;
