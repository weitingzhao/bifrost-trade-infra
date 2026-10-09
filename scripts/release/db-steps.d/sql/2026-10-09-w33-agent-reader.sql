-- Read-only login for Agent queries. Member of pg_read_all_data.
-- CONNECT on the four databases. No password in this file.
-- Not applied by this commit. The Owner sets the password out of band.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $w33$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
    CREATE ROLE agent_reader
      LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
      CONNECTION LIMIT 8;
  END IF;
END
$w33$;

ALTER ROLE agent_reader WITH LOGIN INHERIT CONNECTION LIMIT 8;
ALTER ROLE agent_reader SET default_transaction_read_only = on;
ALTER ROLE agent_reader SET statement_timeout = '120s';
ALTER ROLE agent_reader SET idle_in_transaction_session_timeout = '60s';

GRANT pg_read_all_data TO agent_reader;
GRANT CONNECT ON DATABASE bifrost_dev TO agent_reader;
GRANT CONNECT ON DATABASE bifrost_stg TO agent_reader;
GRANT CONNECT ON DATABASE bifrost_prod TO agent_reader;
GRANT CONNECT ON DATABASE bifrost_golden_source TO agent_reader;

COMMENT ON ROLE agent_reader IS
  'W-33: read-only login. pg_read_all_data plus CONNECT on the four databases.';

COMMIT;
