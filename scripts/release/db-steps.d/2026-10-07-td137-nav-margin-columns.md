---
id: 2026-10-07-td137-nav-margin-columns
envs: dev stg prod
when: before
done:
---
# TD-137: account_nav_daily margin columns (core 0.52.0)

Owner approved the three statements on 2026-10-06 ("批准 TD-137 三条 DDL，明天收盘前发"). core 0.52.0's
capture INSERTs `cushion`, `excess_liquidity` and `maint_margin_req`; an image on 0.52.0 against a database
without them fails the 16:20 ET capture and loses that session. db-init would add them too, but a finished
db-init Job lingers a day and Argo leaves it alone (TD-68), so apply them **before** the deliver in every
env, and in any case before 16:20 ET. Avoid 20:05–20:40 UTC.

Statements: `sql/2026-10-07-td137-nav-margin-columns.sql` (copied from core `snapshot_ddl.py:78-81`).
Nullable, no default: a catalog-only change under a brief ACCESS EXCLUSIVE lock; no rewrite, no backfill, no
grants touched. Idempotent (`IF NOT EXISTS`). Verify must list the three columns, double precision, nullable.

Commands run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`.
No rollback step: an extra nullable column is harmless to core < 0.52.0, so a core rollback leaves them.

## dev
commit: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns.sql
verify: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns-verify.sql

## stg
commit: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns.sql
verify: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns-verify.sql

## prod
commit: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns.sql
verify: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-07-td137-nav-margin-columns-verify.sql
