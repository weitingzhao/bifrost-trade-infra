\set ON_ERROR_STOP on
-- Fail closed before using env in an identifier. Run with -v env=dev|stg|prod.
SELECT :'env' IN ('dev', 'stg', 'prod') AS valid_env \gset
\if :valid_env
\else
  \echo 'w31: env must be dev, stg or prod'
  \quit 2
\endif
SELECT set_config('w31.env', :'env', false);
SELECT CASE WHEN :'env' = 'prod' THEN 'bifrost_platform' ELSE 'bifrost_platform_' || :'env' END AS db \gset
-- This step must run in the target database for the backup default ACLs.
SELECT current_database() = :'db' AS correct_database \gset
\if :correct_database
\else
  \echo 'w31: connect to the target database'
  \quit 2
\endif
BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'db')
\gexec
-- Revoke stale explicit cross-environment grants, too.
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', :'db', role)
  FROM (SELECT prefix || env AS role FROM unnest(ARRAY['dev','stg','prod']) e(env)
        CROSS JOIN unnest(ARRAY['agentrt_owner_','platform_agentrt_']) p(prefix)
        WHERE env <> :'env') r
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', role)
  FROM (VALUES ('agentrt_owner_' || :'env'), ('platform_agentrt_' || :'env'),
               ('agent_reader'), ('role_matrix_reader'), ('bifrost')) r(role)
\gexec
-- logical-backup signs in as bifrost (README.md / bifrost-postgres-app reference).
-- Install defaults BEFORE migration creates agentrt and its tables/sequences.
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I GRANT USAGE ON SCHEMAS TO bifrost', 'agentrt_owner_' || :'env')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I GRANT SELECT ON TABLES TO bifrost', 'agentrt_owner_' || :'env')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I GRANT SELECT ON SEQUENCES TO bifrost', 'agentrt_owner_' || :'env')
\gexec
-- Safe to rerun after migration: cover already-created objects as well.
SELECT 'GRANT USAGE ON SCHEMA agentrt TO bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
SELECT 'GRANT SELECT ON ALL TABLES IN SCHEMA agentrt TO bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
SELECT 'GRANT SELECT ON ALL SEQUENCES IN SCHEMA agentrt TO bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
COMMIT;
