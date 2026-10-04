---
id: 2026-10-04-td85-trade-app-roles
envs: dev stg prod
when: before
done: dev stg prod
---
# TD-85 D1: the Trade runtime gets its own role per env, trade_app_<env>

Owner-approved 2026-10-04 (`/stocks/REQUEST-trade-runtime-db-role-plan-2026-10-04.md`, "Owner 批复": D1–D8
as recommended). Today every Trade pod of every env signs in as `bifrost`, which owns all three Trade
databases and most of Golden Source: a DEV pod can write PROD's tables and create objects in Golden Source.
After this step and `scripts/trade-app-role.sh switch <env>`, the api-* and daemon pods of an env sign in as
`trade_app_<env>`; `bifrost` stays the owner and only db-init uses it (Secret `bifrost-<env>-db-owner`).

**What the role may do = what the runtime does** (measured from core 0.45.0 `0f7026e`, api 0.7.3 `8e52001`,
worker 0.2.4 `1388553`; the verify files list each object / privilege with the code that needs it):

| database | trade_app_<env> |
|----------|-----------------|
| its own `bifrost_<env>` | CONNECT; `public` USAGE (no CREATE), every table S/I/U/D, every sequence USAGE/SELECT/UPDATE; `brokerage` / `market` SELECT; FDW user mapping → `brokerage_reader` (read-only), copied server-side from bifrost's mapping |
| the other two Trade databases | nothing (CONNECT through PUBLIC until the public-revoke step) |
| `bifrost_golden_source` | CONNECT; `raw_broker` USAGE, its 10 tables + 3 views S/I/U/D, `open_orders` TRUNCATE, its 6 sequences USAGE/SELECT/UPDATE |
| Golden Source `features` `research` `journal` `dw_stock` `raw_market` `ops_jobs` `ops_dagster` `ops_dbt` | nothing |
| `ops_feedback` | nothing by default (see below) |

No password is in any file. The role is created without one; `scripts/trade-app-role.sh password <env>` sends
a SCRAM verifier computed locally. Default privileges cover what db-init (bifrost) creates later in `public`,
`brokerage`, `market`, `raw_broker`, and what the Owner re-imports as postgres into `brokerage` / `market`.
Role-level settings are copied from bifrost (`statement_timeout=2s`, `lock_timeout=5s`,
`idle_in_transaction_session_timeout=15s` today).

`ops_feedback`: the plan's §2.2 lists DML for it, but no Trade code reaches `ops_feedback` with these
credentials — api-research uses `ANALYTICS_PG_*` (analytics_writer) up to api 0.7.4 and `FEEDBACK_PG_*`
(`feedback_writer`, TD-49 D4, S/I/U without DELETE per decision C) from 0.7.5. So the default run grants
nothing there; `sql/2026-10-04-td85-trade-app-ops-feedback.sql` (S/I/U, same as feedback_writer) is ready if
the Owner wants the plan's §3 repoint instead.

## Statements (all as postgres; lane executed none)

`sql/2026-10-04-td85-trade-app-gs.sql` — once, in `bifrost_golden_source`:

| # | statement | object | owner after | reversible? | rollback (`sql/…-trade-app-gs-rollback.sql`) |
|---|-----------|--------|-------------|-------------|----------------------------------------------|
| 1 | `CREATE ROLE trade_app_{dev,stg,prod} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` (only if absent), `COMMENT ON ROLE` | 3 cluster roles, no password, no membership | — | yes | `DROP ROLE` (last, after every Trade rollback) |
| 2 | `ALTER ROLE trade_app_<env> SET <name> = <value>` for each of bifrost's role settings | role settings | — | yes | goes with the role |
| 3 | `GRANT CONNECT ON DATABASE bifrost_golden_source TO` the 3 | database ACL | bifrost (db owner) | yes | `REVOKE ALL ON DATABASE bifrost_golden_source FROM …` |
| 4 | `GRANT USAGE ON SCHEMA raw_broker TO` the 3 | schema ACL | bifrost | yes | `REVOKE ALL ON SCHEMA raw_broker FROM …` |
| 5 | `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw_broker TO` the 3 | 10 tables + 3 views | bifrost | yes | `REVOKE ALL ON ALL TABLES IN SCHEMA raw_broker FROM …` |
| 6 | `GRANT TRUNCATE ON raw_broker.open_orders TO` the 3 | 1 table | bifrost | yes | (in 5) |
| 7 | `GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA raw_broker TO` the 3 | 6 sequences | bifrost | yes | `REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_broker FROM …` |
| 8 | `ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker GRANT S/I/U/D ON TABLES` / `GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO` the 3 | 2 `pg_default_acl` rows | bifrost | yes | `… REVOKE ALL ON TABLES / SEQUENCES FROM …` |

