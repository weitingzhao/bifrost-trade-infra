-- TD-85 verify (read-only), Trade database of one env, after ...-td85-trade-app-trade.sql:
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -c "SET default_transaction_read_only=on;" -f - < this file
-- Expect: section 2 granted = required, missing empty; section 3 granted = objects; section 4 all
-- zero / false except create_via_public and the other roles' connect (true until the public-revoke
-- step); section 5 the role's mapping -> brokerage_reader; section 6 reads through the FDW as the role.
--
-- Section 2 is the table set the runtime code touches, measured statically from core 0.45.0
-- (0f7026e), api 0.7.3 (8e52001) and worker 0.2.4 (1388553): every SQL string literal with module
-- constants resolved (INSERT / UPDATE / DELETE / TRUNCATE / FROM / JOIN; FOR UPDATE -> UPDATE;
-- ON CONFLICT DO UPDATE -> INSERT + UPDATE). db-init / migration modules are left out (they run as bifrost).
\set ON_ERROR_STOP on
\if :{?env}
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: pass -v env=dev|stg|prod'; END $$;
\endif
\set role 'trade_app_' :env
\set db 'bifrost_' :env
SELECT current_database() = :'db' AS td85_right_db, to_regrole(:'role') IS NOT NULL AS td85_role_exists \gset
\if :td85_right_db
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif
\if :td85_role_exists
\else
  \echo 'td85: role' :role 'does not exist yet'
  \quit
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
 WHERE r.rolname = :'role'
 ORDER BY 1;

