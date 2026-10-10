\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SELECT clock_timestamp() AS checked_at, current_user, current_setting('transaction_read_only') AS read_only;
SELECT id, status, created_at, finished_at,
       result->'retention_archive' AS archive_runs,
       result->'option_snapshot_intraday_deleted' AS intraday_deleted,
       result->'option_snapshot_past_window_deleted' AS snapshot_all_deleted,
       result->'option_daily_default_rows_deleted' AS option_daily_deleted,
       result->'short_volume_deleted' AS short_volume_deleted
FROM ops_jobs.job_ingest WHERE kind = 'slot-trim'
ORDER BY created_at DESC LIMIT 6;
-- Fixed acceptance dates: aggregate only; remaining pinned rows must not be lost.
SELECT (s.snapshot_ts AT TIME ZONE 'UTC')::date AS utc_day,
       count(*) AS remaining_intraday,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM research.option_pinned_contract p
           WHERE p.option_ticker = s.option_ticker AND p.pin_until >= CURRENT_DATE
       )) AS currently_pinned
FROM raw_market.option_snapshot s
WHERE s.snapshot_ts >= '2026-09-08 00:00+00'::timestamptz
  AND s.snapshot_ts < '2026-09-10 00:00+00'::timestamptz
  AND (s.snapshot_ts AT TIME ZONE 'America/New_York')::time <> time '16:00'
GROUP BY 1;
SELECT min(bar_date) AS first_option_daily FROM raw_market.option_daily;
SELECT min(period_date) AS first_short_volume FROM raw_market.short_volume;
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'raw_market'
  AND table_name IN ('option_snapshot', 'option_daily', 'short_volume')
ORDER BY table_name, ordinal_position;
SELECT table_name, column_name, ordinal_position
FROM information_schema.key_column_usage
WHERE table_schema = 'raw_market'
  AND table_name IN ('option_snapshot', 'option_daily', 'short_volume')
ORDER BY table_name, ordinal_position;
COMMIT;
