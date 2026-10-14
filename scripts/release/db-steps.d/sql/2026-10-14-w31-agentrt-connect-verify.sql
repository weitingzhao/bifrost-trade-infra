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
DO $w31$
DECLARE
  env text := current_setting('w31.env');
  role text;
  other_env text;
BEGIN
  FOREACH role IN ARRAY ARRAY['agentrt_owner_' || env, 'platform_agentrt_' || env,
                             'agent_reader', 'role_matrix_reader', 'bifrost'] LOOP
    IF NOT has_database_privilege(role, current_database(), 'CONNECT') THEN
      RAISE EXCEPTION 'w31: missing CONNECT for %', role;
    END IF;
  END LOOP;
  FOREACH other_env IN ARRAY ARRAY['dev','stg','prod'] LOOP
    IF other_env = env THEN CONTINUE; END IF;
    FOREACH role IN ARRAY ARRAY['agentrt_owner_' || other_env, 'platform_agentrt_' || other_env] LOOP
      IF has_database_privilege(role, current_database(), 'CONNECT') THEN
        RAISE EXCEPTION 'w31: cross-environment CONNECT for %', role;
      END IF;
    END LOOP;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_database d,
             LATERAL aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
             WHERE d.datname = current_database() AND a.grantee = 0 AND a.privilege_type = 'CONNECT') THEN
    RAISE EXCEPTION 'w31: PUBLIC still has CONNECT';
  END IF;
END
$w31$;
