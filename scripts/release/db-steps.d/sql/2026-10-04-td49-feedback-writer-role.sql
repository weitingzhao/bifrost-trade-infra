-- TD-49 D4 / TD-77 E5 (Owner 2026-10-03, item 4): a role that can read and write ops_feedback and
-- nothing else, for trade-api's feedback store (api 0.7.5, env FEEDBACK_PG_*).
-- Database: bifrost_golden_source (one copy shared by dev, stg and prod).
-- Run as postgres: psql -v ON_ERROR_STOP=1 -f - < this file   (it has its own BEGIN / COMMIT)
--
-- Idempotent: a second run changes nothing. No password here (all repos are public): the role is
-- created LOGIN without one, so nobody can sign in as it until the Owner runs
-- `scripts/feedback-writer-secret.sh password`, which sends only a SCRAM verifier computed locally.
--
-- Split of duties: the DDL (ops_feedback.* tables, owner bifrost) stays with db-init, which connects
-- as bifrost (api scripts/run_db_refresh_schema.py -> feedback_schema.ensure_feedback_schema).
-- feedback_writer gets DML only, no CREATE on the schema. ALTER DEFAULT PRIVILEGES FOR ROLE bifrost
-- covers a table or sequence a later feedback_schema step creates; a new column is covered by the
-- table grant.
-- SELECT / INSERT / UPDATE only: what the store uses. No DELETE (Owner 2026-10-04, decision C): a
-- report is closed by status (wontfix), never deleted by the service. Identity columns need no
-- sequence privilege; USAGE is granted so
-- a future serial column or explicit nextval() works too.
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $td49$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'feedback_writer') THEN
    CREATE ROLE feedback_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ops_feedback') THEN
    RAISE EXCEPTION 'schema ops_feedback is missing: run the db-init (trade-api >= 0.6.8) first';
  END IF;
END
$td49$;

COMMENT ON ROLE feedback_writer IS
  'trade-api feedback store (ops_feedback.* DML only; TD-49 D4 / TD-77 E5). DDL stays with bifrost (db-init).';

GRANT CONNECT ON DATABASE bifrost_golden_source TO feedback_writer;
GRANT USAGE ON SCHEMA ops_feedback TO feedback_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ops_feedback TO feedback_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ops_feedback TO feedback_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback
  GRANT SELECT, INSERT, UPDATE ON TABLES TO feedback_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback
  GRANT USAGE ON SEQUENCES TO feedback_writer;

COMMIT;
