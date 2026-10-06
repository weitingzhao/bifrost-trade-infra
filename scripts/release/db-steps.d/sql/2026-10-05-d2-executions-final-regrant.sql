-- TD-85 D2 follow-up (as postgres, bifrost_golden_source): put back analytics_writer's SELECT on
-- raw_broker.executions_final. D2 step 1a granted it on 2026-10-04; every db-init since rebuilds the three
-- raw_broker views (core brokerage_ddl: DROP VIEW ... CASCADE + CREATE) and re-grants only the roles core
-- knows, so the grant is gone and Research's memory distill (Dagster research_memory_distill_job, 23:55 UTC
-- weekdays) failed on 2026-10-05 with "permission denied for view executions_final". Idempotent.
-- Until core keeps view grants across the rebuild, re-run this after every Trade release's db-init.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
GRANT SELECT ON raw_broker.executions_final TO analytics_writer;
COMMIT;
SELECT has_table_privilege('analytics_writer', 'raw_broker.executions_final', 'SELECT') AS analytics_writer_select;
