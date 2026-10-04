-- D2 step 2 of 3 (OPTIONAL, Owner names it; as postgres, bifrost_golden_source, one transaction):
-- schemas features and research move from bifrost to analytics_writer.
--
-- Not needed for the revoke (analytics_writer has USAGE and CREATE on both schemas by its own grant).
-- What it changes: a schema owner may DROP any object in its schema, so while bifrost owns these two
-- schemas, everything holding bifrost's password (db-init, market-data, flex-query, CNPG's app Secret)
-- can drop Research's tables. After it, only analytics_writer (and postgres) can.
--
-- ALTER SCHEMA … OWNER rewrites the schema ACL like a table's: bifrost's entry merges into
-- analytics_writer's, market_reader keeps USAGE with analytics_writer as grantor. bifrost gets USAGE
-- back (it reads features.option_metric_*); it does not get CREATE back (nothing creates Research
-- objects as bifrost after D2). Idempotent.

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER SCHEMA features OWNER TO analytics_writer;
ALTER SCHEMA research OWNER TO analytics_writer;
GRANT USAGE ON SCHEMA features, research TO bifrost;

COMMIT;
