-- TD-85 dry-run (read-only): the state every TD-85 step starts from, in the database it runs in.
-- Works in bifrost_dev / bifrost_stg / bifrost_prod and bifrost_golden_source:
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < this file
-- Expected (read-only 2026-10-04): Trade databases -- public 19 tables / 14 sequences / 3 views owned
-- by bifrost; brokerage 10 foreign tables + 6 views, market 3 + 1, owner bifrost (STG / PROD) or
-- postgres (DEV, until the D8 step); FDW mappings bifrost -> brokerage_reader, postgres ->
-- brokerage_writer. Golden Source -- raw_broker 10 tables + 3 views + 6 sequences, ops_feedback 2 + 2,
-- all owned by bifrost. No trade_app_* role before the roles step.
\set ON_ERROR_STOP on

SELECT current_database() AS db, pg_get_userbyid(datdba) AS owner, coalesce(datacl::text, '(default: PUBLIC connect + temp)') AS acl
  FROM pg_database WHERE datname = current_database();

-- Roles TD-85 creates (none before the roles step) and the role-level settings they copy.
SELECT r.rolname, r.rolcanlogin AS login, r.rolinherit AS inherit,
       (SELECT array_to_string(setconfig, ', ') FROM pg_db_role_setting WHERE setrole = r.oid AND setdatabase = 0) AS settings
  FROM pg_roles r WHERE r.rolname IN ('bifrost', 'trade_app_dev', 'trade_app_stg', 'trade_app_prod') ORDER BY 1;

-- Schemas (owner, ACL).
SELECT nspname, pg_get_userbyid(nspowner) AS owner, coalesce(nspacl::text, '') AS acl
  FROM pg_namespace WHERE nspname NOT LIKE 'pg\_%' AND nspname <> 'information_schema' ORDER BY 1;

-- Objects the steps grant on (count by schema / kind / owner).
SELECT n.nspname, c.relkind::text AS kind, pg_get_userbyid(c.relowner) AS owner, count(*)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('public', 'brokerage', 'market', 'raw_broker', 'ops_feedback')
   AND c.relkind IN ('r', 'p', 'v', 'f', 'S') AND NOT c.relispartition
 GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- D8 (DEV): the FDW objects one by one with their owner.
SELECT n.nspname, c.relname, c.relkind::text AS kind, pg_get_userbyid(c.relowner) AS owner
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('brokerage', 'market') AND c.relkind IN ('f', 'v')
 ORDER BY 1, 3, 2;

-- FDW user mappings: remote user only (the password option is never selected).
SELECT srvname, usename,
       (SELECT substr(o, 6) FROM unnest(umoptions) o WHERE o LIKE 'user=%') AS remote_user,
       EXISTS (SELECT 1 FROM unnest(umoptions) o WHERE o LIKE 'password=%') AS has_password
  FROM pg_user_mappings ORDER BY 1, 2;

-- Default privileges.
SELECT pg_get_userbyid(d.defaclrole) AS for_role, coalesce(n.nspname, '*') AS nspname,
       d.defaclobjtype::text AS objtype, d.defaclacl::text AS acl
  FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace ORDER BY 1, 2, 3;

-- D4: login roles that reach this database only through PUBLIC's CONNECT (they lose it), and
-- who is connected now, by user.
SELECT r.rolname AS connect_only_via_public
  FROM pg_roles r
 WHERE r.rolcanlogin AND NOT r.rolsuper
   AND has_database_privilege(r.oid, current_database(), 'CONNECT')
   AND NOT pg_has_role(r.oid, (SELECT datdba FROM pg_database WHERE datname = current_database()), 'USAGE')
   AND NOT EXISTS (SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
                    WHERE d.datname = current_database() AND a.grantee = r.oid AND a.privilege_type = 'CONNECT')
 ORDER BY 1;
SELECT usename, coalesce(application_name, '') AS application_name, count(*) AS sessions
  FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2 ORDER BY 1, 2;
