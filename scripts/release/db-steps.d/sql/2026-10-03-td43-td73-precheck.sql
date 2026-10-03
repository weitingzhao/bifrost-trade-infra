-- TD-43 / TD-73: read-only dry-run for dropping strategy_plan.filled_at, strategy_instance.notes
-- and trade_review.note. Run with default_transaction_read_only=on. Changes nothing.
-- present = whether the column still exists (false once dropped); non_null must be 0 before the commit.
SELECT t.table_name, t.column_name,
       EXISTS (SELECT 1 FROM information_schema.columns c
               WHERE c.table_schema = 'public' AND c.table_name = t.table_name
                 AND c.column_name = t.column_name) AS present
FROM (VALUES ('strategy_plan', 'filled_at'), ('strategy_instance', 'notes'), ('trade_review', 'note'))
     AS t(table_name, column_name)
ORDER BY 1;

-- Non-null values: must all be 0 before the commit (it refuses otherwise). A column that is
-- already gone is skipped (psql \if), so the dry-run also reads cleanly after the drop.
SELECT
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
          AND table_name = 'strategy_plan' AND column_name = 'filled_at') AS has_filled_at,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
          AND table_name = 'strategy_instance' AND column_name = 'notes') AS has_notes,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
          AND table_name = 'trade_review' AND column_name = 'note') AS has_note
\gset
\if :has_filled_at
SELECT count(*) AS plans, count(filled_at) AS strategy_plan_filled_at_non_null FROM public.strategy_plan;
\endif
\if :has_notes
SELECT count(*) AS trades, count(notes) AS strategy_instance_notes_non_null FROM public.strategy_instance;
\endif
\if :has_note
SELECT count(*) AS reviews, count(note) AS trade_review_note_non_null FROM public.trade_review;
\endif

-- What a rollback would have to restore for filled_at: filled plans (their filled_at is the
-- instance's opened_at, so it can be rebuilt exactly).
SELECT count(*) AS filled_plans FROM public.strategy_plan WHERE status = 'filled';

-- Anything else that depends on the three columns (views, indexes, constraints): must be 0 rows.
SELECT d.classid::regclass AS kind, d.objid, a.attrelid::regclass AS table_name, a.attname AS column_name
FROM pg_attribute a
JOIN pg_depend d ON d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
WHERE a.attrelid IN (to_regclass('public.strategy_plan'), to_regclass('public.strategy_instance'),
                     to_regclass('public.trade_review'))
  AND (a.attrelid::regclass::text, a.attname) IN
      (('strategy_plan', 'filled_at'), ('strategy_instance', 'notes'), ('trade_review', 'note'))
  AND d.deptype <> 'i';
