---
id: 2026-10-10-td74-drop-settings-flex-columns
envs: dev stg prod
when: after
done:
---
# TD-74: drop `settings.flex_default_range_days` / `settings.flex_init_range_days` (Trade dev / stg / prod)

The Flex Query plugin keeps its range in Golden Source `ops_jobs.flex_settings` since 0.7.0 (live 2026-10-03,
row seeded 19:15 UTC as 30 / 270); the three Trade copies are dead weight that a partial fan-out could make
diverge (TD-74). Core has not read them since 0.39.0, and the TD-74 core commit takes them out of the DDL
(`_ensure_tables` neither creates them on a fresh database nor adds them back; wave 13's NOT NULL step that
named them is gone).

**Gate: one week of Flex >= 0.7.0 on Golden Source, i.e. not before 2026-10-10** (Owner: "observe one week").
Order: deliver the core that carries the TD-74 commit, then this step in each env (`when: after`). Rehearsed
2026-10-04 in a throwaway postgres:17 built from a read-only `pg_dump --schema-only` of bifrost_dev: core
0.45.0 (origin/main) and the TD-74 core both run `_ensure_tables` twice on the dropped schema without error
and without adding the columns back, so the order is not load-bearing -- it is "after" so a fresh database
built in between does not grow them again.

Read 2026-10-04 (read-only):

| env | columns | values (id 1) | rows | dependents (views / indexes / constraints) | column grants | owner |
|-----|---------|---------------|------|-----|-----|-----|
| dev  | int4 NOT NULL, defaults 30 / 360 | 30 / 270 | 1 | none | none | bifrost |
| stg  | same | 30 / 270 | 1 | none | none | bifrost |
| prod | same | 30 / 270 | 1 | none | none | bifrost |

Golden Source `ops_jobs.flex_settings`: one row, 30 / 270. No foreign table, view or other database reads
`public.settings` (the Trade `brokerage.settings_flex` foreign table is Golden Source `raw_broker.settings_flex`,
not this table).

Readers, all repos at origin/main 2026-10-04: core -- none (DDL and wave 13 only, both removed by TD-74);
api, worker, research, platform, market-data plugin, IB gateway plugin -- none; frontend and platform console --
only the Flex plugin's own summary (`range_days`), not the Trade column. **Flex 0.8.1** still has a fallback
(`config_rw.read_trade_flex_range_days`) that reads them only while the Golden Source row is missing, inside
try/except: after the drop that fallback returns None and the plugin's defaults 30 / **360** apply (rehearsed),
so the Golden Source row must stay; the fallback can go in the next Flex release.

Steps per env (commands below, run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`):

0. Once, before the first env -- the gate (read-only):
   - Flex images: `kubectl -n plugin-flex-query get deploy -o 'custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'` -- both >= 0.7.0 (quoted: zsh reads `[0]` as a glob).
   - Golden Source row: `kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -c "SET default_transaction_read_only=on;" -c "SELECT * FROM ops_jobs.flex_settings;"` -- one row, 30 / 270.
   - A week of Flex jobs on it: `kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -c "SET default_transaction_read_only=on;" -c "SELECT kind, status, count(*), max(finished_at) FROM ops_jobs.job_flex_ingest WHERE created_at >= '2026-10-05' GROUP BY 1, 2 ORDER BY 1, 2;" -c "SELECT pod, version, seen_at, jobs_done, jobs_failed, last_error_category FROM ops_jobs.flex_worker_heartbeat;"` -- jobs done on every US trading day since 10-05, none failed for a settings / range reason.
1. `dry-run` (read-only): both columns present, the values, 1 row, 0 dependents, 0 column grants.
2. `export`: the row's values to `~/bifrost-backups/trade-settings/td74-settings-flex/<db>.csv` (outside any repo),
   then `shasum -a 256 *.csv > SHA256SUMS` in that folder. Must print `1,30,270` (or whatever the dry-run showed).
3. `commit`: `sql/2026-10-10-td74-drop-settings-flex-columns.sql`, one transaction with its own BEGIN / COMMIT:
   ACCESS EXCLUSIVE on `settings` (`lock_timeout` 5s -- rerun if it times out; one row, the lock is momentary),
   prints the values it drops (NOTICE), refuses with RAISE if anything depends on the columns, then
   `DROP COLUMN IF EXISTS` both. Idempotent (rehearsed twice in a row).
4. `verify`: the first query returns 0 rows; `settings_rows` = 1; the column list is the other seven.
5. `rollback` (only if a reader comes back -- Flex < 0.7.0): `ADD COLUMN IF NOT EXISTS` both as they were
   (int4 NOT NULL, defaults 30 / 360) and the exported values back on id 1, from psql variables. Idempotent.
   The columns come back at the end of the table, not in their old position (nothing reads `settings` by position).

Ordering note: the Ops data clone (platform `data_clone.go`, `pg_dump --data-only` -> `COPY settings (col, ...)`)
from an env that still has the columns into one that has dropped them fails on `settings`. Run the three envs in
one sitting, or do not clone between envs while they differ.

## dev
gate:    not before 2026-10-10 (one week of Flex >= 0.7.0 on Golden Source), after step 0 of this file passed and the core carrying the TD-74 commit is delivered to dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-precheck.sql
export:  mkdir -p ~/bifrost-backups/trade-settings/td74-settings-flex && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -q -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -c "COPY (SELECT id, flex_default_range_days, flex_init_range_days FROM public.settings ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_dev.csv && cat ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_dev.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-drop-settings-flex-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-verify.sql
rollback (values from the export CSV): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v default_days=30 -v init_days=270 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-rollback.sql

## stg
gate:    not before 2026-10-10 (one week of Flex >= 0.7.0 on Golden Source), after step 0 of this file passed and the core carrying the TD-74 commit is delivered to stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-precheck.sql
export:  mkdir -p ~/bifrost-backups/trade-settings/td74-settings-flex && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -q -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -c "COPY (SELECT id, flex_default_range_days, flex_init_range_days FROM public.settings ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_stg.csv && cat ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_stg.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-drop-settings-flex-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-verify.sql
rollback (values from the export CSV): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v default_days=30 -v init_days=270 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-rollback.sql

## prod
gate:    not before 2026-10-10 (one week of Flex >= 0.7.0 on Golden Source), after step 0 of this file passed and the core carrying the TD-74 commit is delivered to prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-precheck.sql
export:  mkdir -p ~/bifrost-backups/trade-settings/td74-settings-flex && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -q -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -c "COPY (SELECT id, flex_default_range_days, flex_init_range_days FROM public.settings ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_prod.csv && cat ~/bifrost-backups/trade-settings/td74-settings-flex/bifrost_prod.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-drop-settings-flex-columns.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-verify.sql
rollback (values from the export CSV): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v default_days=30 -v init_days=270 -f - < scripts/release/db-steps.d/sql/2026-10-10-td74-rollback.sql
