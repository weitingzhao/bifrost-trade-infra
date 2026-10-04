-- D6 step 1 of 4 (as postgres; run in bifrost_golden_source; roles are cluster-wide). Additive: no plugin
-- changes behaviour (both still sign in as bifrost until the Secret switch).
--
--   M6  data_writer gets the role-level settings the plugin code was written against (it signed in as
--       bifrost, which carries them): statement_timeout 2s, lock_timeout 5s,
--       idle_in_transaction_session_timeout 15s. Long statements already raise their own limit
--       (SET LOCAL statement_timeout / libpq options), exactly as they do under bifrost.
--   F1  flex_writer: LOGIN NOINHERIT, no attributes, no memberships, same three settings. Created without a
--       password: nobody can sign in as it until `scripts/plugin-db-roles.sh password flex_writer`
--       sends a SCRAM verifier computed on the Owner's machine. data_writer keeps its existing
--       password until `… password data_writer` replaces it.
--
-- Idempotent. Rollback: sql/2026-10-04-d6-rollback-roles.sql (after the other rollbacks).
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $d6$
BEGIN
  IF to_regrole('data_writer') IS NULL THEN
    RAISE EXCEPTION 'd6: role data_writer is missing (market-data scripts/create_roles.sql created it)';
  END IF;
  IF pg_has_role('data_writer', 'bifrost', 'MEMBER') THEN
    RAISE EXCEPTION 'd6: data_writer is a member of bifrost; this plan assumes it is not';
  END IF;
  IF to_regrole('flex_writer') IS NULL THEN
    CREATE ROLE flex_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    RAISE NOTICE 'd6: role flex_writer created (no password yet)';
  ELSE
    RAISE NOTICE 'd6: role flex_writer exists, left as is';
  END IF;
END
$d6$;

ALTER ROLE data_writer SET statement_timeout = '2s';
ALTER ROLE data_writer SET lock_timeout = '5s';
ALTER ROLE data_writer SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE flex_writer SET statement_timeout = '2s';
ALTER ROLE flex_writer SET lock_timeout = '5s';
ALTER ROLE flex_writer SET idle_in_transaction_session_timeout = '15s';

COMMENT ON ROLE data_writer IS
  'market-data plugin (D6): owner of raw_market and of the market tables in ops_jobs; reads what Research publishes. Not a member of bifrost.';
COMMENT ON ROLE flex_writer IS
  'flex-query plugin (D6): owner of its four ops_jobs tables; raw_broker flex DML only; read-only on the Trade database it reads.';

COMMIT;

SELECT rolname, rolcanlogin, rolinherit, rolpassword IS NOT NULL AS has_password,
       (SELECT setconfig FROM pg_db_role_setting s WHERE s.setrole = a.oid AND s.setdatabase = 0) AS settings
FROM pg_authid a WHERE rolname IN ('data_writer', 'flex_writer') ORDER BY 1;
