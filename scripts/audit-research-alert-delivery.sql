-- TD-304 bounded read-only preflight. Run as agent_reader, never a writer.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SELECT dagster_event_type, count(*) AS events_24h
FROM ops_dagster.event_logs
WHERE timestamp >= (now() AT TIME ZONE 'UTC') - interval '24h'
  AND dagster_event_type IN ('PIPELINE_FAILURE', 'PIPELINE_SUCCESS')
GROUP BY dagster_event_type;
SELECT count(*) AS failed_error_evaluations_in_success_24h
FROM ops_dagster.event_logs e
JOIN ops_dagster.runs r ON r.run_id = e.run_id
WHERE e.timestamp >= (now() AT TIME ZONE 'UTC') - interval '24h'
  AND e.dagster_event_type = 'ASSET_CHECK_EVALUATION' AND r.status = 'SUCCESS'
  AND e.event::jsonb->'dagster_event'->'event_specific_data'->>'success' = 'false'
  AND e.event::jsonb->'dagster_event'->'event_specific_data'->'severity'->>'__enum__'
      = 'AssetCheckSeverity.ERROR';
SELECT instigator_body::jsonb->'origin'->>'job_name' AS sensor, status
FROM ops_dagster.instigators
WHERE instigator_type = 'SENSOR'
  AND instigator_body::jsonb->'origin'->>'job_name' IN
      ('bifrost_run_failure_alert', 'bifrost_asset_check_alert', 'bifrost_alert_delivery')
ORDER BY 1;
SELECT min(trade_date), max(trade_date), count(*) AS calendar_dates,
       count(*) FILTER (WHERE is_trading_day) AS sessions
FROM dw_stock.dim_trading_calendar
WHERE trade_date BETWEEN (now() AT TIME ZONE 'America/New_York')::date - 16
                     AND (now() AT TIME ZONE 'America/New_York')::date;
COMMIT;
