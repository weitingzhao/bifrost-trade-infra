-- Put back the grants removed by 2026-10-07-td85-analytics-writer-create-revoke.sql.
-- Run as postgres, in bifrost_golden_source.
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

GRANT CREATE ON SCHEMA raw_market TO analytics_writer;
GRANT CREATE ON SCHEMA raw_broker TO analytics_writer;
GRANT CREATE ON SCHEMA ops_jobs TO analytics_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  ops_jobs.data_source_void,
  ops_jobs.symbol_source_void,
  ops_jobs.watchlist_cache
  TO analytics_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE raw_market.ticker_related TO market_reader;

COMMIT;
