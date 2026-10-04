-- D6 step 4 of 4 (as postgres, bifrost_golden_source, one transaction). Run only after BOTH plugins were
-- switched (scripts/plugin-db-roles.sh switch market-data / switch flex) and `check` shows no bifrost
-- session from plugin-market-data or plugin-flex-query.
--
--   Bridge  bifrost loses what step 3 lent it on raw_market and ops_jobs: from here bifrost (db-init and
--           CNPG only) has nothing in either schema.
--   M5      data_writer gives back what it never used: every right on raw_broker (10 tables, 3 views,
--           6 sequences, schema USAGE) and the matching default privileges FOR ROLE bifrost; INSERT /
--           UPDATE / DELETE / TRUNCATE / REFERENCES / TRIGGER / MAINTAIN on the four
--           features.option_metric_* parents (SELECT stays, M4); everything on the four flex tables of
--           ops_jobs and their sequence (flex_writer owns them now).
--
-- Refuses while bifrost still has a long-lived session in bifrost_golden_source (a plugin pool that was
-- not switched; db-init's sessions last seconds). Pass -v force=1 to skip that guard.
-- Idempotent. Rollback: sql/2026-10-04-d6-rollback-gs.sql.
\set ON_ERROR_STOP on
SELECT count(*) AS d6_bifrost_pools FROM pg_stat_activity
 WHERE usename = 'bifrost' AND datname = 'bifrost_golden_source' AND backend_start < now() - interval '2 minutes' \gset
\if :{?force}
\else
  SELECT :d6_bifrost_pools = 0 AS d6_no_bifrost_pools \gset
  \if :d6_no_bifrost_pools
  \else
    \echo 'd6: bifrost still has' :d6_bifrost_pools 'long-lived session(s) in bifrost_golden_source: a plugin is not switched (scripts/plugin-db-roles.sh check). Nothing changed.'
    DO $$ BEGIN RAISE EXCEPTION 'd6: bifrost sessions present'; END $$;
  \endif
\endif

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $d6$
BEGIN
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market') <> 'data_writer'::regrole
     OR (SELECT relowner FROM pg_class WHERE oid = 'ops_jobs.job_flex_ingest'::regclass) <> to_regrole('flex_writer') THEN
    RAISE EXCEPTION 'd6: step 3 (ownership) has not run';
  END IF;
END
$d6$;

-- Bridge off
REVOKE ALL ON ALL TABLES IN SCHEMA raw_market, ops_jobs FROM bifrost;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_market, ops_jobs FROM bifrost;
REVOKE ALL ON SCHEMA raw_market, ops_jobs FROM bifrost;

-- M5
REVOKE ALL ON ALL TABLES IN SCHEMA raw_broker FROM data_writer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_broker FROM data_writer;
REVOKE ALL ON SCHEMA raw_broker FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker REVOKE ALL ON TABLES FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker REVOKE ALL ON SEQUENCES FROM data_writer;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
  ON features.option_metric_atm_iv_daily, features.option_metric_iv_percentile_daily,
     features.option_metric_max_pain_daily, features.option_metric_pcr_daily
  FROM data_writer;
REVOKE ALL ON ops_jobs.job_flex_ingest, ops_jobs.flex_ingest_freshness, ops_jobs.flex_worker_heartbeat,
              ops_jobs.flex_settings FROM data_writer;
REVOKE ALL ON SEQUENCE ops_jobs.job_flex_ingest_id_seq FROM data_writer;

COMMIT;
