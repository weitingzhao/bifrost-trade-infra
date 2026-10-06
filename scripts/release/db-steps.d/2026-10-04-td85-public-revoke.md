---
id: 2026-10-04-td85-public-revoke
envs: dev stg prod
when: after
done: dev stg prod
---
# TD-85 D4: PUBLIC loses CONNECT on the Trade databases and CREATE in their public schema

Owner-approved 2026-10-04 (plan "Owner 批复" D4). **Run only after all three envs sign in as trade_app_<env>
and ran a full trading day** (`scripts/trade-app-role.sh check dev|stg|prod`), env by env. Until then
any login role — including the other envs' `trade_app_*` — may connect to every Trade database and create
tables in its `public` schema (table privileges stay zero; the verify file's section 4 shows it).

Golden Source is not touched here (its PUBLIC CONNECT involves data_writer / market_reader: D6).

## Statements (`sql/2026-10-04-td85-public-revoke.sql -v env=<env>`, one transaction, as postgres, in bifrost_<env>)

| # | statement | object | owner after | reversible? | rollback (`sql/…-public-revoke-rollback.sql -v env=<env>`) |
|---|-----------|--------|-------------|-------------|-------------------------------------------------------------|
| 1 | `GRANT CONNECT ON DATABASE bifrost_<env> TO trade_app_<env>, brokerage_reader` | database ACL (STG: brokerage_reader had it only through PUBLIC) | bifrost | yes | left in place (same rights as before) |
| 2 | `GRANT USAGE, CREATE ON SCHEMA public TO bifrost` | schema ACL (DEV: bifrost had CREATE only through PUBLIC; STG / PROD: no-op) | postgres | yes | left in place |
| 3 | `REVOKE CONNECT ON DATABASE bifrost_<env> FROM PUBLIC` | database ACL (`=Tc` → `=T`; STG's NULL ACL is materialized) | bifrost | yes | `GRANT CONNECT ON DATABASE bifrost_<env> TO PUBLIC` |
| 4 | `REVOKE CREATE ON SCHEMA public FROM PUBLIC` | schema ACL (`=UC` → `=U`) | postgres | yes | `GRANT CREATE ON SCHEMA public TO PUBLIC` |

Who loses CONNECT (the dry-run's `connect_only_via_public`, read-only 2026-10-04): `brokerage_writer`,
`data_writer`, `market_reader`, `streaming_replica` (replication does not use database CONNECT), and the other
envs' `trade_app_*`. None of them has a session on a Trade database today (`pg_stat_activity` 2026-10-04: only
bifrost and postgres). `data_writer` has SELECT on `public.watchlist` in STG / PROD: when D6 moves market-data
to data_writer, it needs an explicit CONNECT there. `analytics_writer` keeps CONNECT through its bifrost
membership (D2 removes that).

Statement 2 matters: without it DEV's next db-init fails at its first `CREATE TABLE IF NOT EXISTS` with
`permission denied for schema public` (rehearsed as a negative control).

Rehearsed 2026-10-04 (throwaway postgres:17, after the roles step): all three envs, second run (no change);
core 0.45.0 smoke 70/70 per env (optional ops_feedback file applied) with CREATE in public now `42501` and CONNECT to the other two Trade databases
`permission denied for database`; db-init as bifrost in DEV and PROD: ok; rollback: ok.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
         (first: scripts/trade-app-role.sh check dev / stg / prod all show PGUSER trade_app_<env>)
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v env=dev -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
         (section 4: create_via_public f, other roles' connect f); the next DEV db-init completes
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v env=stg -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-public-revoke-rollback.sql
