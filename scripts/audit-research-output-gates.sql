\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '20s';
SELECT clock_timestamp() AS checked_at, current_user,
       current_setting('transaction_read_only') AS read_only;
-- Event-log evaluations are the authoritative verdict; an execution status
-- SUCCEEDED is not the check's passed flag. The observation window is bounded.
WITH recent AS (
    SELECT run_id, create_timestamp, status FROM ops_dagster.runs
    WHERE pipeline_name = 'research_trading_day'
    ORDER BY create_timestamp DESC LIMIT 4
), checks AS (
    SELECT e.run_id, e.event::jsonb #> '{dagster_event,event_specific_data}' AS d
    FROM ops_dagster.event_logs e JOIN recent USING (run_id)
    WHERE dagster_event_type = 'ASSET_CHECK_EVALUATION'
)
SELECT r.run_id, r.create_timestamp, r.status,
       d #>> '{asset_key,path}' AS asset, d->>'success' AS passed,
       d #>> '{severity,__enum__}' AS severity,
       d #>> '{metadata,findings,text}' AS findings
FROM checks JOIN recent r USING (run_id)
WHERE d->>'check_name' = 'output_ok'
ORDER BY r.create_timestamp DESC, asset;

WITH recent AS (
    SELECT run_id, create_timestamp FROM ops_dagster.runs
    WHERE pipeline_name = 'research_trading_day'
    ORDER BY create_timestamp DESC LIMIT 4
)
SELECT r.run_id, r.create_timestamp, e.step_key, m->>'label' AS label,
       COALESCE(m #>> '{entry_data,text}', m #>> '{entry_data,value}') AS value
FROM ops_dagster.event_logs e JOIN recent r USING (run_id)
CROSS JOIN LATERAL jsonb_array_elements(
    e.event::jsonb #> '{dagster_event,event_specific_data,materialization,metadata_entries}'
) m
WHERE e.dagster_event_type = 'ASSET_MATERIALIZATION'
  AND e.step_key = 'batch__husbandry_gate'
  AND m->>'label' IN ('gate', 'market_session', 'expected_session',
                      'market_generated_at', 'market_eod', 'overridden')
ORDER BY r.create_timestamp DESC, label;

SELECT status, instigator_body::jsonb #>> '{origin,job_name}' AS sensor
FROM ops_dagster.instigators
WHERE instigator_body::jsonb #>> '{origin,job_name}'
      IN ('bifrost_asset_check_alert', 'bifrost_run_failure_alert');
SELECT tick_body::jsonb->>'job_name' AS sensor, status, count(*) AS ticks,
       max(timestamp) AS latest
FROM ops_dagster.job_ticks
WHERE timestamp > now() - interval '4 days'
  AND tick_body::jsonb->>'job_name'
      IN ('bifrost_asset_check_alert', 'bifrost_run_failure_alert')
GROUP BY 1, 2 ORDER BY 1, 2;
COMMIT;
