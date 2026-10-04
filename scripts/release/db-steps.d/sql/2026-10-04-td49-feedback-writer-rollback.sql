-- Rollback of 2026-10-04-td49-feedback-writer-role.sql: drop feedback_writer and every grant it got.
-- Run ONLY after every api-research is back on the analytics connection (api 0.7.3 image with the
-- ANALYTICS_PG_* env and Secret bifrost-analytics-secrets still in place): a 0.7.5 pod signed in as
-- feedback_writer loses its feedback store here.
-- Run as postgres: psql -v ON_ERROR_STOP=1 -f - < this file
BEGIN;
SET LOCAL lock_timeout = '10s';
DO $td49$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_writer') THEN
    ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback REVOKE ALL ON TABLES FROM feedback_writer;
    ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback REVOKE ALL ON SEQUENCES FROM feedback_writer;
    REVOKE ALL ON ALL TABLES IN SCHEMA ops_feedback FROM feedback_writer;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA ops_feedback FROM feedback_writer;
    REVOKE ALL ON SCHEMA ops_feedback FROM feedback_writer;
    REVOKE ALL ON DATABASE bifrost_golden_source FROM feedback_writer;
    DROP ROLE feedback_writer;
  END IF;
END
$td49$;
COMMIT;
