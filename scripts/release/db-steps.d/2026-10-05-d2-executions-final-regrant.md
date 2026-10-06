---
id: 2026-10-05-d2-executions-final-regrant
envs: prod
when: after
done: prod
---
# TD-85 D2 follow-up: analytics_writer gets SELECT on raw_broker.executions_final back (Golden Source only)

Re-applies D2 step 1a (Owner-approved 2026-10-04). Found 2026-10-06 01:3x UTC: Research's
`research_memory_distill_job` failed at 2026-10-05 23:55 UTC with `permission denied for view executions_final`
(Postgres log, user analytics_writer); the four runs before it (09-28 .. 10-02) succeeded. Cause: core's
`brokerage_ddl._create_brokerage_views` drops and recreates `raw_broker.executions / executions_final /
executions_fly` on every db-init and `_grant_brokerage_privileges` re-grants only brokerage_writer, brokerage_reader,
bifrost and data_writer; trade_app_* come back through bifrost's default privileges. analytics_writer is in neither.
Read-only check before the fix: `has_table_privilege('analytics_writer','raw_broker.executions_final','SELECT')` = f.

| # | statement | object | owner after | reversible? | rollback |
|---|-----------|--------|-------------|-------------|----------|
| 1 | `GRANT SELECT ON raw_broker.executions_final TO analytics_writer` | view ACL | bifrost (unchanged) | yes | `REVOKE SELECT ON raw_broker.executions_final FROM analytics_writer` |

Listed under `prod` / `after` so `release.sh` prints it after each release until core keeps view grants across
the rebuild. Not tied to a release: it touches bifrost_golden_source only.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At -c "SET default_transaction_read_only=on;" -c "SELECT has_table_privilege('analytics_writer','raw_broker.executions_final','SELECT');"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-05-d2-executions-final-regrant.sql
verify:  the commit prints analytics_writer_select = t; then re-run the missed distill (Dagster: launch research_memory_distill_job once)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -c "REVOKE SELECT ON raw_broker.executions_final FROM analytics_writer;"
