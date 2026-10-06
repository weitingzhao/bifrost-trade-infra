-- TD-85 D6 follow-up, read-only: what data_writer holds in raw_broker. Before the revoke: usage t, about
-- 77 object privileges, 6 default-privilege entries (read 2026-10-06). After: f, 0, 0.
SELECT has_schema_privilege('data_writer', 'raw_broker', 'USAGE') AS usage,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         WHERE n.nspname = 'raw_broker' AND a.grantee = 'data_writer'::regrole) AS object_privileges,
       (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace,
               aclexplode(d.defaclacl) a
         WHERE n.nspname = 'raw_broker' AND a.grantee = 'data_writer'::regrole) AS default_privileges,
       (SELECT count(*) FROM pg_stat_activity WHERE usename = 'data_writer') AS data_writer_sessions;
