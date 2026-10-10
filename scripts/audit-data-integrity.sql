-- Read-only spot check for the 2026-10-10 audit, not an automatic repair.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';

-- Same seven-day window and latest-row rule as lens coverage, for 10-10.
WITH latest AS (
  SELECT DISTINCT ON (symbol) symbol, iv_rank_1y, iv_percentile_1y
  FROM features.option_metric_iv_percentile_daily
  WHERE trade_date BETWEEN DATE '2026-10-03' AND DATE '2026-10-09'
    AND symbol IN (SELECT symbol FROM research.option_universe)
  ORDER BY symbol, trade_date DESC
)
SELECT count(*) AS stored_readings, count(iv_rank_1y) AS usable_rank,
       count(iv_percentile_1y) AS usable_percentile FROM latest;

SELECT symbol, lookback_days, iv_rank_1y, iv_percentile_1y
FROM features.option_metric_iv_percentile_daily
WHERE trade_date = DATE '2026-10-09' AND lookback_days < 10 ORDER BY symbol;

SELECT bar_date, close, close_unadjusted FROM raw_market.stock_daily
WHERE symbol = 'CTVA' AND bar_date BETWEEN DATE '2026-09-29' AND DATE '2026-10-09'
ORDER BY bar_date;
SELECT trade_date, rv_20d, vrp_20d FROM features.stock_signal_vrp_daily
WHERE symbol = 'CTVA' AND trade_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-09'
ORDER BY trade_date;

SELECT date_trunc('week', trade_date)::date AS week,
       count(DISTINCT (symbol, trade_date)) AS iv_name_days,
       count(DISTINCT (symbol, trade_date)) FILTER (
         WHERE expiry - trade_date BETWEEN 50 AND 100
       ) AS tenor_50_100_name_days
FROM features.option_metric_atm_iv_daily
WHERE trade_date BETWEEN DATE '2026-06-22' AND DATE '2026-10-09'
GROUP BY 1 ORDER BY 1;

-- The fixed interval can expire out of retention; zero later is not a PASS.
WITH failed AS (
  SELECT * FROM ops_jobs.job_ingest
  WHERE kind = 'option_daily' AND status = 'failed'
    AND created_at >= TIMESTAMPTZ '2026-10-09 22:45:00+00'
    AND created_at < TIMESTAMPTZ '2026-10-09 22:46:00+00'
)
SELECT r.status AS newer_status, count(*) AS original_failures,
       count(*) FILTER (WHERE f.result->>'error' LIKE '%HTTP 401%') AS auth_failures,
       max(r.finished_at) AS latest_retry_completion
FROM failed f
LEFT JOIN LATERAL (
  SELECT status, finished_at FROM ops_jobs.job_ingest r
  WHERE r.kind = f.kind AND r.payload_hash = f.payload_hash AND r.id > f.id
  ORDER BY r.id DESC LIMIT 1
) r ON true
GROUP BY r.status;
ROLLBACK;
