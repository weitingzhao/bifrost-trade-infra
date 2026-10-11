-- Run only with agent_reader. No vendor requests, alerts, backfill or DDL.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SELECT current_user, current_setting('transaction_read_only') AS read_only, now() AS checked_at;
WITH days AS (
    SELECT trade_date FROM dw_stock.dim_trading_calendar
    WHERE is_trading_day AND trade_date <= (now() AT TIME ZONE 'America/New_York')::date
    ORDER BY trade_date DESC LIMIT 5
)
SELECT d.trade_date,
    (SELECT count(DISTINCT symbol) FROM raw_market.stock_daily s WHERE s.bar_date=d.trade_date) AS stock_symbols,
    (SELECT count(DISTINCT underlying) FROM raw_market.option_daily o WHERE o.bar_date=d.trade_date AND o.close>0) AS priced_option_symbols,
    (SELECT count(DISTINCT symbol) FROM features.option_metric_atm_iv_daily a WHERE a.trade_date=d.trade_date AND atm_iv>0 AND atm_iv<10) AS valid_atm_symbols,
    (SELECT count(DISTINCT symbol) FROM features.option_metric_atm_iv_daily a WHERE a.trade_date=d.trade_date AND expiry-trade_date>=180 AND atm_iv>0 AND atm_iv<10) AS upper_180_symbols
FROM days d ORDER BY d.trade_date;
SELECT kind,status,count(*) AS jobs,max(finished_at) AS last_finished
FROM ops_jobs.job_ingest WHERE created_at >= now()-interval '3 days'
GROUP BY kind,status ORDER BY kind,status;
SELECT dimension,last_run_at,rows_written,status FROM ops_jobs.ingest_freshness ORDER BY dimension;
ROLLBACK;