-- 2. Required by the code: (object, privilege, where in the code).
SELECT count(*) AS required,
       count(*) FILTER (WHERE has_table_privilege(:'role', obj, priv)) AS granted,
       string_agg(obj || ' ' || priv, ', ') FILTER (WHERE NOT has_table_privilege(:'role', obj, priv)) AS missing
  FROM (VALUES
  ('brokerage.account', 'SELECT', 'api/core portfolio:accounts.py+accounts_helpers.py+core.py'),
  ('brokerage.commissions', 'SELECT', 'api/core portfolio:executions.py'),
  ('brokerage.contract_quote_live', 'SELECT', 'api/core monitor:market.py+strategy_instance.py; api/core portfolio:accounts.py+core.py+executions.py+short...'),
  ('brokerage.executions_final', 'SELECT', 'api/core monitor:strategy_win_rate.py; api/core portfolio:executions.py+option_stock_link.py'),
  ('brokerage.executions_tws', 'SELECT', 'api/core portfolio:executions.py'),
  ('brokerage.open_orders', 'SELECT', 'api/core monitor:status.py'),
  ('brokerage.positions', 'SELECT', 'api/core monitor:strategy_instance.py; api/core portfolio:accounts.py+core.py+executions.py+short_legs.py'),
  ('brokerage.trade_fill_splits', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_win_rate.py; api/core portfolio:accounts.py+executions.py'),
  ('market.us_market_holiday', 'SELECT', 'api/core monitor:market.py'),
  ('public.account_execution_option_stock_link', 'DELETE', 'api/core portfolio:option_stock_link.py'),
  ('public.account_execution_option_stock_link', 'INSERT', 'api/core portfolio:option_stock_link.py'),
  ('public.account_execution_option_stock_link', 'SELECT', 'api/core portfolio:accounts.py+option_stock_link.py'),
  ('public.gate_safety_strategy', 'INSERT', 'api/core monitor:gate_safety_write.py'),
  ('public.gate_safety_strategy', 'SELECT', 'api/core monitor:gate_safety.py+strategy.py'),
  ('public.gate_safety_strategy', 'UPDATE', 'api/core monitor:gate_safety_write.py'),
  ('public.preference_instrument_class', 'DELETE', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'INSERT', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'SELECT', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'UPDATE', 'api/core portfolio:instrument_class.py'),
  ('public.preference_market_streams_symbol_order', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'SELECT', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'SELECT', 'api/core monitor:watchlist.py; api/core portfolio:accounts.py+position_categories.py'),
  ('public.preference_position_categories', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'SELECT', 'api/core portfolio:accounts.py+position_categories.py'),
  ('public.preference_position_category_tags', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_saved_search', 'DELETE', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'INSERT', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'SELECT', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'UPDATE', 'api/core monitor:saved_search.py'),
  ('public.settings', 'INSERT', 'api/core monitor:settings.py'),
  ('public.settings', 'SELECT', 'api/core monitor:gate_safety.py+settings.py+strategy_rules_delete.py; daemon/core sink:postgres_sink.py'),
  ('public.settings', 'UPDATE', 'api/core monitor:settings.py+strategy_structure_write.py'),
  ('public.strategy_allocation', 'INSERT', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation', 'SELECT', 'api/core monitor:strategy.py+strategy_rules_delete.py'),
  ('public.strategy_allocation', 'UPDATE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'DELETE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'INSERT', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'SELECT', 'api/core monitor:strategy.py+strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'UPDATE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_opportunity', 'INSERT', 'api/core monitor:strategy_opportunity_write.py'),
  ('public.strategy_opportunity', 'SELECT', 'api/core monitor:strategy.py+strategy_instance.py+strategy_opportunity_write.py+strategy_rules_delete.py; a...'),
  ('public.strategy_opportunity', 'UPDATE', 'api/core monitor:strategy_opportunity_write.py'),
  ('public.strategy_plan', 'DELETE', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_plan', 'INSERT', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_plan', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_plan.py'),
  ('public.strategy_plan', 'UPDATE', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_structure', 'INSERT', 'api/core monitor:strategy_structure_write.py'),
  ('public.strategy_structure', 'SELECT', 'api/core monitor:strategy.py+strategy_instance.py+strategy_structure_write.py+template_config.py+template_c...'),
  ('public.strategy_structure', 'UPDATE', 'api/core monitor:strategy_structure_write.py'),
  ('public.strategy_template', 'DELETE', 'api/core monitor:template_config_write.py'),
  ('public.strategy_template', 'INSERT', 'api/core monitor:template_config_write.py'),
  ('public.strategy_template', 'SELECT', 'api/core monitor:strategy.py+template_config.py+template_config_write.py; api/core portfolio:executions.py'),
  ('public.strategy_template', 'UPDATE', 'api/core monitor:template_config_write.py'),
  ('public.trade', 'DELETE', 'api/core monitor:strategy_instance.py'),
  ('public.trade', 'INSERT', 'api/core monitor:strategy_instance.py'),
  ('public.trade', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_plan.py+strategy_rules_delete.py+trade_review.py; api/core p...'),
  ('public.trade', 'UPDATE', 'api/core monitor:strategy_instance.py'),
  ('public.trade_execution', 'DELETE', 'api/core portfolio:accounts.py'),
  ('public.trade_execution', 'INSERT', 'api/core portfolio:accounts.py'),
  ('public.trade_execution', 'SELECT', 'api/core monitor:instance_state.py+strategy_instance.py; api/core portfolio:accounts.py'),
  ('public.trade_execution', 'UPDATE', 'api/core portfolio:accounts.py'),
  ('public.trade_review', 'INSERT', 'api/core monitor:trade_review.py'),
  ('public.trade_review', 'SELECT', 'api/core monitor:strategy_instance.py+trade_review.py'),
  ('public.trade_review', 'UPDATE', 'api/core monitor:trade_review.py'),
  ('public.watchlist', 'DELETE', 'api/core monitor:watchlist.py'),
  ('public.watchlist', 'INSERT', 'api/core monitor:watchlist.py'),
  ('public.watchlist', 'SELECT', 'api/core monitor:watchlist.py; api/core portfolio:accounts.py+position_categories.py'),
  ('public.watchlist', 'UPDATE', 'api/core monitor:watchlist.py')
       ) AS need(obj, priv, path);
SELECT obj, priv, has_table_privilege(:'role', obj, priv) AS ok, path
  FROM (VALUES
  ('brokerage.account', 'SELECT', 'api/core portfolio:accounts.py+accounts_helpers.py+core.py'),
  ('brokerage.commissions', 'SELECT', 'api/core portfolio:executions.py'),
  ('brokerage.contract_quote_live', 'SELECT', 'api/core monitor:market.py+strategy_instance.py; api/core portfolio:accounts.py+core.py+executions.py+short...'),
  ('brokerage.executions_final', 'SELECT', 'api/core monitor:strategy_win_rate.py; api/core portfolio:executions.py+option_stock_link.py'),
  ('brokerage.executions_tws', 'SELECT', 'api/core portfolio:executions.py'),
  ('brokerage.open_orders', 'SELECT', 'api/core monitor:status.py'),
  ('brokerage.positions', 'SELECT', 'api/core monitor:strategy_instance.py; api/core portfolio:accounts.py+core.py+executions.py+short_legs.py'),
  ('brokerage.trade_fill_splits', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_win_rate.py; api/core portfolio:accounts.py+executions.py'),
  ('market.us_market_holiday', 'SELECT', 'api/core monitor:market.py'),
  ('public.account_execution_option_stock_link', 'DELETE', 'api/core portfolio:option_stock_link.py'),
  ('public.account_execution_option_stock_link', 'INSERT', 'api/core portfolio:option_stock_link.py'),
  ('public.account_execution_option_stock_link', 'SELECT', 'api/core portfolio:accounts.py+option_stock_link.py'),
  ('public.gate_safety_strategy', 'INSERT', 'api/core monitor:gate_safety_write.py'),
  ('public.gate_safety_strategy', 'SELECT', 'api/core monitor:gate_safety.py+strategy.py'),
  ('public.gate_safety_strategy', 'UPDATE', 'api/core monitor:gate_safety_write.py'),
  ('public.preference_instrument_class', 'DELETE', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'INSERT', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'SELECT', 'api/core portfolio:instrument_class.py'),
  ('public.preference_instrument_class', 'UPDATE', 'api/core portfolio:instrument_class.py'),
  ('public.preference_market_streams_symbol_order', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'SELECT', 'api/core portfolio:position_categories.py'),
  ('public.preference_market_streams_symbol_order', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_categories', 'SELECT', 'api/core monitor:watchlist.py; api/core portfolio:accounts.py+position_categories.py'),
  ('public.preference_position_categories', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'DELETE', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'INSERT', 'api/core portfolio:position_categories.py'),
  ('public.preference_position_category_tags', 'SELECT', 'api/core portfolio:accounts.py+position_categories.py'),
  ('public.preference_position_category_tags', 'UPDATE', 'api/core portfolio:position_categories.py'),
  ('public.preference_saved_search', 'DELETE', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'INSERT', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'SELECT', 'api/core monitor:saved_search.py'),
  ('public.preference_saved_search', 'UPDATE', 'api/core monitor:saved_search.py'),
  ('public.settings', 'INSERT', 'api/core monitor:settings.py'),
  ('public.settings', 'SELECT', 'api/core monitor:gate_safety.py+settings.py+strategy_rules_delete.py; daemon/core sink:postgres_sink.py'),
  ('public.settings', 'UPDATE', 'api/core monitor:settings.py+strategy_structure_write.py'),
  ('public.strategy_allocation', 'INSERT', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation', 'SELECT', 'api/core monitor:strategy.py+strategy_rules_delete.py'),
  ('public.strategy_allocation', 'UPDATE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'DELETE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'INSERT', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'SELECT', 'api/core monitor:strategy.py+strategy_allocation_write.py'),
  ('public.strategy_allocation_opportunity', 'UPDATE', 'api/core monitor:strategy_allocation_write.py'),
  ('public.strategy_opportunity', 'INSERT', 'api/core monitor:strategy_opportunity_write.py'),
  ('public.strategy_opportunity', 'SELECT', 'api/core monitor:strategy.py+strategy_instance.py+strategy_opportunity_write.py+strategy_rules_delete.py; a...'),
  ('public.strategy_opportunity', 'UPDATE', 'api/core monitor:strategy_opportunity_write.py'),
  ('public.strategy_plan', 'DELETE', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_plan', 'INSERT', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_plan', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_plan.py'),
  ('public.strategy_plan', 'UPDATE', 'api/core monitor:strategy_plan.py'),
  ('public.strategy_structure', 'INSERT', 'api/core monitor:strategy_structure_write.py'),
  ('public.strategy_structure', 'SELECT', 'api/core monitor:strategy.py+strategy_instance.py+strategy_structure_write.py+template_config.py+template_c...'),
  ('public.strategy_structure', 'UPDATE', 'api/core monitor:strategy_structure_write.py'),
  ('public.strategy_template', 'DELETE', 'api/core monitor:template_config_write.py'),
  ('public.strategy_template', 'INSERT', 'api/core monitor:template_config_write.py'),
  ('public.strategy_template', 'SELECT', 'api/core monitor:strategy.py+template_config.py+template_config_write.py; api/core portfolio:executions.py'),
  ('public.strategy_template', 'UPDATE', 'api/core monitor:template_config_write.py'),
  ('public.trade', 'DELETE', 'api/core monitor:strategy_instance.py'),
  ('public.trade', 'INSERT', 'api/core monitor:strategy_instance.py'),
  ('public.trade', 'SELECT', 'api/core monitor:strategy_instance.py+strategy_plan.py+strategy_rules_delete.py+trade_review.py; api/core p...'),
  ('public.trade', 'UPDATE', 'api/core monitor:strategy_instance.py'),
  ('public.trade_execution', 'DELETE', 'api/core portfolio:accounts.py'),
  ('public.trade_execution', 'INSERT', 'api/core portfolio:accounts.py'),
  ('public.trade_execution', 'SELECT', 'api/core monitor:instance_state.py+strategy_instance.py; api/core portfolio:accounts.py'),
  ('public.trade_execution', 'UPDATE', 'api/core portfolio:accounts.py'),
  ('public.trade_review', 'INSERT', 'api/core monitor:trade_review.py'),
  ('public.trade_review', 'SELECT', 'api/core monitor:strategy_instance.py+trade_review.py'),
  ('public.trade_review', 'UPDATE', 'api/core monitor:trade_review.py'),
  ('public.watchlist', 'DELETE', 'api/core monitor:watchlist.py'),
  ('public.watchlist', 'INSERT', 'api/core monitor:watchlist.py'),
  ('public.watchlist', 'SELECT', 'api/core monitor:watchlist.py; api/core portfolio:accounts.py+position_categories.py'),
  ('public.watchlist', 'UPDATE', 'api/core monitor:watchlist.py')
       ) AS need(obj, priv, path)
 ORDER BY ok, obj, priv;

-- 3. Whole-schema coverage (what the grant gives; a superset of section 2).
SELECT n.nspname, c.relkind::text AS kind, count(*) AS objects,
       count(*) FILTER (WHERE CASE WHEN c.relkind = 'S' THEN has_sequence_privilege(:'role', c.oid, 'USAGE, SELECT, UPDATE')
                                   WHEN n.nspname = 'public' THEN has_table_privilege(:'role', c.oid, 'SELECT, INSERT, UPDATE, DELETE')
                                   ELSE has_table_privilege(:'role', c.oid, 'SELECT') END) AS granted
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('public', 'brokerage', 'market') AND c.relkind IN ('r', 'p', 'v', 'f', 'S')
 GROUP BY 1, 2 ORDER BY 1, 2;

-- 4. Nothing more: no write on brokerage / market, no TRUNCATE / REFERENCES / TRIGGER / MAINTAIN
--    anywhere, no CREATE except what PUBLIC still gives until the public-revoke step, and nothing
--    for the other envs' roles in this database.
SELECT
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('brokerage', 'market') AND c.relkind IN ('r', 'v', 'f')
      AND (has_table_privilege(:'role', c.oid, 'INSERT') OR has_table_privilege(:'role', c.oid, 'UPDATE')
           OR has_table_privilege(:'role', c.oid, 'DELETE'))) AS fdw_writable,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND c.relkind IN ('r', 'p', 'v', 'f', 'm')
      AND (has_table_privilege(:'role', c.oid, 'TRUNCATE') OR has_table_privilege(:'role', c.oid, 'REFERENCES')
           OR has_table_privilege(:'role', c.oid, 'TRIGGER') OR has_table_privilege(:'role', c.oid, 'MAINTAIN'))) AS truncate_ref_trigger_maintain,
  (SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a
    WHERE a.grantee = to_regrole(:'role') AND a.privilege_type = 'CREATE') AS explicit_schema_create,
  (SELECT count(*) FROM pg_namespace n
    WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname <> 'information_schema' AND n.nspname <> 'public'
      AND has_schema_privilege(:'role', n.oid, 'CREATE')) AS create_outside_public,
  has_schema_privilege(:'role', 'public', 'CREATE') AS create_via_public,
  has_database_privilege(:'role', current_database(), 'CREATE') AS create_schema_in_db;
SELECT o.rolname AS other_role,
       has_database_privilege(o.rolname, current_database(), 'CONNECT') AS connect_until_public_revoke,
       (SELECT count(*) FROM pg_class c, aclexplode(c.relacl) a WHERE a.grantee = o.oid) AS object_grants,
       (SELECT count(*) FROM pg_default_acl d, aclexplode(d.defaclacl) a WHERE a.grantee = o.oid) AS default_grants,
       (SELECT count(*) FROM pg_user_mappings m WHERE m.usename = o.rolname) AS user_mappings
  FROM pg_roles o
 WHERE o.rolname LIKE 'trade\_app\_%' AND o.rolname <> :'role'
 ORDER BY 1;

-- 5. FDW user mappings (remote user only; the password option is never selected) and default privileges.
SELECT srvname, usename,
       (SELECT substr(o, 6) FROM unnest(umoptions) o WHERE o LIKE 'user=%') AS remote_user,
       EXISTS (SELECT 1 FROM unnest(umoptions) o WHERE o LIKE 'password=%') AS has_password
  FROM pg_user_mappings WHERE usename IN (:'role', 'bifrost', 'postgres') ORDER BY usename;
SELECT pg_get_userbyid(d.defaclrole) AS for_role, n.nspname, d.defaclobjtype::text AS objtype,
       string_agg(a.privilege_type, ',' ORDER BY a.privilege_type) AS privs
  FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace, aclexplode(d.defaclacl) a
 WHERE a.grantee = to_regrole(:'role') GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- 6. Reads through the FDW as the role (foreign table: its own mapping; view: the view owner's).
SET ROLE :"role";
SELECT current_user AS as_role,
       (SELECT count(*) FROM (SELECT 1 FROM brokerage.account LIMIT 1) x) AS foreign_table_rows_seen,
       (SELECT count(*) FROM (SELECT 1 FROM brokerage.executions_final LIMIT 1) x) AS view_rows_seen,
       (SELECT count(*) FROM (SELECT 1 FROM market.us_market_holiday LIMIT 1) x) AS market_rows_seen;
RESET ROLE;
