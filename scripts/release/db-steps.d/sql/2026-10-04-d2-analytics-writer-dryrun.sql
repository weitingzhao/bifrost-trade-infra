-- D2 (TD-85 follow-up): read-only matrix of what Research's analytics_writer needs on bifrost_golden_source,
-- and whether it holds each need DIRECTLY (own ACL entry, PUBLIC, or ownership) or only through its
-- membership in bifrost. Run with default_transaction_read_only=on. Changes nothing.
-- Before the grants step: some needs are ok_now but not ok_direct (that is the D2 gap).
-- After the grants step: every need is ok_direct, and the last query says ready_to_revoke = true.
-- After the revoke step (verify): ok_now = ok_direct everywhere; the "inherited only" list is empty.
--
-- The needs come from Research's code at origin/main ed144db (0.161.0 / 0.161.0-dagster), read 2026-10-04:
--   * DDL on features / research (schema/ddl.py apply_all_ddl via the research-ddl-apply Job and the
--     canonical_pnl CLI: CREATE INDEX IF NOT EXISTS, ALTER TABLE … ADD COLUMN IF NOT EXISTS, COMMENT ON,
--     CREATE OR REPLACE VIEW) and monthly partitions (Dagster research_ensure_partitions_job,
--     ops_jobs.ensure_month_partitions -> CREATE TABLE … PARTITION OF): Postgres wants ownership even
--     when nothing changes.
--   * DML on features / research / journal / dw_stock / ops_dbt / ops_dagster (engines, dbt, Dagster storage).
--   * SELECT raw_market.* (dbt sources, engines), raw_broker.executions_final (journal_distill,
--     repositories/journal_memory), ops_jobs.watchlist_cache (option_universe entry).
--   * Nothing in bifrost_dev / stg / prod, nothing in ops_feedback, no other raw_broker or ops_jobs object.

-- 1. Membership (the thing D2 removes).
SELECT g.rolname AS role, m.member::regrole AS member, m.grantor::regrole AS grantor,
       m.inherit_option AS inherit, m.set_option AS can_set_role, m.admin_option AS admin
FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
WHERE m.member = 'analytics_writer'::regrole;

-- 2. Relations: per need and schema, how many objects are covered directly vs. right now.
WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid),
rel AS (
  SELECT c.oid, n.nspname, c.relname, c.relkind, c.relowner,
         coalesce(c.relacl, acldefault(CASE WHEN c.relkind = 'S' THEN 's'::"char" ELSE 'r'::"char" END, c.relowner)) AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S') AND n.nspname !~ '^(pg_|information_schema)'
),
direct AS (
  SELECT r.oid, coalesce(array_agg(a.privilege_type) FILTER (WHERE a.grantee IN ((SELECT oid FROM aw), 0)), '{}') AS privs
  FROM rel r LEFT JOIN LATERAL aclexplode(r.acl) a ON true
  GROUP BY r.oid
),
needs AS (
  SELECT 'own' AS need, r.oid, NULL::text AS priv FROM rel r
   WHERE r.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster') AND r.relkind IN ('r', 'p', 'v', 'm')
  UNION ALL
  SELECT 'dml', r.oid, p FROM rel r CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) p
   WHERE r.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster') AND r.relkind IN ('r', 'p')
  UNION ALL
  SELECT 'seq', r.oid, p FROM rel r CROSS JOIN unnest(ARRAY['USAGE', 'SELECT', 'UPDATE']) p
   WHERE r.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster') AND r.relkind = 'S'
  UNION ALL
  SELECT 'read', r.oid, 'SELECT' FROM rel r
   WHERE (r.nspname = 'raw_market' AND r.relkind IN ('r', 'p', 'v', 'm'))
      OR (r.nspname, r.relname) IN (('raw_broker', 'executions_final'), ('ops_jobs', 'watchlist_cache'))
),
judged AS (
  SELECT n.need, r.nspname, r.relname, n.priv,
         CASE WHEN n.need = 'own' THEN r.relowner = (SELECT oid FROM aw)
              ELSE r.relowner = (SELECT oid FROM aw) OR n.priv = ANY (d.privs) END AS ok_direct,
         CASE WHEN n.need = 'own' THEN pg_has_role((SELECT oid FROM aw), r.relowner, 'USAGE')
              WHEN n.need = 'seq' THEN has_sequence_privilege((SELECT oid FROM aw), r.oid, n.priv)
              ELSE has_table_privilege((SELECT oid FROM aw), r.oid, n.priv) END AS ok_now
  FROM needs n JOIN rel r ON r.oid = n.oid JOIN direct d ON d.oid = r.oid
)
SELECT need, nspname AS schema, count(*) AS checks,
       count(*) FILTER (WHERE ok_direct) AS ok_direct,
       count(*) FILTER (WHERE ok_now) AS ok_now,
       left(string_agg(DISTINCT relname, ', ') FILTER (WHERE NOT ok_direct), 160) AS not_direct_sample
FROM judged
GROUP BY 1, 2
ORDER BY 1, 2;

