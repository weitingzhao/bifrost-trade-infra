\set ON_ERROR_STOP on
-- Fail closed before using env in an identifier. Run with -v env=dev|stg|prod.
SELECT :'env' IN ('dev', 'stg', 'prod') AS valid_env \gset
\if :valid_env
\else
  \echo 'w31: env must be dev, stg or prod'
  \quit 2
\endif
SELECT set_config('w31.env', :'env', false);
BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT format('CREATE ROLE %I', role)
  FROM (VALUES ('agentrt_owner_' || :'env'), ('platform_agentrt_' || :'env')) r(role)
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role)
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT %s',
              role, lim)
  FROM (VALUES ('agentrt_owner_' || :'env', 4),
               ('platform_agentrt_' || :'env', CASE WHEN :'env' = 'prod' THEN 10 ELSE 5 END)) r(role, lim)
\gexec
COMMIT;
