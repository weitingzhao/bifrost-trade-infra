-- Rollback of 2026-10-06-td85-gs-public-connect-revoke: PUBLIC may connect to bifrost_golden_source again.
\set ON_ERROR_STOP on
BEGIN;
GRANT CONNECT ON DATABASE bifrost_golden_source TO PUBLIC;
COMMIT;
