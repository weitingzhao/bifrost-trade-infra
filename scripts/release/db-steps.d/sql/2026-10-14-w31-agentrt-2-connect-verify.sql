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
  owner_oid oid;
  backup_oid oid;
  object_type "char";
  wanted_privilege text;
BEGIN
  FOREACH role IN ARRAY ARRAY['agentrt_owner_' || env, 'platform_agentrt_' || env,
                             'agent_reader', 'role_matrix_reader'] LOOP
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
  IF has_database_privilege('bifrost', current_database(), 'CONNECT') <> (env = 'prod') THEN
    RAISE EXCEPTION 'w31: bifrost CONNECT must be present only in PROD';
  END IF;
  SELECT oid INTO STRICT owner_oid FROM pg_roles WHERE rolname = 'agentrt_owner_' || env;
  SELECT oid INTO STRICT backup_oid FROM pg_roles WHERE rolname = 'bifrost';
  -- Defaults are global: agentrt does not exist before migration. They apply to
  -- the owner's future agentrt schema, tables and sequences, including reruns.
  IF env = 'prod' THEN
    FOREACH object_type IN ARRAY ARRAY['n'::"char", 'r'::"char", 'S'::"char"] LOOP
      wanted_privilege := CASE WHEN object_type = 'n' THEN 'USAGE' ELSE 'SELECT' END;
      IF NOT EXISTS (SELECT 1 FROM pg_default_acl d, LATERAL aclexplode(d.defaclacl) a
                     WHERE d.defaclrole = owner_oid AND d.defaclnamespace = 0
                       AND d.defaclobjtype = object_type AND a.grantee = backup_oid
                       AND a.privilege_type = wanted_privilege AND NOT a.is_grantable) THEN
        RAISE EXCEPTION 'w31: missing backup default privilege % on %', wanted_privilege, object_type;
      END IF;
    END LOOP;
  END IF;
  -- Owner's own defaults are intrinsic. Every other grantee (including PUBLIC)
  -- is forbidden, apart from PROD's read-only backup identity.
  IF EXISTS (SELECT 1 FROM pg_default_acl d, LATERAL aclexplode(d.defaclacl) a
             WHERE d.defaclrole = owner_oid AND a.grantee <> owner_oid
               AND NOT (env = 'prod' AND a.grantee = backup_oid AND NOT a.is_grantable
                        AND (d.defaclnamespace = 0 OR d.defaclnamespace = coalesce(to_regnamespace('agentrt')::oid, 0::oid))
                        AND ((d.defaclobjtype IN ('r', 'S') AND a.privilege_type = 'SELECT')
                             OR (d.defaclobjtype = 'n' AND a.privilege_type = 'USAGE')))) THEN
    RAISE EXCEPTION 'w31: unexpected owner default privilege (grantee, scope, privilege or grant option)';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_database d,
             LATERAL aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
             WHERE d.datname = current_database() AND a.grantee = 0 AND a.privilege_type = 'CONNECT') THEN
    RAISE EXCEPTION 'w31: PUBLIC still has CONNECT';
  END IF;
END
$w31$;
