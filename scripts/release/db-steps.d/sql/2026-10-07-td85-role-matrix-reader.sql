-- Login that can CONNECT to the four databases and nothing else.
-- Catalog reads (pg_database, pg_namespace, pg_class, pg_roles, pg_auth_members)
-- need no further grants. No password in this file: the Owner sets one out of band
-- and stores it in Secret data/db-role-matrix-reader (keys username, password).
-- Run as postgres, in any database. Not applied by this commit.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $td85$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'role_matrix_reader') THEN
    CREATE ROLE role_matrix_reader
      LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END
$td85$;

COMMENT ON ROLE role_matrix_reader IS
  'TD-85: read-only login for the daily role-matrix check. CONNECT on the four databases only.';

GRANT CONNECT ON DATABASE bifrost_dev TO role_matrix_reader;
GRANT CONNECT ON DATABASE bifrost_stg TO role_matrix_reader;
GRANT CONNECT ON DATABASE bifrost_prod TO role_matrix_reader;
GRANT CONNECT ON DATABASE bifrost_golden_source TO role_matrix_reader;

COMMIT;
