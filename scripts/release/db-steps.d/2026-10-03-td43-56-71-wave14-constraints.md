---
id: 2026-10-03-td43-56-71-wave14-constraints
envs: dev stg prod
when: before
done:
---
# TD-43 / TD-56 / TD-71: Wave 14 constraints (core 0.41.0)

core 0.41.0's db-init (`_ensure_tables` -> `migrate_wave14_trade_invariants`) applies this itself on the
deliver: plan and review FKs -> ON DELETE RESTRICT, CHECK `strategy_plan_filled_instance_ck`,
`category_id` int4 -> bigint on `preference_position_category_tags` and `watchlist`, UNIQUE
`preference_position_categories_name_uq`, CHECK `strategy_opportunity_scope_type_ck`. It is idempotent and
catalog-guarded. Rows that break a CHECK do not fail db-init -- the CHECK stays NOT VALID with a WARNING, and a
duplicated name skips the UNIQUE -- so this step is the gate: **every `*_violations` count must be 0** before the
deliver. Read 2026-10-03: 0 on DEV, STG and PROD for every count.

Commands run from the `bifrost-trade-infra` checkout (the SQL files are under `scripts/release/db-steps.d/sql/`),
with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`. `commit` is optional: it applies the same statements before the
deliver (db-init then finds nothing to do); skip it and db-init applies them. Either way, mark the step done once
the dry-run reads 0. Statements: `sql/2026-10-03-wave14-trade-invariants.sql` (generated from core's
`wave14_statements()`). Locks: each ALTER holds a short ACCESS EXCLUSIVE lock on a table of <= 26 rows.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-trade-invariants.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-verify.sql
rollback (only with core rolled back below 0.41.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-trade-invariants.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-verify.sql
rollback (only with core rolled back below 0.41.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-trade-invariants.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-verify.sql
rollback (only with core rolled back below 0.41.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-wave14-rollback.sql
