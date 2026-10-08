---
id: 2026-10-07-td85-analytics-writer-create
envs: prod
when: after
done: prod
---
# TD-85: analytics_writer loses schema CREATE on ingest and brokerage

Not executed. Golden Source is one database, so the step runs once (filed under prod).

D13: Research writes `dw_stock`, `features`, `research`, and `journal`. It does not write
`raw_market` or `raw_broker`. Live ACLs still have `analytics_writer=UC` on both schemas
(CREATE + USAGE). `REVOKE CREATE` leaves USAGE, so SELECT keeps working.

`ops_jobs` CREATE is the same shape and is not required. `ops_jobs.ensure_month_partitions`
is SECURITY INVOKER. Research calls it as analytics_writer; the function creates partitions
in `features`, where analytics_writer already owns the parent tables. EXECUTE (granted to
PUBLIC) plus that ownership is enough. USAGE on `ops_jobs` stays.

Three `ops_jobs` tables also grant analytics_writer `arwd` (data_source_void,
symbol_source_void, watchlist_cache). Research only SELECTs watchlist_cache. The step
revokes INSERT, UPDATE, and DELETE and leaves SELECT.

`market_reader` has `arwd` on `raw_market.ticker_related` and no CONNECT anywhere (no
workload uses the role). The step revokes the write bits and leaves SELECT.

| # | statement | object | reversible? | rollback |
|---|-----------|--------|-------------|----------|
| 1 | `REVOKE CREATE` | schema raw_market | yes | `GRANT CREATE` |
| 2 | `REVOKE CREATE` | schema raw_broker | yes | `GRANT CREATE` |
| 3 | `REVOKE CREATE` | schema ops_jobs | yes | `GRANT CREATE` |
| 4 | `REVOKE INSERT, UPDATE, DELETE` | three ops_jobs tables | yes | grant those three back |
| 5 | `REVOKE INSERT, UPDATE, DELETE` | raw_market.ticker_related from market_reader | yes | grant them back |

No DROP and no table-emptying statement in the forward or rollback files.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-analytics-writer-create-check.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-analytics-writer-create-revoke.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-analytics-writer-create-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-analytics-writer-create-rollback.sql

After it, `k8s/data/role-matrix/check_role_matrix.py --via kubectl` should print `0 difference(s)`.
Until it runs, that check exits 1 on the five cells above, and `release-check.sh <env> before` fails with it.