`sql/2026-10-04-td85-trade-app-trade.sql -v env=<env>` — once per env, in `bifrost_<env>` (refuses another database):

| # | statement | object | owner after | reversible? | rollback (`sql/…-trade-app-trade-rollback.sql -v env=<env>`) |
|---|-----------|--------|-------------|-------------|------------------------------------------------------------|
| 9 | `GRANT CONNECT ON DATABASE bifrost_<env> TO trade_app_<env>` | database ACL | bifrost | yes | `REVOKE ALL ON DATABASE bifrost_<env> FROM trade_app_<env>` |
| 10 | `GRANT USAGE ON SCHEMA public, brokerage, market TO trade_app_<env>` | 3 schema ACLs | postgres (public, brokerage), bifrost (market; DEV: postgres until D8) | yes | `REVOKE ALL ON SCHEMA public, brokerage, market FROM …` |
| 11 | `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO trade_app_<env>` | 19 tables + 3 views | bifrost | yes | `REVOKE ALL ON ALL TABLES IN SCHEMA public, brokerage, market FROM …` |
| 12 | `GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO trade_app_<env>` | 14 sequences | bifrost | yes | `REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM …` |
| 13 | `GRANT SELECT ON ALL TABLES IN SCHEMA brokerage, market TO trade_app_<env>` | 13 foreign tables + 7 views | bifrost (DEV: postgres until D8) | yes | (in 11) |
| 14 | `ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA public GRANT S/I/U/D ON TABLES` + `GRANT USAGE, SELECT, UPDATE ON SEQUENCES`; `FOR ROLE bifrost IN SCHEMA brokerage, market GRANT SELECT ON TABLES`; `FOR ROLE postgres IN SCHEMA brokerage, market GRANT SELECT ON TABLES` | 6 `pg_default_acl` rows | — | yes | the same with `REVOKE ALL … FROM` |
| 15 | `CREATE USER MAPPING FOR trade_app_<env> SERVER golden_source_server OPTIONS (user 'brokerage_reader', password …)` — built in a DO block from bifrost's mapping (asserts it is brokerage_reader), errors re-raised without the statement text | FDW user mapping | server owner postgres | yes | `DROP USER MAPPING IF EXISTS FOR trade_app_<env> SERVER golden_source_server` |
| 16 | `ALTER ROLE trade_app_<env> PASSWORD 'SCRAM-SHA-256$4096:…'` — sent by `scripts/trade-app-role.sh password <env>`, never in a file | role password | — | yes | `ALTER ROLE … PASSWORD NULL`, or `DROP ROLE` |

No data is read or changed; each file is one transaction, `lock_timeout` 10s, catalog rows only; a second
run changes nothing (the user mapping is left as is when present).

Rehearsed 2026-10-04 on a throwaway docker postgres:17 built from read-only `pg_dump --schema-only` of
bifrost_dev, bifrost_prod (also restored as bifrost_stg) and bifrost_golden_source (user mappings stripped in
the pod), roles / memberships / database ACLs / role settings mirrored, pg_hba as CNPG (scram over TCP),
invented rows: D8, both files, `password`, the verify files (74/74 Trade, 31/31 Golden Source per role, every
"nothing more" count 0); core 0.45.0 as `trade_app_<env>` with the config's `user: bifrost` lines and the
switched Secret's env — trades (create / get / list / patch / delete), executions (insert, update with
FOR UPDATE, commission upsert, Flex cash upsert, delete), attribution (replace splits, patch), accounts sync,
reads through the FDW views, performance stats and instance summary, and the daemon sink (open orders
TRUNCATE + INSERT, TWS execution upsert, quote upsert, accounts snapshot, settings, quotes via FDW): 69/69
per env; CREATE in brokerage / raw_broker / GS public, CREATE SCHEMA, TRUNCATE outside open_orders, ALTER,
SET ROLE bifrost, any read or write in the eight other GS schemas, ops_feedback, and the other envs' tables:
all `42501`. db-init (api 0.7.3 `run_db_refresh_schema.py`) with the db-owner override: as bifrost, ok;
without it: `must be owner of table settings`. A table / sequence / foreign table bifrost or postgres
created afterwards: usable by trade_app at once. Rollback chain, then commit again (roles first, D8 after):
ok; the state after rollback matches live except for explicit-equivalent ACL entries.

