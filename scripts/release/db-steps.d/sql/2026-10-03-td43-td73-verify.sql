-- TD-43 / TD-73 verify (read-only): after the commit all three columns are gone (0 rows), and a
-- filled plan still reads filled_at as its instance's opened_at, the way core 0.43.0 reads it.
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (table_name, column_name) IN
      (('strategy_plan', 'filled_at'), ('strategy_instance', 'notes'), ('trade_review', 'note'));

SELECT p.status, count(*) AS plans, count(i.opened_at) AS with_filled_at
FROM public.strategy_plan p
LEFT JOIN public.strategy_instance i ON i.strategy_instance_id = p.strategy_instance_id
GROUP BY p.status
ORDER BY p.status;
