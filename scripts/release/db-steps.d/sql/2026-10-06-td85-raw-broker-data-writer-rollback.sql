-- Rollback of 2026-10-06-td85-raw-broker-data-writer-revoke: what core 0.48.1's db-init granted.
\set ON_ERROR_STOP on
BEGIN;
GRANT USAGE ON SCHEMA raw_broker TO data_writer;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_broker TO data_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw_broker TO data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker GRANT USAGE, SELECT ON SEQUENCES TO data_writer;
COMMIT;
