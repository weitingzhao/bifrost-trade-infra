\set ON_ERROR_STOP on
-- Fail closed before using env in an identifier. Run with -v env=dev|stg|prod.
SELECT :'env' IN ('dev', 'stg', 'prod') AS valid_env \gset
\if :valid_env
\else
  \echo 'w31: env must be dev, stg or prod'
  \quit 2
\endif
SELECT set_config('w31.env', :'env', false);
-- Keep roles and owned objects; stop new logins. Existing sessions remain.
BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT format('ALTER ROLE %I NOLOGIN', role)
  FROM (VALUES ('agentrt_owner_' || :'env'), ('platform_agentrt_' || :'env')) r(role)
 WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role)
\gexec
COMMIT;
