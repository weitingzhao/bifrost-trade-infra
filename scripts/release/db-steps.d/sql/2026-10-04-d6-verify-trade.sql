-- D6 verify, Trade databases (read-only; run in each of bifrost_dev, bifrost_stg, bifrost_prod with
-- default_transaction_read_only=on). flex_writer: read-only on the one database flex-query reads
-- (bifrost_dev); data_writer: nothing in any Trade database. CONNECT / CREATE that come from PUBLIC are
-- expected until D4 (2026-10-04-td85-public-revoke) takes them away.

SELECT current_database() AS db, check_name, actual, expected, actual = expected AS ok FROM (VALUES
  ('flex_writer CONNECT', (to_regrole('flex_writer') IS NOT NULL AND has_database_privilege('flex_writer', current_database(), 'CONNECT'))::text,
     CASE WHEN current_database() = 'bifrost_dev' THEN 'true'
          ELSE (to_regrole('flex_writer') IS NOT NULL AND EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
                WHERE d.datname = current_database() AND a.grantee = 0 AND a.privilege_type = 'CONNECT'))::text END),
  ('flex_writer SELECT public.settings', coalesce(to_regrole('flex_writer') IS NOT NULL AND has_table_privilege('flex_writer', to_regclass('public.settings'), 'SELECT'), false)::text,
     CASE WHEN current_database() = 'bifrost_dev' THEN 'true' ELSE 'false' END),
  ('flex_writer SELECT brokerage.executions', coalesce(to_regrole('flex_writer') IS NOT NULL AND has_table_privilege('flex_writer', to_regclass('brokerage.executions'), 'SELECT'), false)::text,
     CASE WHEN current_database() = 'bifrost_dev' THEN 'true' ELSE 'false' END),
  ('flex_writer SELECT brokerage.settings_flex', coalesce(to_regrole('flex_writer') IS NOT NULL AND has_table_privilege('flex_writer', to_regclass('brokerage.settings_flex'), 'SELECT'), false)::text,
     CASE WHEN current_database() = 'bifrost_dev' THEN 'true' ELSE 'false' END),
  ('flex_writer user mapping -> brokerage_reader',
     coalesce((SELECT (SELECT option_value FROM pg_options_to_table(umoptions) WHERE option_name = 'user')
               FROM pg_user_mappings WHERE srvname = 'golden_source_server' AND usename = 'flex_writer'), 'none'),
     CASE WHEN current_database() = 'bifrost_dev' THEN 'brokerage_reader' ELSE 'none' END),
  ('flex_writer INSERT public.settings', coalesce(to_regrole('flex_writer') IS NOT NULL AND has_table_privilege('flex_writer', to_regclass('public.settings'), 'INSERT'), false)::text, 'false'),
  ('flex_writer tables with any right',
     (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a WHERE a.grantee = to_regrole('flex_writer'))::text,
     CASE WHEN current_database() = 'bifrost_dev' THEN '3' ELSE '0' END),
  ('flex_writer CREATE in schema public', (to_regrole('flex_writer') IS NOT NULL AND has_schema_privilege('flex_writer', 'public', 'CREATE'))::text,
     (to_regrole('flex_writer') IS NOT NULL AND EXISTS (SELECT 1 FROM pg_namespace s, aclexplode(s.nspacl) a
        WHERE s.nspname = 'public' AND a.grantee = 0 AND a.privilege_type = 'CREATE'))::text),
  ('data_writer tables with any right',
     (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a WHERE a.grantee = 'data_writer'::regrole)::text, '0')
) AS t(check_name, actual, expected)
ORDER BY ok, check_name;
