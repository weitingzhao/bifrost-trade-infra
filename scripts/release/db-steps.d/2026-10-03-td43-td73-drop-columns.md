---
id: 2026-10-03-td43-td73-drop-columns
envs: dev stg prod
when: after
done:
---
# TD-43 / TD-73: drop `strategy_plan.filled_at`, `strategy_instance.notes`, `trade_review.note` (core 0.43.0)

Owner-approved 2026-10-03 (`REQUEST-td-ddl-batch-plans-2026-10-03.md`: TD-43 option B step 3/4, TD-73 option A,
"the next DDL wave"). core 0.43.0 / api 0.7.1 never name these columns and work with or without them, and
`_ensure_tables` neither creates them on a fresh database nor adds them back -- so the deliver goes first and this
step runs **after** it, in each env. **Run it only once core >= 0.43.0 is live in that env**: core 0.42.0 still
SELECTs `strategy_instance.notes` and `trade_review.note` and would fail without them.

Read 2026-10-03 (read-only, `count(col)` per column):

| env | `strategy_plan.filled_at` non-null / plans | `strategy_instance.notes` non-null / trades | `trade_review.note` non-null / reviews | filled plans | dependent views / indexes / constraints |
|-----|-----|-----|-----|-----|-----|
| dev  | 0 / 3 | 0 / 89 | 0 / 0 | 0 | none |
| stg  | 0 / 0 | 0 / 74 | 0 / 0 | 0 | none |
| prod | 0 / 0 | 0 / 89 | 0 / 0 | 0 | none |

Nothing is lost: every value is null, and `filled_at` has meant the linked instance's `opened_at` since core 0.41.0
(reads join it). Tables are owned by `bifrost`; the commands run as `postgres`.

- `dry-run` (read-only): whether each column is still present, its non-null count (**all three must be 0**), filled
  plans, and anything depending on the columns (must be 0 rows). It reads cleanly after the drop too.
- `commit`: `sql/2026-10-03-td43-td73-drop-columns.sql`, one transaction with its own BEGIN / COMMIT (no `-1`): takes
  ACCESS EXCLUSIVE on the three tables (`lock_timeout` 5s -- rerun if it times out), **refuses with RAISE and drops
  nothing** if any of the three columns holds a non-null value, then `DROP COLUMN IF EXISTS` all three. Idempotent.
  Tables are 0-89 rows, so the lock is momentary.
- `verify`: 0 rows for the three columns; filled plans still read `filled_at` through the join.
- `rollback` (only with core rolled back below 0.43.0): `ADD COLUMN IF NOT EXISTS` all three, and `filled_at` backfilled
  from the linked instance's `opened_at` for filled plans (exact; `notes` / `note` were empty when dropped).

Ordering note: Ops data clone (platform `data_clone.go`, `pg_dump --data-only` -> `COPY tbl (col, ...)`) from an env that
still has a column into one that has dropped it fails on that table. Run the three envs in one sitting, or do not run a
selective clone of `strategy_*` / `trade_review` across envs while they differ. (Clone into an env that still has the
columns from one that has dropped them is fine: the columns stay null.)

Commands run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-drop-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-verify.sql
rollback (only with core rolled back below 0.43.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-drop-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-verify.sql
rollback (only with core rolled back below 0.43.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-precheck.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-drop-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-verify.sql
rollback (only with core rolled back below 0.43.0): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td43-td73-rollback.sql
