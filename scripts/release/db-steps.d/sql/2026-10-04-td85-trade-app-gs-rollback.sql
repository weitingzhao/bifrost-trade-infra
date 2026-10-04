-- Rollback of 2026-10-04-td85-trade-app-gs.sql (and of the optional ops_feedback file): the Golden
-- Source grants, then the three roles. Last of the rollbacks: every env must already be back on
-- bifrost (scripts/trade-app-role.sh rollback <env>) and ...-trade-app-trade-rollback.sql must have
-- run in bifrost_dev, bifrost_stg and bifrost_prod -- DROP ROLE refuses while any database still
-- holds a grant or user mapping for the role, and this file refuses while a session uses one.
--   psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < this file
\set ON_ERROR_STOP on

SELECT current_database() = 'bifrost_golden_source' AS td85_right_db,
       (SELECT count(*) FROM pg_stat_activity WHERE usename LIKE 'trade\_app\_%') AS td85_sessions \gset
\if :td85_right_db
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: run this file in bifrost_golden_source'; END $$;
\endif
SELECT :td85_sessions = 0 AS td85_idle \gset
\if :td85_idle
\else
  \echo 'td85:' :td85_sessions 'sessions still sign in as trade_app_*: run scripts/trade-app-role.sh rollback <env> first'
  DO $$ BEGIN RAISE EXCEPTION 'td85: trade_app sessions present'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA %I REVOKE ALL ON %s FROM %I', s, k, r)
  FROM unnest(ARRAY['trade_app_dev', 'trade_app_stg', 'trade_app_prod']) r,
       unnest(ARRAY['raw_broker', 'ops_feedback']) s,
       unnest(ARRAY['TABLES', 'SEQUENCES']) k
 WHERE to_regrole(r) IS NOT NULL AND to_regnamespace(s) IS NOT NULL
\gexec
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', s, r) || ';' ||
       format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I', s, r) || ';' ||
       format('REVOKE ALL ON SCHEMA %I FROM %I', s, r)
  FROM unnest(ARRAY['trade_app_dev', 'trade_app_stg', 'trade_app_prod']) r,
       unnest(ARRAY['raw_broker', 'ops_feedback']) s
 WHERE to_regrole(r) IS NOT NULL AND to_regnamespace(s) IS NOT NULL
\gexec
SELECT format('REVOKE ALL ON DATABASE bifrost_golden_source FROM %I', r) || ';' || format('DROP ROLE %I', r)
  FROM unnest(ARRAY['trade_app_dev', 'trade_app_stg', 'trade_app_prod']) r
 WHERE to_regrole(r) IS NOT NULL
\gexec
COMMIT;

SELECT count(*) AS trade_app_roles_left FROM pg_roles WHERE rolname LIKE 'trade\_app\_%';
