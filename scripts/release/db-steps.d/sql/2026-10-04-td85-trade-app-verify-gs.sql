-- TD-85 verify (read-only), Golden Source, all three roles, after ...-td85-trade-app-gs.sql:
--   psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < this file
-- Expect: section 2 granted = required, missing empty, for each role; section 3 all zero / false,
-- schemas_with_usage = public,raw_broker (plus ops_feedback, and ops_feedback_optional = 2, only
-- if the optional ops_feedback file ran).
-- Section 2 is the measured table set (method: the Trade verify file), plus the paths that pick
-- the table at run time (portfolio/reader/accounts.py raw_tbl; accounts_sync shared with the daemon).
\set ON_ERROR_STOP on
SELECT current_database() = 'bifrost_golden_source' AS td85_right_db \gset
\if :td85_right_db
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: run this file in bifrost_golden_source'; END $$;
\endif

-- 1. Role attributes: LOGIN, NOINHERIT, no SUPERUSER / CREATEDB / CREATEROLE / REPLICATION / BYPASSRLS,
--    member of nothing, a SCRAM password, the same role-level settings as bifrost.
SELECT r.rolname,
       r.rolcanlogin AS login, r.rolinherit AS inherit,
       (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls) AS any_power,
       (SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid) AS memberships,
       coalesce(a.rolpassword LIKE 'SCRAM-SHA-256$%', false) AS scram_password,
       (SELECT array_agg(x ORDER BY x) FROM pg_db_role_setting, unnest(setconfig) x WHERE setrole = r.oid AND setdatabase = 0)
         IS NOT DISTINCT FROM
       (SELECT array_agg(x ORDER BY x) FROM pg_db_role_setting, unnest(setconfig) x WHERE setrole = 'bifrost'::regrole AND setdatabase = 0)
         AS settings_as_bifrost
  FROM pg_roles r JOIN pg_authid a ON a.oid = r.oid
 WHERE r.rolname LIKE 'trade\_app\_%'
 ORDER BY 1;

