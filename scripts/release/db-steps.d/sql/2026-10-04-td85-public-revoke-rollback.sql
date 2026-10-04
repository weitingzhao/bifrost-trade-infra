-- Rollback of 2026-10-04-td85-public-revoke.sql: PUBLIC gets CONNECT and CREATE-in-public back.
-- The explicit grants it added stay (harmless: the same rights as before).
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < this file
\set ON_ERROR_STOP on

\if :{?env}
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: pass -v env=dev|stg|prod'; END $$;
\endif
\set db 'bifrost_' :env
SELECT current_database() = :'db' AS td85_right_db \gset
\if :td85_right_db
\else
  DO $$ BEGIN RAISE EXCEPTION 'td85: wrong database'; END $$;
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';
GRANT CONNECT ON DATABASE :"db" TO PUBLIC;
GRANT CREATE ON SCHEMA public TO PUBLIC;
COMMIT;

SELECT datname, datacl::text FROM pg_database WHERE datname = current_database();
SELECT nspname, nspacl::text FROM pg_namespace WHERE nspname = 'public';
