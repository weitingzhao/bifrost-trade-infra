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
-- Quarantine rather than reopen PUBLIC. Does not drop data or kill sessions.
BEGIN;
SET LOCAL lock_timeout = '5s';
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', :'db', role)
  FROM (VALUES ('agentrt_owner_' || :'env'), ('platform_agentrt_' || :'env'),
               ('agent_reader'), ('role_matrix_reader')) r(role)
\gexec
SELECT :'env' = 'prod' AS is_prod \gset
\if :is_prod
SELECT format('REVOKE CONNECT ON DATABASE %I FROM bifrost', :'db')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE USAGE ON SCHEMAS FROM bifrost', 'agentrt_owner_' || :'env')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE SELECT ON TABLES FROM bifrost', 'agentrt_owner_' || :'env')
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE SELECT ON SEQUENCES FROM bifrost', 'agentrt_owner_' || :'env')
\gexec
SELECT 'REVOKE USAGE ON SCHEMA agentrt FROM bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
SELECT 'REVOKE SELECT ON ALL TABLES IN SCHEMA agentrt FROM bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
SELECT 'REVOKE SELECT ON ALL SEQUENCES IN SCHEMA agentrt FROM bifrost' WHERE to_regnamespace('agentrt') IS NOT NULL
\gexec
\endif
COMMIT;
