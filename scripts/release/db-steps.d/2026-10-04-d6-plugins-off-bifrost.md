---
id: 2026-10-04-d6-plugins-off-bifrost
envs: prod
when: after
done: prod
---
# TD-85 D6: the two Ops plugins stop signing in as bifrost (Golden Source + bifrost_dev, bifrost_stg, bifrost_prod)

Owner-approved 2026-10-04 (`REQUEST-trade-runtime-db-role-plan-2026-10-04.md`, appendix C4 and "Owner 批复（附录 C）"):
**D6 = P1** — market-data uses the existing `data_writer` and becomes the owner of `raw_market` and of the market side
of `ops_jobs`; flex-query gets a new `flex_writer` that owns its four `ops_jobs` tables, has minimal `raw_broker`
DML and reads its Trade database read-only (own FDW user mapping). **M4** plugins may read what Research publishes
(read-only). **F3** no `executions_raw_tws` / `executions_raw_journal` for flex. **F5** `ops_jobs` owners split per
plugin. Listed under `prod` / `after` so `release.sh` prints it; it is not tied to a Trade release. After it, bifrost
is held only by db-init (`bifrost-<env>-db-owner`) and CNPG (`bifrost-postgres-app`).

## What the plugins connect as and touch (read-only, 2026-10-04 14:2x UTC; code at market-data b7f7fdb, flex f701de0, core 7e54e8d)

