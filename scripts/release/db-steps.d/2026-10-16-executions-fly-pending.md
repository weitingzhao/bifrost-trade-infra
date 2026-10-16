---
id: 2026-10-16-executions-fly-pending
envs: dev stg prod
when: after
done:
---
# core 0.61.0: brokerage.executions_fly holds the TWS fills Flex has not confirmed (by exec_id)

`source_scope=on_the_fly` reads each env's `brokerage.executions_fly`. Until core 0.61.0 it counted a TWS fill as
confirmed when Flex had any row for the same account and contract, so a new fill on a contract traded before never
showed (2026-10-16: an NVDA option fill missing while IB's position had moved), and it held 19 March–May rows Flex has
under another exec_id. The new rule: pending while Flex has no row with the fill's exec_id **and** its trading day
(US/Eastern) is after the last day Flex covers for its account; never a BAG, never a row without an account.

**One statement per env**: `CREATE OR REPLACE VIEW brokerage.executions_fly AS …`, exactly core 0.61.0's
`_create_brokerage_views(env=True)` statement (generated with `view_statements('brokerage')`), as `bifrost`, the view
owner in all three envs (read 2026-10-16), `lock_timeout` 5s. Same columns, so the grants and the views that read it
stay; no data changes. The same SQL serves dev, stg and prod.

**Why a DB step**: db-init never rebuilds the env views (its FDW step stops at `must be owner of foreign server`, see
`2026-10-08-r4-drop-compat`). Golden Source's own `raw_broker.executions_fly` has no reader and is rebuilt by the next
db-init run with core 0.61.0; this step does not touch Golden Source.

**Order (`when: after`)**: either order is safe. The Ledger (frontend after core 0.61.0) applies the same rule to what
it reads, so it shows the right pending fills before and after this step; the Performance page's on-the-fly mode is the
other reader and only gets the corrected set.

**Rehearsed 2026-10-16** on a local Postgres 16 with the 0.60.1 env views owned by `bifrost`: verify `f|t` (old) →
dry run, still old → commit, verify `t|f` (new) → rollback, verify `f|t`. Read-only on Golden Source the new rule held
exactly that day's two fills; PROD's view held 21 rows under the old one.

Verify prints `new_rule | old_rule | pending_rows`; after the commit it must read `t | f | <n>`.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-16-executions-fly-pending-rollback.sql
