-- TD-74 rollback: put settings.flex_default_range_days / flex_init_range_days back, as they were
-- (int4 NOT NULL, defaults 30 / 360) with the exported values. Needed only if something that still reads
-- them comes back (Flex Query plugin < 0.7.0 reads and writes them; core >= 0.39.0 never does).
-- The values come from the export CSV, as psql variables:
--   psql -v ON_ERROR_STOP=1 -v default_days=30 -v init_days=270 -f - < this file
-- (2026-10-04 all three envs held 30 / 270.) It has its own BEGIN / COMMIT. Idempotent.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.settings ADD COLUMN IF NOT EXISTS flex_default_range_days integer NOT NULL DEFAULT 30;
ALTER TABLE public.settings ADD COLUMN IF NOT EXISTS flex_init_range_days integer NOT NULL DEFAULT 360;
UPDATE public.settings
SET flex_default_range_days = :default_days,
    flex_init_range_days = :init_days
WHERE id = 1;
COMMIT;
