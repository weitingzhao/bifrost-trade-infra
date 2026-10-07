-- TD-85 role matrix: take Research's schema CREATE off ingest and brokerage,
-- and the table DML that is not required to call ops_jobs.ensure_month_partitions.
-- Run as postgres, in bifrost_golden_source. Not applied by this commit.
-- Idempotent. SELECT and USAGE are left in place.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $td85$
BEGIN
  IF current_database() <> 'bifrost_golden_source' THEN
    RAISE EXCEPTION 'td85: run this in bifrost_golden_source, not %', current_database();
  END IF;
END
$td85$;

REVOKE CREATE ON SCHEMA raw_market FROM analytics_writer;
REVOKE CREATE ON SCHEMA raw_broker FROM analytics_writer;
REVOKE CREATE ON SCHEMA ops_jobs FROM analytics_writer;
REVOKE INSERT, UPDATE, DELETE ON TABLE
  ops_jobs.data_source_void,
  ops_jobs.symbol_source_void,
  ops_jobs.watchlist_cache
  FROM analytics_writer;
REVOKE INSERT, UPDATE, DELETE ON TABLE raw_market.ticker_related FROM market_reader;

COMMIT;
