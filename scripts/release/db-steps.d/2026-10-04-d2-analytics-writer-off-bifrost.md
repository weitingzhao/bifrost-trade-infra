---
id: 2026-10-04-d2-analytics-writer-off-bifrost
envs: prod
when: after
done: prod
---
# TD-85 D2: Research's analytics_writer stops inheriting bifrost (Golden Source only)

Owner-approved 2026-10-04 (`REQUEST-trade-runtime-db-role-plan-2026-10-04.md`, "Owner 批复" D2: a separate Research
step, explicit grants first). Not tied to a Trade release: it is listed under `prod` / `after` only so
`release.sh` prints it; it touches **bifrost_golden_source alone** (one database for all envs) and needs no
Secret, image or manifest change. Pick a quiet window (below), not a release.

**Why.** `analytics_writer` (Research: research-api, research-mcp, Dagster daemon / webserver, CronJobs) is a
member of `bifrost` (inherit + SET ROLE). Through it Research can write every table of the three Trade databases,
all of `raw_broker`, `raw_market`, `ops_jobs`, `ops_feedback`, create in GS `public`, and `SET ROLE bifrost`.

**What Research really uses only through bifrost** (read-only measurement 2026-10-04 05:4x UTC, dry-run file; code
at research origin/main ed144db = 0.161.0 / 0.161.0-dagster, Dagster run history of the last 7 days):

