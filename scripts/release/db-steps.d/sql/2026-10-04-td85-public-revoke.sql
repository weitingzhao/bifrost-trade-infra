-- TD-85 D4 (Owner 2026-10-04): close what PUBLIC may do on a Trade database. Run per env, as
-- postgres, in that env's database, only after ALL THREE envs run as trade_app_<env>:
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < this file
-- After it: only the owner bifrost, trade_app_<env> and brokerage_reader may connect, and only
-- explicit grantees may create in public (bifrost: explicit CREATE, added here where it came
-- from PUBLIC only, which is DEV). TEMP stays with PUBLIC. Golden Source is not touched (D6).
\set ON_ERROR_STOP on

\if :{?env}
\else
  \echo 'td85: pass -v env=dev|stg|prod'
  DO $$ BEGIN RAISE EXCEPTION 'td85: env not set'; END $$;
\endif
\set role 'trade_app_' :env
\set db 'bifrost_' :env
SELECT current_database() = :'db' AS td85_right_db, to_regrole(:'role') IS NOT NULL AS td85_role_exists \gset
\if :td85_right_db
\else
  \echo 'td85: this database is not' :db
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif
\if :td85_role_exists
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: trade_app role missing; the roles step comes first'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';

-- 1. Explicit CONNECT for everyone who needs it, before PUBLIC loses it. bifrost owns the
--    database (implicit). brokerage_reader: explicit in DEV / PROD already, missing in STG.
GRANT CONNECT ON DATABASE :"db" TO :"role", brokerage_reader;
-- 2. db-init (bifrost) creates tables in public: explicit CREATE (STG / PROD have it; DEV only
--    through PUBLIC, so without this DEV's next db-init fails).
GRANT USAGE, CREATE ON SCHEMA public TO bifrost;
-- 3. PUBLIC: no CONNECT, no CREATE in public.
REVOKE CONNECT ON DATABASE :"db" FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

COMMIT;

SELECT datname, datacl::text FROM pg_database WHERE datname = current_database();
SELECT nspname, nspacl::text FROM pg_namespace WHERE nspname = 'public';
