-- D6 rollback, roles (as postgres; last, after …-rollback-gs.sql and …-rollback-trade.sql in bifrost_dev).
-- DROP ROLE refuses while flex_writer still owns or holds anything in any database: that error names the
-- object, which means a rollback file above was skipped. data_writer's role settings and comment go; its
-- password stays whatever `scripts/plugin-db-roles.sh password data_writer` set (nothing used the old one:
-- no data_writer session existed before D6).
\set ON_ERROR_STOP on
BEGIN;
DROP ROLE IF EXISTS flex_writer;
ALTER ROLE data_writer RESET statement_timeout;
ALTER ROLE data_writer RESET lock_timeout;
ALTER ROLE data_writer RESET idle_in_transaction_session_timeout;
COMMENT ON ROLE data_writer IS NULL;
COMMIT;