-- 3. Schemas, the database and the partition helper.
WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid),
sch AS (
  SELECT n.oid, n.nspname, n.nspowner, coalesce(n.nspacl, acldefault('n', n.nspowner)) AS acl FROM pg_namespace n
),
need AS (
  SELECT s.*, p FROM sch s CROSS JOIN unnest(ARRAY['USAGE', 'CREATE']) p
   WHERE s.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster')
  UNION ALL
  SELECT s.*, 'USAGE' FROM sch s WHERE s.nspname IN ('raw_market', 'raw_broker', 'ops_jobs', 'public')
)
SELECT 'schema ' || nspname AS object, p AS priv,
       nspowner = (SELECT oid FROM aw)
         OR EXISTS (SELECT 1 FROM aclexplode(acl) a WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = p) AS ok_direct,
       has_schema_privilege((SELECT oid FROM aw), oid, p) AS ok_now
FROM need
UNION ALL
SELECT 'database ' || d.datname, p,
       EXISTS (SELECT 1 FROM aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a
               WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = p),
       has_database_privilege((SELECT oid FROM aw), d.oid, p)
FROM pg_database d CROSS JOIN unnest(ARRAY['CONNECT', 'CREATE', 'TEMPORARY']) p
WHERE d.datname = 'bifrost_golden_source'
UNION ALL
SELECT 'function ' || p.oid::regprocedure, 'EXECUTE',
       EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
               WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = 'EXECUTE'),
       has_function_privilege((SELECT oid FROM aw), p.oid, 'EXECUTE')
FROM pg_proc p WHERE p.oid = 'ops_jobs.ensure_month_partitions(text,text,integer,integer)'::regprocedure
ORDER BY 1, 2;

-- 4. What analytics_writer reaches today ONLY through bifrost and Research does not need: this is what
--    the revoke takes away (table DML; ownership-only rights such as DROP / ALTER follow the same split).
--    Expected before D2: raw_broker (everything but executions_final), raw_market writes, the ops_jobs
--    tables without an analytics_writer grant, ops_feedback, plus the features / research DDL rights the
--    grants step turns into ownership. After the revoke: no rows.
WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid),
rel AS (
  SELECT c.oid, n.nspname, c.relname, c.relowner,
         coalesce(c.relacl, acldefault('r'::"char", c.relowner)) AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p', 'v', 'm') AND n.nspname !~ '^(pg_|information_schema)'
)
SELECT r.nspname AS schema, p AS priv, count(*) AS objects_inherited_only
FROM rel r CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) p
WHERE has_table_privilege((SELECT oid FROM aw), r.oid, p)
  AND r.relowner <> (SELECT oid FROM aw)
  AND NOT EXISTS (SELECT 1 FROM aclexplode(r.acl) a WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = p)
GROUP BY 1, 2
ORDER BY 1, 2;

-- 5. Ownership in features / research (the grants step moves bifrost's to analytics_writer), and the
--    rights bifrost holds there that are not ownership (the grants step gives it S/I/U/D/TRUNCATE back:
--    the market-data plugin still signs in as bifrost and reads features.option_metric_*).
SELECT n.nspname AS schema, pg_get_userbyid(c.relowner) AS owner, c.relkind AS kind,
       count(*) AS objects, count(*) FILTER (WHERE c.relispartition) AS partitions
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('features', 'research') AND c.relkind IN ('r', 'p', 'v', 'm')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

SELECT n.nspname AS schema, pg_get_userbyid(n.nspowner) AS schema_owner, n.nspacl::text AS schema_acl
FROM pg_namespace n WHERE n.nspname IN ('features', 'research') ORDER BY 1;

WITH b AS (SELECT 'bifrost'::regrole::oid AS oid)
SELECT n.nspname AS schema, p AS priv,
       count(*) AS objects,
       count(*) FILTER (WHERE has_table_privilege((SELECT oid FROM b), c.oid, p)) AS bifrost_has
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) p
WHERE n.nspname IN ('features', 'research') AND c.relkind IN ('r', 'p')
GROUP BY 1, 2
ORDER BY 1, 2;

-- 6. Verdict: every need covered directly (ownership included) -> the revoke is safe to run.
WITH aw AS (SELECT 'analytics_writer'::regrole::oid AS oid),
rel AS (
  SELECT c.oid, n.nspname, c.relname, c.relkind, c.relowner,
         coalesce(c.relacl, acldefault('r'::"char", c.relowner)) AS acl
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p', 'v', 'm') AND n.nspname !~ '^(pg_|information_schema)'
),
gaps AS (
  SELECT r.nspname || '.' || r.relname AS obj FROM rel r
   WHERE r.nspname IN ('features', 'research', 'journal', 'dw_stock', 'ops_dbt', 'ops_dagster')
     AND r.relowner <> (SELECT oid FROM aw)
  UNION ALL
  SELECT r.nspname || '.' || r.relname FROM rel r
   WHERE ((r.nspname = 'raw_market') OR (r.nspname, r.relname) IN (('raw_broker', 'executions_final'), ('ops_jobs', 'watchlist_cache')))
     AND r.relowner <> (SELECT oid FROM aw)
     AND NOT EXISTS (SELECT 1 FROM aclexplode(r.acl) a WHERE a.grantee IN ((SELECT oid FROM aw), 0) AND a.privilege_type = 'SELECT')
)
SELECT count(*) = 0 AS ready_to_revoke, count(*) AS gaps, left(string_agg(obj, ', '), 300) AS gap_sample FROM gaps;
