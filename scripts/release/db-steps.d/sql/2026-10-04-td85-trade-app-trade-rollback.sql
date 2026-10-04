-- Rollback of 2026-10-04-td85-trade-app-trade.sql for one env. First point the env back at bifrost
-- (scripts/trade-app-role.sh rollback <env>) and, if it ran, roll back the public-revoke step.
--   psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < this file
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
  \echo 'td85: role' :role 'does not exist; nothing to roll back here'
  \quit
\endif

BEGIN;
SET LOCAL lock_timeout = '10s';
DROP USER MAPPING IF EXISTS FOR :"role" SERVER golden_source_server;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA brokerage, market REVOKE ALL ON TABLES FROM :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA brokerage, market REVOKE ALL ON TABLES FROM :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA public REVOKE ALL ON SEQUENCES FROM :"role";
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA public REVOKE ALL ON TABLES FROM :"role";
REVOKE ALL ON ALL TABLES IN SCHEMA public, brokerage, market FROM :"role";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"role";
REVOKE ALL ON SCHEMA public, brokerage, market FROM :"role";
REVOKE ALL ON DATABASE :"db" FROM :"role";
COMMIT;

SELECT count(*) AS acl_entries_left
  FROM pg_class c, aclexplode(c.relacl) a
 WHERE a.grantee = to_regrole(:'role');
