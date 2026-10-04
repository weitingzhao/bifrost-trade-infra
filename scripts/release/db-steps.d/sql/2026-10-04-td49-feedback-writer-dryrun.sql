-- TD-49 D4 / TD-77 E5: read-only view of who can do what on ops_feedback (bifrost_golden_source).
-- Run with default_transaction_read_only=on. Changes nothing. Also the verify after the commit,
-- and after the later revoke step. Never prints a password: only whether one is set.

-- 1. The roles involved. feedback_writer is absent before the commit; has_password is false until
--    `scripts/feedback-writer-secret.sh password` has run.
SELECT r.rolname, r.rolcanlogin AS login, r.rolsuper AS super, r.rolinherit AS inherit,
       r.rolcreaterole AS createrole, r.rolcreatedb AS createdb,
       (a.rolpassword IS NOT NULL) AS has_password,
       coalesce(a.rolpassword LIKE 'SCRAM-SHA-256$%', false) AS scram,
       ARRAY(SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
             WHERE m.member = r.oid ORDER BY 1) AS member_of
FROM pg_roles r JOIN pg_authid a ON a.oid = r.oid
WHERE r.rolname IN ('feedback_writer', 'analytics_writer', 'analytics_reader', 'bifrost')
ORDER BY 1;

-- 2. ops_feedback: schema and objects, owner and ACL (relacl NULL = owner only).
SELECT 'schema' AS kind, n.nspname AS object, pg_get_userbyid(n.nspowner) AS owner, n.nspacl::text AS acl
FROM pg_namespace n WHERE n.nspname = 'ops_feedback'
UNION ALL
SELECT CASE c.relkind WHEN 'r' THEN 'table' WHEN 'S' THEN 'sequence' WHEN 'i' THEN 'index' END,
       c.relname, pg_get_userbyid(c.relowner), c.relacl::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'ops_feedback'
ORDER BY 1, 2;

-- 3. Default privileges on ops_feedback (the commit adds two rows for role bifrost).
SELECT pg_get_userbyid(d.defaclrole) AS for_role, d.defaclobjtype AS objtype, d.defaclacl::text AS acl
FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace
WHERE n.nspname = 'ops_feedback'
ORDER BY 1, 2;

-- 4. Effective privileges (inheritance included) of each role on ops_feedback and on a sample of
--    what feedback_writer must NOT reach. Rows only for roles that exist.
--    Expected after the commit, for feedback_writer: ops_feedback tables sel/ins/upd true and del
--    FALSE (no DELETE, Owner 2026-10-04), no CREATE on the schema; every other object all false.
WITH roles AS (
  SELECT oid, rolname FROM pg_roles
  WHERE rolname IN ('feedback_writer', 'analytics_writer', 'analytics_reader', 'bifrost')
), objs AS (
  SELECT c.oid, n.nspname || '.' || c.relname AS obj
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p')
    AND (n.nspname = 'ops_feedback'
         OR (n.nspname, c.relname) IN (('raw_broker', 'account'), ('journal', 'note'),
                                       ('dw_stock', 'mart_sepa_screener_wide'),
                                       ('features', 'stock_signal_momentum_daily')))
)
SELECT r.rolname, o.obj,
       has_table_privilege(r.oid, o.oid, 'SELECT') AS sel,
       has_table_privilege(r.oid, o.oid, 'INSERT') AS ins,
       has_table_privilege(r.oid, o.oid, 'UPDATE') AS upd,
       has_table_privilege(r.oid, o.oid, 'DELETE') AS del
FROM roles r CROSS JOIN objs o
ORDER BY 1, 2;

SELECT r.rolname, n.nspname AS schema,
       has_schema_privilege(r.oid, n.oid, 'USAGE') AS usage,
       has_schema_privilege(r.oid, n.oid, 'CREATE') AS create
FROM pg_roles r CROSS JOIN pg_namespace n
WHERE r.rolname IN ('feedback_writer', 'analytics_writer', 'bifrost')
  AND n.nspname IN ('ops_feedback', 'public', 'raw_broker', 'journal', 'dw_stock', 'features')
ORDER BY 1, 2;

SELECT r.rolname, has_database_privilege(r.oid, 'bifrost_golden_source', 'CONNECT') AS connect_gs,
       has_database_privilege(r.oid, 'bifrost_golden_source', 'CREATE') AS create_in_gs
FROM pg_roles r WHERE r.rolname IN ('feedback_writer', 'analytics_writer', 'bifrost') ORDER BY 1;

-- 5. Who is connected to Golden Source as which role, by application_name (api 0.7.5 sets
--    trade-api-feedback). After the cutover: feedback_writer rows appear, and no analytics_writer
--    session comes from a bifrost-dev/stg/prod pod (map client_addr with `kubectl get pods -A -o wide`).
SELECT usename, application_name, client_addr, count(*) AS sessions
FROM pg_stat_activity WHERE datname = 'bifrost_golden_source'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