| | market-data | flex-query |
|---|---|---|
| workloads | `market-data-api` (1), `polygon-worker-options` (8), `polygon-worker-stocks` (3); 14 CronJobs (all suspended; Dagster fires the slots through the API); `job-wave8-schema-migrate` on every release | `flex-query-api` (1), `flex-query-worker` (1) |
| Secret (key names) | `market-data-secrets`: `polygon-api-key`, `postgres-host`, `postgres-password`, `write-token` | `flex-query-secrets`: `postgres-host`, `postgres-password`, `trade-pg-db`, `trade-pg-host`, `trade-pg-password` (+ `bifrost-flex-tokens`) |
| login today | ConfigMap `postgres.user: bifrost` + `POSTGRES_PASSWORD` (= bifrost's, D5 value) | ConfigMap `postgres` / `trade_postgres` / `golden_source` `user: bifrost` + both passwords (= bifrost's) |
| sessions (pg_stat_activity by pod IP) | 12, all `bifrost@bifrost_golden_source` | 1, `bifrost@bifrost_golden_source` (worker; Trade connections are short) |
| writes | `raw_market.*` (upserts, DELETE, `TRUNCATE ticker_type`, `corporate_action_id_seq`); `ops_jobs.job_ingest` (`FOR UPDATE SKIP LOCKED`), `queue_sample`, `coverage_sample`, `ingest_freshness`, `data_source_void`, `symbol_source_void`, `watchlist_cache` | `ops_jobs.job_flex_ingest`, `flex_ingest_freshness`, `flex_worker_heartbeat`, `flex_settings`; through core: `raw_broker.executions_raw_flex` (+ `commissions`) and `transactions` upserts (all rows `source=flex_trades`); `raw_broker.settings_flex` delete-all + insert |
| reads outside its schemas | `research.option_universe`, `research.option_pinned_contract`, `features.option_metric_{atm_iv,iv_percentile,max_pain,pcr}_daily`, `dw_stock.mart_sepa_fundamental_eval` (dbt table, rebuilt nightly) | `raw_broker.positions`; Trade `bifrost_dev` (Secret `trade-pg-db`; the API fell back to the ConfigMap's same name): `public.settings`, `brokerage.executions` (view), `brokerage.settings_flex` (foreign table) |
| DDL that needs ownership | migrate Job: `CREATE INDEX IF NOT EXISTS` on `option_open_interest` / `option_contract`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS ops_jobs.coverage_sample`, `ALTER TABLE ops_jobs.job_ingest SET (autovacuum…)`, `CREATE OR REPLACE VIEW`; trim 02:15 UTC: `ensure_*_partitions` / `drop_*_partitions_older_than`; doctor's runway checks `relowner = current_user` | `ensure_flex_ops_schema` on each process's first call: 8 × `ALTER TABLE … ADD COLUMN IF NOT EXISTS` + 2 × `CREATE TABLE IF NOT EXISTS` |

Catalog: `raw_market` 165 relations (19 tables, 7 partitioned parents, 135 partitions, 4 views) + 2 sequences, 391 + 17
indexes; `ops_jobs` 7 market + 4 flex tables, 3 sequences, 5 partition helpers (SECURITY INVOKER, PUBLIC EXECUTE);
both schemas and everything in them owned by bifrost. `data_writer` already holds `arwdDxtm` on all of `raw_market`
and `ops_jobs` (flex tables included), USAGE/CREATE on both schemas, and **extra**: `arwdD` on all 13 `raw_broker`
relations + 6 sequences, `arwdDxtm` on the four `features.option_metric_*` parents, SELECT on `public.watchlist` in
`bifrost_stg` / `bifrost_prod`. It has no USAGE on `research` / `features` / `dw_stock`, no role settings, no
explicit CONNECT (PUBLIC), no session. `flex_writer` does not exist.

## Statements

| # | file / statement | object | owner after | reversible? | rollback |
|---|------------------|--------|-------------|-------------|----------|
| M6 + F1 | `sql/…-d6-1-roles.sql`: `ALTER ROLE data_writer SET statement_timeout '2s'`, `lock_timeout '5s'`, `idle_in_transaction_session_timeout '15s'`; `CREATE ROLE flex_writer LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` (no password) + the same three settings; role comments | cluster roles | — | yes | `sql/…-d6-rollback-roles.sql` (`DROP ROLE flex_writer`, `ALTER ROLE data_writer RESET …`) |
| pw | `scripts/plugin-db-roles.sh password data_writer` / `password flex_writer`: `ALTER ROLE … PASSWORD '<SCRAM verifier>'` computed locally, sent on stdin | role passwords | — | yes (set again) | no consumer of data_writer's old password exists (0 sessions) |
| M4 + F2a + F3 | `sql/…-d6-2-grants-gs.sql` (additive): data_writer `CONNECT, TEMPORARY` on the database; `USAGE` on `research, features, dw_stock`; `SELECT` on the seven Research objects; `ALTER DEFAULT PRIVILEGES FOR ROLE analytics_writer IN SCHEMA dw_stock GRANT SELECT ON TABLES TO data_writer` (the dbt swap). flex_writer `CONNECT`; `USAGE, CREATE` on `ops_jobs`; S/I/U/D on its four tables + sequence; `USAGE` on `raw_broker`; S/I/U on `executions_raw_flex, commissions, transactions`; S/I/D on `settings_flex`; S on `positions`; `USAGE` on their three sequences | GS ACLs | unchanged | yes | `sql/…-d6-rollback-gs.sql` |
| F4 | `sql/…-d6-2-grants-trade.sql -v db=bifrost_dev`: `CONNECT`; `USAGE` on `public, brokerage`; `SELECT` on `public.settings, brokerage.executions, brokerage.settings_flex`; `CREATE USER MAPPING FOR flex_writer SERVER golden_source_server` copying bifrost's mapping server-side (remote `brokerage_reader`, read-only; asserts it) | bifrost_dev ACLs, FDW mapping | mapping: server owner postgres | yes | `sql/…-d6-rollback-trade.sql -v db=bifrost_dev` |
| M1 | `sql/…-d6-3-ownership-gs.sql`: `ALTER TABLE / VIEW … OWNER TO data_writer` for every bifrost-owned relation in `raw_market` (165; sequences / indexes follow), `ALTER SCHEMA raw_market OWNER TO data_writer` | raw_market | data_writer | yes | `…-rollback-gs.sql` (every data_writer / flex_writer object in both schemas back to bifrost + data_writer's direct grants as they were) |
| M2 | same file: the seven market `ops_jobs` tables → data_writer | ops_jobs | data_writer | yes | same |
| F2 | same file: the four flex tables → flex_writer (`job_flex_ingest_id_seq` follows) | ops_jobs | flex_writer | yes | same |
| F5 | same file: `ALTER SCHEMA ops_jobs OWNER TO postgres`; the five helpers → postgres; `GRANT USAGE, CREATE ON SCHEMA ops_jobs TO data_writer, flex_writer` | ops_jobs schema, functions | postgres | yes | same |
| M3 | same file: `ALTER DEFAULT PRIVILEGES FOR ROLE data_writer IN SCHEMA raw_market GRANT SELECT ON TABLES TO analytics_writer, analytics_reader, market_reader, brokerage_reader`; `… IN SCHEMA ops_jobs … TO analytics_reader, market_reader`; `FOR ROLE flex_writer IN SCHEMA ops_jobs … TO analytics_reader` | default privileges | — | yes | same |
| bridge | same file: `GRANT USAGE ON SCHEMA raw_market, ops_jobs TO bifrost`; S/I/U/D/TRUNCATE on all their tables, USAGE/SELECT/UPDATE on their sequences | GS ACLs | — | yes | step 4 removes it |
| bridge off + M5 | `sql/…-d6-4-close-gs.sql` (after both switches; refuses while bifrost holds a > 2 min session in GS unless `-v force=1`): `REVOKE ALL` from bifrost on `raw_market` / `ops_jobs` (tables, sequences, schemas); from data_writer: everything on `raw_broker` (tables, views, sequences, schema) and bifrost's `raw_broker` default privileges for it, I/U/D/T/R/Tr/M on the four `features.option_metric_*` parents, everything on the four flex tables + sequence | GS ACLs | — | yes | `…-rollback-gs.sql` |
| M5b (named) | `sql/…-d6-4-close-trade.sql -v db=bifrost_stg` and `-v db=bifrost_prod`: `REVOKE ALL ON public.watchlist FROM data_writer` | Trade ACL | — | yes | `…-rollback-trade.sql` with the same `-v db` |

**Deviation from the plan's M2, named for the Owner:** the five partition helpers go to **postgres**, not data_writer.
They are SECURITY INVOKER (EXECUTE, which PUBLIC has, is all a caller needs), no plugin path re-creates them at run
time (only the superuser bootstrap `apply_ddl`), and Research's Dagster runs `ops_jobs.ensure_month_partitions` as
analytics_writer — an owning plugin could rewrite code Research executes. To follow M2 literally, change the function
loop's target in `…-3-ownership-gs.sql` to data_writer.
**Additions, named:** explicit `CONNECT` (+ `TEMPORARY` for data_writer, which its conditional view rebuild uses) so a
later `REVOKE CONNECT ON DATABASE bifrost_golden_source FROM PUBLIC` cannot cut them off; the dw_stock default
privilege (a plain table grant dies with each nightly dbt rebuild); the bifrost bridge; M5b.

## Order (Owner)

0. **Release the plugins first** (not Argo: build in cluster, pin, apply) — market-data **0.76.0**, flex-query
   **0.9.0** from branches `td-batch/2026-10-04-lane-ah`. They map `postgres-user` from their Secrets (optional), so
   with today's Secrets they still sign in as bifrost: no behaviour change. market-data: apply the migrate Job alone and
   wait for it (repo `CLAUDE.md` § 修改纪律). Then `scripts/plugin-db-roles.sh check` must say `manifests read
   postgres-user: yes` for both.
1. dry-run (below) — section 2 all `f`, section 5 shows bifrost's plugin sessions.
2. step 1 (roles); `scripts/plugin-db-roles.sh ensure`; `… password data_writer`; `… password flex_writer`.
3. step 2, GS and bifrost_dev (additive; plugins unaffected).
4. **Quiet window** (market-data slots fire at 02:15 trim, 03:30, :10 of 05–08 / 11 / 14 / 20 UTC, :20 every 6 h, and
   20:55–23:30 weekdays; the workers drain the queue all the time): e.g. 09:00–10:50 UTC. In one sitting:
   step 3 → `scripts/plugin-db-roles.sh switch market-data` → `… switch flex` → `… check`.
   Between step 3 and each switch the still-bifrost pods keep their DML through the bridge, but ownership-only work
   fails: the migrate Job, partition create / drop, and a flex pod that restarts (its first `ensure_flex_ops_schema`
   runs ALTERs). Do not restart pods by hand in that gap.
5. verify GS (all `ok = t`, the second query no rows) and Trade (dev / stg / prod); `… check` shows only data_writer /
   flex_writer sessions from the plugin namespaces.
6. step 4 (GS), then M5b in bifrost_stg and bifrost_prod; verify again.
7. Watch one plugin day: the 02:15 trim (`option_snapshot` / `option_daily` partitions created and dropped; the
   doctor's partition runway shows every parent owned), the evening batch, a Flex trades + cash pull; no
   `permission denied` / `must be owner` in `kubectl -n data logs bifrost-postgres-1 -c postgres` for data_writer or
   flex_writer.
8. Closing commits (separate branches `td-batch/2026-10-04-lane-ah-closing`): the plugins' ConfigMap `user:` lines →
   data_writer / flex_writer (apply with the next plugin release), and the two plugin holders leave
   `scripts/bifrost-password-rotate.sh` `HOLDERS` (bifrost is then held by db-init and CNPG only). Merge both only
   after step 7.

Rollback, any time: `scripts/plugin-db-roles.sh rollback market-data` / `rollback flex` (Secret back to bifrost, its
password read from `data/bifrost-postgres-app`, restart). Before step 4 the bridge carries bifrost's DML; after it, or
for ownership work, run `…-rollback-gs.sql` (and `…-rollback-trade.sql` per database, then `…-rollback-roles.sql`).

## Rehearsal (2026-10-04, throwaway docker postgres:17, nothing on the cluster)

Read-only `pg_dump --schema-only` of bifrost_golden_source, bifrost_dev and bifrost_stg + `pg_dumpall --roles-only
--no-role-passwords`; FDW mapping passwords scrubbed from the dumps on arrival; database ACLs mirrored by hand; the
`vector` column stubbed as text. An ACL / owner fingerprint of every relation, schema, ops_jobs function, default ACL,
database and user mapping matched the live cluster exactly (GS 495 objects, dev 69, stg 70). Invented rows only
(U0000001, ZZTA). The plugins' own code from the lane branches, signed in the way a pod does (ConfigMap user unless
`POSTGRES_USER` / `GOLDEN_SOURCE_USER` / `FLEX_TRADE_PG_USER` are set):

| phase | market-data | flex-query |
|-------|-------------|------------|
| A. today (bifrost) | 16 paths ok: migrate Job, upsert, TRUNCATE, sequence, job insert/claim/done, freshness, Research reads, trim CLI, partition create + drop, `ensure_partitions`, doctor runway. 11 of 12 "must not" checks **succeed** (today's over-reach: raw_broker writes, features writes, DROP of flex tables, `SET ROLE bifrost`, CREATE in public) | 11 paths ok; all 11 "must not" checks succeed (tws / journal / positions writes, raw_market, other plugin's tables, Trade UPDATE, `SET ROLE bifrost`) |
| B. steps 1-2, still bifrost | all ok | all ok |
| B'. negative control: switch before step 3 | migrate Job `must be owner of table option_open_interest`; partitions `must be owner`; doctor sees 7 parents not owned | `ensure_flex_ops_schema` `must be owner of table job_flex_ingest` |
| C. step 3 (bridge), still bifrost | DML, reads, trim ok; migrate Job / partition create fail (expected: ownership moved) | DML ok; a fresh process's ensure fails (expected) |
| D. switched | all 16 ok as data_writer (new partitions owned by data_writer, runway all owned); before step 4 raw_broker / features writes still possible | all 11 ok as flex_writer (FDW read over its own mapping); all 11 "must not" → 42501 |
| E. step 4 | all 16 ok; all 12 "must not" → 42501 / must be owner; bifrost: `permission denied for schema raw_market / ops_jobs` | all ok, all refused |
| verify | GS 57 / 57 ok, nothing outside the sets; Trade dev 9 / 9, stg 9 / 9 | |
| F. rollback (3 files) | fingerprint GS / dev / stg identical to A (0 lines); all paths ok as bifrost | all ok as bifrost |
| G. steps 1-4 again on the rolled-back state | 165 + 11 + 5 moved again, verify 57 / 57, all paths ok | all ok |

Step 3 twice: second run moves 0. Step 4 twice: no-op. Owner script (`scripts/plugin-db-roles.sh`) against the
container with a fake kubectl (Secrets as JSON, workloads = the rendered 0.75.0 / 0.76.0 and 0.8.1 / 0.9.0
manifests): `switch` refused without a local password, before step 3, and with the old manifests (lists every
workload missing `postgres-user`); with the new ones one Secret patch + restart each; pods then run as their Secret
says; `rollback` restores bifrost from the CNPG Secret; no password value appears in any output.

## Risks

- **Bridge gap** (step 3 → switch): ownership-only work fails for minutes; keep it short and in the window above.
- **A slow plugin statement holds a raw_market table**: step 3 takes ACCESS EXCLUSIVE per relation until COMMIT
  (catalog only); `lock_timeout 5s` rolls the whole step back — run it again.
- **flex reads bifrost_dev** for every environment (Secret `trade-pg-db`, ConfigMap fallback): kept as is; F4 grants
  that database only. Which environment flex should read is a separate decision (plan C5 #5).
- **`make sync-k8s-secrets` in the flex repo** rewrote the Secret with bifrost's PGPASSWORD; 0.9.0 makes it refuse
  once `postgres-user` is not bifrost.
- **Mac local tools**: the market-data repo's `.env` is set up for data_writer (`scripts/materialize_k8s_trade_secrets.py`
  says so; not read here): its old data_writer password stops working after `password data_writer`. The flex repo's
  `.env` holds bifrost's (D5 holder list) and keeps working for local runs.
- **Research's own grants**: D2 step 1c gave bifrost S/I/U/D/T on `features` / `research` because market-data read them
  as bifrost; after D6 nothing needs that, but Research's `_grant_*` re-adds it on every ddl-apply (plan C5 #2) — a
  Research follow-up, not this step.
- Not in this step: `market_reader` has `arwd` on one `raw_market` table; `analytics_writer` keeps direct CREATE on
  `raw_market` / `raw_broker` / `ops_jobs`; PUBLIC still has CONNECT on bifrost_golden_source (now safe to revoke for
  the plugins, other roles not checked).

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-dryrun.sql
commit (1): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-1-roles.sql
         then: scripts/plugin-db-roles.sh ensure && scripts/plugin-db-roles.sh password data_writer && scripts/plugin-db-roles.sh password flex_writer
commit (2): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-2-grants-gs.sql
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -v db=bifrost_dev -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-2-grants-trade.sql
commit (3, window): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-3-ownership-gs.sql
         then: scripts/plugin-db-roles.sh switch market-data && scripts/plugin-db-roles.sh switch flex && scripts/plugin-db-roles.sh check
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-verify-gs.sql
         for db in bifrost_dev bifrost_stg bifrost_prod; do kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d "$db" -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-verify-trade.sql; done
commit (4, after both switches): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-4-close-gs.sql
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -v db=bifrost_stg -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-4-close-trade.sql
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -v db=bifrost_prod -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-4-close-trade.sql
         then verify again, and checklist 7
rollback: scripts/plugin-db-roles.sh rollback market-data && scripts/plugin-db-roles.sh rollback flex
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-rollback-gs.sql
         for db in bifrost_dev bifrost_stg bifrost_prod; do kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d "$db" -X -v ON_ERROR_STOP=1 -v db="$db" -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-rollback-trade.sql; done
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d6-rollback-roles.sql
