-- TD-43 (option B step 3/4) / TD-73 (option A): drop strategy_plan.filled_at, strategy_instance.notes
-- and trade_review.note. Owner-approved 2026-10-03. Run only once core >= 0.43.0 is live in the env
-- (it never names these columns; core 0.42.0 still SELECTs notes / note and would fail).
-- One transaction: locks the three tables, refuses (RAISE, nothing dropped) while any of the three
-- holds a non-null value, then drops. Idempotent: a column already gone is skipped.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -f - < this file   (it has its own BEGIN / COMMIT)
BEGIN;
SET LOCAL lock_timeout = '5s';
LOCK TABLE public.strategy_plan, public.strategy_instance, public.trade_review IN ACCESS EXCLUSIVE MODE;
DO $td73$
DECLARE
  c record;
  n bigint;
BEGIN
  FOR c IN
    SELECT * FROM (VALUES ('strategy_plan', 'filled_at'), ('strategy_instance', 'notes'), ('trade_review', 'note'))
      AS v(t, col)
  LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = c.t AND column_name = c.col) THEN
      EXECUTE format('SELECT count(*) FROM public.%I WHERE %I IS NOT NULL', c.t, c.col) INTO n;
      IF n > 0 THEN
        RAISE EXCEPTION 'td43/td73: %.% holds % non-null value(s); nothing dropped', c.t, c.col, n;
      END IF;
    END IF;
  END LOOP;
END $td73$;
ALTER TABLE public.strategy_plan DROP COLUMN IF EXISTS filled_at;
ALTER TABLE public.strategy_instance DROP COLUMN IF EXISTS notes;
ALTER TABLE public.trade_review DROP COLUMN IF EXISTS note;
COMMIT;
