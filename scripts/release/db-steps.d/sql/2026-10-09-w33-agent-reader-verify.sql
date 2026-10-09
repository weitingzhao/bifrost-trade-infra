-- Read-only. Confirms the role exists, inherits pg_read_all_data, and cannot CREATE.
\set ON_ERROR_STOP on
DO $w33$
DECLARE
  bad text;
BEGIN
  IF to_regrole('agent_reader') IS NULL THEN
    RAISE EXCEPTION 'w33: agent_reader does not exist';
  END IF;
  SELECT string_agg(label, ', ' ORDER BY label) INTO bad
    FROM (
      SELECT 'not a member of pg_read_all_data' AS label
       WHERE NOT pg_has_role('agent_reader', 'pg_read_all_data', 'member')
      UNION ALL
      SELECT 'superuser' WHERE (SELECT rolsuper FROM pg_roles WHERE rolname = 'agent_reader')
      UNION ALL
      SELECT 'connection limit ' || rolconnlimit::text
        FROM pg_roles
       WHERE rolname = 'agent_reader' AND rolconnlimit <> 8
      UNION ALL
      SELECT 'missing read-only default'
       WHERE NOT EXISTS (
         SELECT 1 FROM pg_roles
          WHERE rolname = 'agent_reader'
            AND 'default_transaction_read_only=on' = ANY (rolconfig)
       )
      UNION ALL
      SELECT 'missing CONNECT ' || d.datname
        FROM pg_database d
       WHERE d.datname IN ('bifrost_dev','bifrost_stg','bifrost_prod','bifrost_golden_source')
         AND NOT has_database_privilege('agent_reader', d.oid, 'CONNECT')
      UNION ALL
      SELECT 'unexpected CREATE ' || n.nspname
        FROM pg_namespace n
       WHERE n.nspname NOT LIKE 'pg\_%'
         AND n.nspname <> 'information_schema'
         AND has_schema_privilege('agent_reader', n.oid, 'CREATE')
    ) s;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'w33 agent_reader verify failed: %', bad;
  END IF;
END
$w33$;