## Owner checklist (in order; DEV → STG → PROD; each env stable before the next)

1. Dry-run (read-only, any env; an agent may run it): the state the plan measured.
2. **Roles + grants**: the Golden Source file once, then the Trade file in each of the three databases.
   Then the verify files (read-only).
3. **Passwords**: `scripts/trade-app-role.sh ensure`, then `scripts/trade-app-role.sh password dev stg prod`.
4. **db-init's Secret**: `scripts/trade-app-role.sh owner-secret dev stg prod` (while the env is still on bifrost).
5. **Infra**: the TD-85 commit (db-init's explicit `PGUSER` / `GOLDEN_SOURCE_USER` / passwords from
   `bifrost-<env>-db-owner`) on main. STG / PROD: the next deliver's Argo sync; a finished db-init Job of the
   old template stays until its TTL and the next one comes from git. DEV: the overlay is applied by the DEV
   release (`kubectl apply -k k8s/overlays/dev`, after deleting a finished `db-init-dev` Job).
6. **Switch** (not a release; run `release.sh window` first so it does not overlap one):
   `scripts/trade-app-role.sh switch <env>` — refuses without the role password, a local value that signs in
   to both databases, a working `bifrost-<env>-db-owner`, the db-init override in this checkout, or (PROD)
   during the US regular session. Then `scripts/trade-app-role.sh check <env>` and the verify list below.
7. `release.sh db-done <env> 2026-10-04-td85-trade-app-roles` per env after 2–4.
8. After all three envs ran a full trading day on trade_app: the after-step `2026-10-04-td85-public-revoke`.

Rollback of one env: `scripts/trade-app-role.sh rollback <env>` (one Secret patch back to bifrost + restart; the
role and its grants can stay). Full rollback: every env `rollback`, the public-revoke rollback if it ran,
`…-trade-app-trade-rollback.sql` in each Trade database, then `…-trade-app-gs-rollback.sql` (refuses while a
`trade_app_*` session exists).

## dev
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
commit (once, Golden Source): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-gs.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-trade.sql
password: scripts/trade-app-role.sh ensure && scripts/trade-app-role.sh password dev
owner:   scripts/trade-app-role.sh owner-secret dev
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v env=dev -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-gs.sql
switch:  scripts/trade-app-role.sh switch dev && scripts/trade-app-role.sh check dev
after:   GET http://192.168.10.73:30882/api/health on each domain; `check dev` shows only trade_app_dev sessions on bifrost_dev;
         no "permission denied" in kubectl -n bifrost-dev logs deploy/api-account / api-monitor / api-market / api-research / daemon;
         one write per desk route family on DEV (a watchlist row, a position category) and remove it again
rollback: scripts/trade-app-role.sh rollback dev

## stg
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
commit (Golden Source, only if the dry-run of bifrost_golden_source shows no trade_app_* role): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-gs.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-trade.sql
password: scripts/trade-app-role.sh password stg
owner:   scripts/trade-app-role.sh owner-secret stg
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v env=stg -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
switch:  scripts/trade-app-role.sh switch stg && scripts/trade-app-role.sh check stg
after:   scripts/release/release-check.sh stg after; the DEV checks against :30880
rollback: scripts/trade-app-role.sh rollback stg

## prod
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dryrun.sql
commit (Golden Source, only if not done yet): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-gs.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-trade.sql
password: scripts/trade-app-role.sh password prod
owner:   scripts/trade-app-role.sh owner-secret prod
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-verify-trade.sql
switch (after the US close): scripts/trade-app-role.sh switch prod && scripts/trade-app-role.sh check prod
after:   scripts/release/release-check.sh prod after; over the next session raw_broker.positions / account n_tup_upd keep growing
         (SELECT relname, n_tup_upd FROM pg_stat_user_tables WHERE schemaname = 'raw_broker' in bifrost_golden_source, read-only),
         `check prod` shows trade_app_prod for the Trade pods' sessions, no "permission denied" in the daemon / api logs
rollback: scripts/trade-app-role.sh rollback prod
          full: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-trade-rollback.sql
          (each env), then kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-trade-app-gs-rollback.sql
