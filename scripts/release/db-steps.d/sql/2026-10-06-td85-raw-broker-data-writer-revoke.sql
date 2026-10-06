-- TD-85 D6 follow-up (as postgres, bifrost_golden_source, one transaction): data_writer -- the market-data
-- plugin's login since D6 -- loses everything in raw_broker. The plugin names no raw_broker object; every
-- core db-init up to 0.48.1 granted it S/I/U/D/T on all raw_broker tables and views, USAGE/SELECT on the
-- sequences and the same through bifrost's default privileges. Run only after every env runs core >= 0.48.2,
-- or the next db-init grants it all back. Idempotent.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
REVOKE ALL ON ALL TABLES IN SCHEMA raw_broker FROM data_writer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_broker FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker REVOKE ALL ON TABLES FROM data_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker REVOKE ALL ON SEQUENCES FROM data_writer;
REVOKE USAGE ON SCHEMA raw_broker FROM data_writer;
COMMIT;
