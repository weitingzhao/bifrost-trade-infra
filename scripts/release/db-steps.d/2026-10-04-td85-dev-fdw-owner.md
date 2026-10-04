---
id: 2026-10-04-td85-dev-fdw-owner
envs: dev
when: before
done:
---
# TD-85 D8: DEV's brokerage / market FDW objects owned by bifrost, as in STG and PROD

Owner-approved 2026-10-04 (plan "Owner 批复" D8: each object named before it runs). In DEV the 20 FDW objects
and schema `market` are owned by `postgres`; in STG / PROD by `bifrost` (schema `brokerage` stays postgres's
everywhere). A query through a view runs the FDW as the view owner: DEV's views read Golden Source as
`brokerage_writer` (the postgres mapping, can write `raw_broker`), STG / PROD's as `brokerage_reader`
(read-only). After this step DEV's do too. Independent of the roles step (either order rehearsed).

## Statements (`sql/2026-10-04-td85-dev-fdw-owner.sql`, one transaction, as postgres, in bifrost_dev)

Each statement runs only while the object is still postgres's, so a second run changes nothing.

| # | statement | object | owner after | reversible? | rollback (`sql/…-dev-fdw-owner-rollback.sql`) |
|---|-----------|--------|-------------|-------------|-----------------------------------------------|
| 1 | `ALTER FOREIGN TABLE brokerage.account OWNER TO bifrost` | foreign table | bifrost | yes | `OWNER TO postgres` + `GRANT SELECT … TO bifrost` |
| 2 | `ALTER FOREIGN TABLE brokerage.commissions OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 3 | `ALTER FOREIGN TABLE brokerage.contract_quote_live OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 4 | `ALTER FOREIGN TABLE brokerage.executions_raw_flex OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 5 | `ALTER FOREIGN TABLE brokerage.executions_raw_journal OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 6 | `ALTER FOREIGN TABLE brokerage.executions_raw_tws OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 7 | `ALTER FOREIGN TABLE brokerage.open_orders OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 8 | `ALTER FOREIGN TABLE brokerage.positions OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 9 | `ALTER FOREIGN TABLE brokerage.settings_flex OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 10 | `ALTER FOREIGN TABLE brokerage.transactions OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 11 | `ALTER FOREIGN TABLE market.ticker OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 12 | `ALTER FOREIGN TABLE market.ticker_related OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 13 | `ALTER FOREIGN TABLE market.us_market_holiday OWNER TO bifrost` | foreign table | bifrost | yes | same |
| 14 | `ALTER VIEW brokerage.executions OWNER TO bifrost` | view | bifrost | yes | same |
| 15 | `ALTER VIEW brokerage.executions_final OWNER TO bifrost` | view | bifrost | yes | same |
| 16 | `ALTER VIEW brokerage.executions_fly OWNER TO bifrost` | view | bifrost | yes | same |
| 17 | `ALTER VIEW brokerage.executions_tws OWNER TO bifrost` | view | bifrost | yes | same |
| 18 | `ALTER VIEW brokerage.instance_allocations OWNER TO bifrost` | view (R3 compatibility) | bifrost | yes | same |
| 19 | `ALTER VIEW brokerage.trade_fill_splits OWNER TO bifrost` | view | bifrost | yes | same |
| 20 | `ALTER VIEW market.v_us_equity_universe OWNER TO bifrost` | view | bifrost | yes | same |
| 21 | `ALTER SCHEMA market OWNER TO bifrost` | schema (STG / PROD: bifrost) | bifrost | yes | `ALTER SCHEMA market OWNER TO postgres` + `GRANT USAGE ON SCHEMA market TO bifrost` |

ACL effect: each object's `{postgres=arwdDxtm/postgres,bifrost=r/postgres}` becomes `{bifrost=arwdDxtm/bifrost}`
(the owner change moves postgres's rights to bifrost); `market`'s `{postgres=UC/postgres,bifrost=U/postgres}`
becomes `{bifrost=UC/bifrost}` — both as in STG / PROD. The rollback restores the measured DEV ACLs exactly
(rehearsed). bifrost already has a `golden_source_server` mapping to `brokerage_reader` in DEV.

Rehearsed 2026-10-04 (throwaway postgres:17 from the read-only bifrost_dev schema dump): commit, second run
(0 statements), views read through the FDW as bifrost and as trade_app_dev, core 0.45.0 smoke as trade_app_dev
69/69, rollback (ACLs equal to live DEV), commit again after the roles step: ok.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
         (section "D8": the 20 objects, all postgres; schemas: market postgres)
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dev-fdw-owner.sql
verify:  the dry-run again: 20 objects and schema market owned by bifrost; then DEV /health and one GET of
         http://192.168.10.73:30882/api/portfolio executions (a read through the brokerage views)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dev-fdw-owner-rollback.sql
