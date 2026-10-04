-- Rollback of the D8 complement: schema brokerage back to postgres, bifrost and trade_app_dev keep USAGE.
BEGIN;
ALTER SCHEMA brokerage OWNER TO postgres;
GRANT USAGE ON SCHEMA brokerage TO bifrost, trade_app_dev;
COMMIT;