| # | need | where in Research | why bifrost | covered by |
|---|------|-------------------|-------------|------------|
| 1 | ownership of the 4 partitioned parents `features.option_metric_{atm_iv,iv_percentile,max_pain,pcr}_daily` | Dagster `research_ensure_partitions_job` (1st of month 00:30 UTC) → `ops_jobs.ensure_month_partitions` → `CREATE TABLE … PARTITION OF` | parents owned by bifrost; the 8 partitions y2027m01/m02 Research made on 10-01 are analytics_writer's | step 1 (ownership) |
| 2 | ownership of the other 46 bifrost-owned relations in `features` (45 tables + view `v_atm_iv_unified`) and the 18 in `research`, plus 72 old partitions | `research-ddl-apply` Job / `schema.init --apply` and the canonical_pnl CLI (`apply_all_ddl`: `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, `COMMENT ON`, `CREATE OR REPLACE VIEW`) | Postgres checks ownership before IF NOT EXISTS; the Job's own comment says "sweep ownership back to bifrost" | step 1 (ownership) |
| 3 | SELECT `raw_broker.executions_final` | `engines/journal_distill.py` (memory distill 23:55 UTC), `repositories/journal_memory.py` | no grant to analytics_* on any raw_broker object | step 1 (GRANT) |

Everything else Research touches it already holds directly: DML on all 112 + 19 relations of features / research
(direct `arwdD`), owner of journal / dw_stock / ops_dbt / ops_dagster, SELECT on all 165 raw_market relations,
`ops_jobs.watchlist_cache`, USAGE / CREATE on its schemas, CONNECT / CREATE / TEMP on the database, EXECUTE on the
partition helper. **Correction to the plan's R5:** Research's code reads none of the 8 `ops_jobs` tables without a
grant (only `watchlist_cache`, which has one); they are in the "goes away" list, not the "needs" list.

What the revoke takes away (dry-run query 4, expected rows): raw_broker 13 relations (S/I/U/D/T),
raw_market 165 (I/U/D/T), ops_jobs 8 (+TRUNCATE on 11), ops_feedback 2, `SET ROLE bifrost`, CREATE in GS
`public`, and all table rights in bifrost_dev / stg / prod.

## Statements

| # | file / statement | object | owner after | reversible? | rollback |
|---|------------------|--------|-------------|-------------|----------|
| 1a | `GRANT SELECT ON raw_broker.executions_final TO analytics_writer` (`sql/…-d2-analytics-writer-grants.sql`) | view ACL | bifrost (unchanged) | yes | `REVOKE SELECT ON raw_broker.executions_final FROM analytics_writer` (full rollback file) |
| 1b | `ALTER TABLE / VIEW … OWNER TO analytics_writer` for every bifrost-owned relation in `features` and `research` (122 today: 4 parents + 72 partitions, 45 + 18 tables, 1 view; indexes follow) | ownership | analytics_writer | yes | `sql/…-rollback-ownership.sql` (literal list of the 122, with analytics_writer's original direct grants) |
| 1c | `GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA features, research TO bifrost` | table ACLs (bifrost loses its owner entry in 1b; market-data still signs in as bifrost and reads `features.option_metric_*`, `research.option_universe`, `research.option_pinned_contract`) | — | yes | folds back into the owner entry on rollback |
| 2 (optional) | `ALTER SCHEMA features / research OWNER TO analytics_writer` + `GRANT USAGE ON SCHEMA features, research TO bifrost` (`sql/…-schemas.sql`) | schema owner (a schema owner may DROP any table in it: today db-init and both plugins could drop Research's tables) | analytics_writer | yes | in the full rollback file (only if 2 ran) |
| 3 | `REVOKE bifrost FROM analytics_writer` (`sql/…-revoke.sql`; refuses unless step 1 left 0 gaps) | role membership (granted by postgres, inherit + set) | — | yes | `GRANT bifrost TO analytics_writer WITH INHERIT TRUE, SET TRUE GRANTED BY postgres` (`sql/…-rollback.sql`) |

Step 1 changes nothing Research does (analytics_writer stays a member until step 3); it takes an ACCESS EXCLUSIVE
lock per relation for the length of one short transaction (catalog only), `lock_timeout 5s` — if research-api holds
a table the whole step rolls back and is simply run again. Idempotent (second run moves 0). Step 3 takes effect
for new and running sessions at their next privilege check.

**Rollback** is one statement (`…-rollback.sql`), instant, and restores every right Research had; steps 1 / 2 may
stay (analytics_writer owning Research's tables is what Research's own DDL produces). The full rollback
(`…-rollback-ownership.sql`) also puts the 122 owners, the schema owners and the view grant back.

## Rehearsal (2026-10-04, throwaway docker postgres:17, nothing on the cluster)

Read-only `pg_dump --schema-only` of bifrost_golden_source + `pg_dumpall --roles-only --no-role-passwords`
(roles and membership mirrored; database ACL mirrored by hand; `vector` column stubbed as text — the image has no
pgvector) + a synthetic Trade database `bifrost_dev`. Suite = Research's own code from origin/main
(`apply_all_ddl`, `ensure_month_partitions`) logged in as analytics_writer, the journal and option-universe
queries, S/I/U/D on every Research table, TRUNCATE canonical_pnl, a dbt-style table swap in dw_stock; negatives
(raw_broker / raw_market writes, ops_jobs.job_ingest, ops_feedback, `SET ROLE bifrost`, CREATE in public, a Trade
table); and bifrost / market_reader reading features + research.

| phase | result |
|-------|--------|
| baseline (member of bifrost) | all Research checks ok; **all 7 negatives also ok** (today's over-reach) |
| negative control: `REVOKE` without step 1 | `apply_all_ddl` 42501; `ensure_month_partitions` created **nothing and reported nothing** (it swallows errors); executions_final 42501 — this is what a bare revoke would break. `…-revoke.sql` refused: "123 need(s) … not covered" |
| step 1 twice, step 2, dry-run, step 3 | NOTICE 122 moved (then 0); `ready_to_revoke = t`; every Research check ok, new partitions created; 7 negatives 42501; bifrost / market_reader reads ok; bifrost `DROP TABLE research.hypothesis` → must be owner; verify 25/25 |
| rollback ×2, then full rollback | Research checks ok; 122 relations back to bifrost with the original ACL strings, schemas back, view grant gone |
| step 1 + 3 again on the rolled-back state | 122 moved, verify 25/25 |

## Quiet window

Dagster runs (ops_dagster.runs, last 7 days): the trading-day batch 02:30 UTC (11–16 min), forecast 03:00, the
23:20–23:55 engine chain, intraday 14:45–20:45 (America/New_York 10:45–16:45), event radar every 30 min on
weekdays (seconds), ensure_partitions on the 1st at 00:30, weekly backfill Sunday 22:00 (≈4 h). research-api reads
features all day (UI). **Recommended: a weekend day 06:00–20:00 UTC, or a weekday 05:45–10:15 UTC**, not the 1st
of a month. Then let one full weekday cycle run before calling it done.

## Owner checklist

1. dry-run → note `ready_to_revoke = f` with `gaps = 123` (122 owners + executions_final).
2. step 1 (grants) → dry-run again: `ready_to_revoke = t`, query 5 shows features / research owned by analytics_writer only and bifrost S/I/U/D/T on all of them.
3. (optional, name it) step 2 (schemas).
4. step 3 (revoke) → verify: 25 rows `ok = t`, inherited-only list empty.
5. Exercise the two DDL paths as analytics_writer in the cluster (this is DDL, yours to run; both are idempotent):
   `kubectl -n research exec deploy/dagster-daemon -- python -m bifrost_research.schema.init --apply --scope all`
   → prints `apply_all_ddl complete`; and the partition helper with one month more than the schedule uses
   (y2027m03 would be created on 11-01 anyway):
   `kubectl -n research exec deploy/dagster-daemon -- python -c "from bifrost_research.db.conn import connect; from bifrost_research.schema.ddl import ensure_month_partitions as e; c=connect(); e(c, months_back=3, months_forward=5); c.close()"`
   then the partition count of `features.option_metric_pcr_daily` must have grown by one (the helper hides errors:
   **count, do not trust the exit**).
6. Next weekday: `research_trading_day` (02:30), the 23:20–23:55 chain and `research_memory_distill_job` SUCCESS;
   no `permission denied` for analytics_writer in `kubectl -n data logs bifrost-postgres-1 -c postgres`.
7. `release.sh db-done prod 2026-10-04-d2-analytics-writer-off-bifrost`.

Follow-ups outside this repo (Research lane, no DB change): `k8s/jobs/ddl-apply.yaml`'s comment ("sweep
ownership back to `bifrost`") must say the opposite now; `ensure_month_partitions` should not swallow errors; the
Mac's `bifrost-research/.env` signs in as `bifrost` (local Research tooling) and should use analytics_writer.
Not in this step: analytics_writer's own direct `CREATE` on schemas `raw_market`, `raw_broker`, `ops_jobs`
(from `scripts/golden_source_schema_grants.sql`; not used by Research's code) — a D13 hardening candidate.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-dryrun.sql
commit (1): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-grants.sql
commit (2, optional): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-schemas.sql
commit (3): kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-revoke.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-verify.sql
         then checklist 5 and 6
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-d2-analytics-writer-rollback.sql
         (full, after it, only if the owners must go back too: …-rollback-ownership.sql the same way)
