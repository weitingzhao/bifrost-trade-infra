-- TD-43 / TD-73 rollback: put the three columns back. Needed only if core is rolled back below
-- 0.43.0 after the drop (0.42.0 SELECTs strategy_instance.notes and trade_review.note; below 0.41.0
-- core also reads strategy_plan.filled_at). notes / note were 0 non-null when dropped, so nothing
-- else comes back; filled_at is rebuilt exactly from the linked instance's opened_at.
-- Run as postgres or bifrost: psql -v ON_ERROR_STOP=1 -f - < this file   (it has its own BEGIN / COMMIT)
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.strategy_plan ADD COLUMN IF NOT EXISTS filled_at timestamptz;
ALTER TABLE public.strategy_instance ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE public.trade_review ADD COLUMN IF NOT EXISTS note text;
UPDATE public.strategy_plan p
SET filled_at = i.opened_at
FROM public.strategy_instance i
WHERE i.strategy_instance_id = p.strategy_instance_id
  AND p.status = 'filled'
  AND p.filled_at IS NULL;
COMMIT;
