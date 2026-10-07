-- Read-only. The role can CONNECT to the four databases and cannot CREATE or write.
\set ON_ERROR_STOP on
DO $td85$
DECLARE
  bad text;
BEGIN
  IF to_regrole('role_matrix_reader') IS NULL THEN
    RAISE EXCEPTION 'td85: role_matrix_reader does not exist';
  END IF;
  SELECT string_agg(label, ', ' ORDER BY label) INTO bad
    FROM (
      SELECT 'missing CONNECT ' || d.datname AS label
        FROM pg_database d
       WHERE d.datname IN ('bifrost_dev','bifrost_stg','bifrost_prod','bifrost_golden_source')
         AND NOT has_database_privilege('role_matrix_reader', d.oid, 'CONNECT')
      UNION ALL
      SELECT 'unexpected CREATE ' || n.nspname
        FROM pg_namespace n
       WHERE n.nspname NOT LIKE 'pg\_%'
         AND n.nspname <> 'information_schema'
         AND has_schema_privilege('role_matrix_reader', n.oid, 'CREATE')
    ) s;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'td85 reader verify failed: %', bad;
  END IF;
END
$td85$;