-- 2. Required by the code, per role.
SELECT r.rolname, count(*) AS required,
       count(*) FILTER (WHERE has_table_privilege(r.rolname, obj, priv)) AS granted,
       string_agg(obj || ' ' || priv, ', ') FILTER (WHERE NOT has_table_privilege(r.rolname, obj, priv)) AS missing
  FROM pg_roles r,
       (VALUES
  ('raw_broker.account', 'INSERT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.account', 'SELECT', 'daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.account', 'UPDATE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.commissions', 'DELETE', 'api/core portfolio:accounts.py'),
  ('raw_broker.commissions', 'INSERT', 'api/core portfolio:accounts.py; daemon/core sink:postgres_sink.py'),
  ('raw_broker.commissions', 'SELECT', 'api/core portfolio:accounts.py'),
  ('raw_broker.commissions', 'UPDATE', 'api/core portfolio:accounts.py; daemon/core sink:postgres_sink.py'),
  ('raw_broker.contract_quote_live', 'INSERT', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.contract_quote_live', 'UPDATE', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.executions_raw_flex', 'DELETE', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'INSERT', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'SELECT', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'UPDATE', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'DELETE', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'SELECT', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'UPDATE', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'DELETE', 'api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)...'),
  ('raw_broker.executions_raw_tws', 'SELECT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'UPDATE', 'api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.open_orders', 'INSERT', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.open_orders', 'SELECT', 'daemon/core sink:postgres_sink.py(write_open_orders)'),
  ('raw_broker.open_orders', 'TRUNCATE', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.positions', 'DELETE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'INSERT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'SELECT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'UPDATE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.transactions', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(upsert_account_transactions)'),
  ('raw_broker.transactions', 'SELECT', 'api/core portfolio:accounts.py(upsert_account_transactions)'),
  ('raw_broker.transactions', 'UPDATE', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(upsert_account_transactions)')
       ) AS need(obj, priv, path)
 WHERE r.rolname LIKE 'trade\_app\_%'
 GROUP BY 1 ORDER BY 1;
SELECT obj, priv, path
  FROM (VALUES
  ('raw_broker.account', 'INSERT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.account', 'SELECT', 'daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.account', 'UPDATE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.commissions', 'DELETE', 'api/core portfolio:accounts.py'),
  ('raw_broker.commissions', 'INSERT', 'api/core portfolio:accounts.py; daemon/core sink:postgres_sink.py'),
  ('raw_broker.commissions', 'SELECT', 'api/core portfolio:accounts.py'),
  ('raw_broker.commissions', 'UPDATE', 'api/core portfolio:accounts.py; daemon/core sink:postgres_sink.py'),
  ('raw_broker.contract_quote_live', 'INSERT', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.contract_quote_live', 'UPDATE', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.executions_raw_flex', 'DELETE', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'INSERT', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'SELECT', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_flex', 'UPDATE', 'api/core portfolio:accounts.py(write_account_executions_to_db, update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'DELETE', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'SELECT', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_journal', 'UPDATE', 'api/core portfolio:accounts.py(insert/update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'DELETE', 'api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)...'),
  ('raw_broker.executions_raw_tws', 'SELECT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.executions_raw_tws', 'UPDATE', 'api/core portfolio:accounts.py(_fill_key lock, update/delete_one_execution)'),
  ('raw_broker.open_orders', 'INSERT', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.open_orders', 'SELECT', 'daemon/core sink:postgres_sink.py(write_open_orders)'),
  ('raw_broker.open_orders', 'TRUNCATE', 'daemon/core sink:postgres_sink.py'),
  ('raw_broker.positions', 'DELETE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'INSERT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'SELECT', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.positions', 'UPDATE', 'api/core portfolio:accounts_sync.py; daemon/core sink:accounts_sync.py(sync_accounts_snapshot_to_tables)'),
  ('raw_broker.transactions', 'INSERT', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(upsert_account_transactions)'),
  ('raw_broker.transactions', 'SELECT', 'api/core portfolio:accounts.py(upsert_account_transactions)'),
  ('raw_broker.transactions', 'UPDATE', 'api/core portfolio:accounts.py; api/core portfolio:accounts.py(upsert_account_transactions)')
       ) AS need(obj, priv, path)
 ORDER BY obj, priv;

-- 3. Nothing more, per role.
SELECT r.rolname,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT IN ('raw_broker', 'ops_feedback', 'pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\_toast%' AND c.relkind IN ('r', 'p', 'v', 'f', 'm')
      AND (has_table_privilege(r.oid, c.oid, 'SELECT') OR has_table_privilege(r.oid, c.oid, 'INSERT')
           OR has_table_privilege(r.oid, c.oid, 'UPDATE') OR has_table_privilege(r.oid, c.oid, 'DELETE')
           OR has_table_privilege(r.oid, c.oid, 'TRUNCATE') OR has_table_privilege(r.oid, c.oid, 'REFERENCES')
           OR has_table_privilege(r.oid, c.oid, 'TRIGGER') OR has_table_privilege(r.oid, c.oid, 'MAINTAIN'))) AS rels_outside_raw_broker,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT IN ('raw_broker', 'ops_feedback') AND c.relkind = 'S'
      AND CASE WHEN c.relkind = 'S' THEN has_sequence_privilege(r.oid, c.oid, 'USAGE') OR has_sequence_privilege(r.oid, c.oid, 'SELECT')
               OR has_sequence_privilege(r.oid, c.oid, 'UPDATE') END) AS seqs_outside_raw_broker,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ops_feedback' AND c.relkind IN ('r', 'p')
      AND has_table_privilege(r.oid, c.oid, 'SELECT')) AS ops_feedback_optional,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'raw_broker' AND c.relname <> 'open_orders' AND c.relkind IN ('r', 'p', 'v')
      AND has_table_privilege(r.oid, c.oid, 'TRUNCATE')) AS truncate_besides_open_orders,
  (SELECT count(*) FROM pg_namespace n
    WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname <> 'information_schema'
      AND has_schema_privilege(r.oid, n.oid, 'CREATE')) AS schemas_with_create,
  (SELECT string_agg(n.nspname, ',' ORDER BY n.nspname) FROM pg_namespace n
    WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname <> 'information_schema'
      AND has_schema_privilege(r.oid, n.oid, 'USAGE')) AS schemas_with_usage,
  has_database_privilege(r.oid, current_database(), 'CREATE') AS create_schema_in_db
  FROM pg_roles r WHERE r.rolname LIKE 'trade\_app\_%' ORDER BY 1;

-- 4. Default privileges for what bifrost creates later.
SELECT pg_get_userbyid(d.defaclrole) AS for_role, n.nspname, d.defaclobjtype::text AS objtype,
       pg_get_userbyid(a.grantee) AS grantee, string_agg(a.privilege_type, ',' ORDER BY a.privilege_type) AS privs
  FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace, aclexplode(d.defaclacl) a
 WHERE pg_get_userbyid(a.grantee) LIKE 'trade\_app\_%'
 GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;
