# DB Hygiene Wave 3 — executable phase plan

> Status: **GREEN — all Owner decisions recorded 2026-08-24. Ready to
> execute on Owner "start" command.**

## Owner decisions (2026-08-24)

| # | Decision |
|---|---|
| **D-W3.1** | **DROP** `strategy_history` — feature not needed. Remove DDL, core writer/reader, Trade API endpoint, and Frontend `StrategyHistorySection`. |
| **D-W3.2** | **LEAVE** `raw_broker.transactions.raw_extra` — accept the ~2× storage cost on this small table. |
| **D-W3.3** | **EXTEND** `raw_broker.transactions` UNIQUE tuple to `(account_id, ts, amount, type, report_date)`. |
| **D-W3.4** | **WIDE scope** — Wave 3 covers D-W3.1 (Trade DB) **and** D-W3.3 (Golden Source). D-W3.2 collapses to a no-op inside the wide scope. |
| **K-W3.1** | **SINGLE cutover** — Wave 2 + Wave 3 ship together as one `bifrost-core v0.12.0` release. `v0.11.0` stays a local tag; no standalone Wave 2 rollout to STG/PROD. |
| **K-W3.2** | **SILENT removal** for `StrategyHistorySection` — table has been empty since day one; no user has seen data there. No deprecation banner. |

Wave 1 (2026-08-24) closed Plugin ingest drift and dbt lookback.
Wave 2 (2026-08-24) folded 3 strategy KV subtables into jsonb and moved
`ops_audit_log` DDL into `bifrost-core`, taking Trade DB `strategy_*` from
15 → 12 tables. This blueprint captures what remains after those two waves
and framing choices for Owner.

## 1. What is actually left on the Trade DB side

After Waves 1–2 the trade DB has 12 `strategy_*` tables and the retained
`preference_*` set. Row counts (2026-08-24) across dev/stg/prod:

| Table | dev / stg / prod | Verdict |
|---|---|---|
| `strategy_dim`                          | 25 / 25 / 25 | **Keep** — enum dictionary (direction / structure / coverage / risk / volatility / time); consumed by `OptionCategoryDimensionsDialog.tsx` and core reader |
| `strategy_template` / `_leg`            | 14 / 14 / 14 · 26 / 26 / 26 | **Keep** — active, jsonb-collapsed in Wave 2 |
| `strategy_structure` / `_leg`           | 6 / 6 / 6 · 13 / 13 / 13 | **Keep** — active, jsonb-collapsed in Wave 2 |
| `strategy_instance`                     | 80 / 74 / 82 | **Keep** — live |
| `strategy_opportunity` / `_symbol`      | 21 / 19 / 23 | **Keep** — live |
| `strategy_opportunity_entry_condition`  | 1 / 1 / 1 | **Keep** — seed row only, but core writer + FE (`AllocationsPage`) exist. Feature-gated, not obsolete. |
| `strategy_allocation` / `_opportunity`  | 1 / 2 across all envs | **Keep** — feature-gated (portfolio allocations); core has `strategy_allocation_write.py`, FE has `AllocationsPage.tsx` |
| `strategy_history`                      | **0 / 0 / 0** | **Owner decision D-W3.1 (below)** — full read/write pipeline present but `daemon.status_sink.append_history` is never set to `True`. Feature never enabled. |

There is **no more "obviously dead" table on Trade DB**. The only genuine
"never-written" surface is `strategy_history`, which is a dormant feature
rather than a legacy fossil.

Legacy artefacts already reconciled (do not re-do):

- `preference_data_gap_ack` — retired in core `0.10.10` (Wave 1)
- `strategy_template_param` / `_characteristic` / `strategy_structure_meta` — retired in core `0.11.0` (Wave 2)
- `ops_audit_log` DDL — owned by core `0.11.0` (Wave 2)
- `flex_ops` compat views — verified absent in Golden Source AND all Trade DBs (2026-08-24)

## 2. Where the real Wave 3 work sits — Golden Source `raw_broker.transactions`

DEV Golden Source `raw_broker.transactions` currently holds **102 rows**
(2025-04-02 → 2026-08-06; dividend/withdrawal/deposit/other, no `Trade` rows
because those live in `executions_raw_flex`). Column density:

| Column | non-null % | Note |
|---|---|---|
| `account_id`, `ts`, `amount`, `type`, `currency`, `description`, `flex_type`, `report_date`, `fx_rate_to_base`, `raw_extra` | 100 % | core fields, always populated |
| `asset_category`, `asset_subcategory`, `symbol`, `conid`, `security_id`, `security_id_type`, `listing_exchange` | 29 % | only for dividend rows tied to a symbol |
| `available_for_trading_date` | 5 % | rare Flex field |
| **`flex_transaction_id`** | **0 %** | IB Cash Transactions XML does **not** emit `transactionID` for cash txns — investigated 2026-08-24 |
| **`flex_code`** | **0 %** | IB Cash Transactions XML `code` attribute is empty for the queried report types — investigated 2026-08-24 |

### 2.1 Redundant `raw_extra`

Every row's `raw_extra` jsonb re-stores the full XML attribute dict; keys
like `code`, `figi`, `isin`, `conid`, `cusip`, `symbol`, `putCall`,
`expiry` all appear both in `raw_extra` and as promoted columns. Estimated
half the payload is redundant. Two tactics:

- **Option A (thin)** — leave `raw_extra` untouched (current); accept ~2×
  storage on a small table. Cheap, safe.
- **Option B (strip)** — Plugin upsert removes keys already promoted to
  top-level columns before `raw_extra = jsonb`; existing rows migrate via
  a one-shot backfill. Saves storage, but hides fields from anyone reading
  `raw_extra` directly.

### 2.2 Deduplication key is fragile

DDL: `UNIQUE (account_id, ts, amount, type)`. If two same-type cash
movements happen on the same trading day for the same account with the
same amount (rare but not impossible for dividends across two symbols),
they collapse into one row. Since IB does not give us `transactionID` on
cash txns, we cannot promote to a real IB-provided key.

Mitigation candidates for Owner:
- Add `md5(description || asset_category || symbol)` as a tiebreaker,
- Or add `report_date` to the UNIQUE tuple (safer for daily aggregation).

Do not change this without an Owner decision — it is data-shape.

## 3. Owner decisions — recorded (see banner)

See the decision block at the top of this document. §4 below is the
executable phase plan derived from those decisions.

## 4. Wave 3 phase plan (Wide scope — D-W3.1 drop + D-W3.3 extend)

Two independent tracks. Track A touches Trade DB / core / api / Frontend.
Track B touches only Golden Source and `bifrost-flex-query`. They can run
in either order or in parallel; recommended order is **A first** to
consolidate the core version bump, then **B**.

### Track A — Retire `strategy_history` (Trade DB / core / api / FE)

| Phase | Change | Files |
|---|---|---|
| **A1** | Remove core write path — delete the `append_history` branch and DDL migration | `bifrost-trade-core/src/bifrost_core/persistence/postgres_sink.py`, `bifrost_core/persistence/status_sink.py`, `bifrost_core/persistence/postgres/ddl.py` (remove `_log_table("strategy_history", ...)` block + indexes) |
| **A2** | Remove core reader | `bifrost_core/monitor/reader/strategy.py` (delete `get_strategy_history`), `bifrost_core/monitor/reader/common.py` (delete wrapper) |
| **A3** | Remove Trade API endpoint | `bifrost-trade-api/src/bifrost_api/monitor/routers/status.py` and/or `config.py` and `strategy/routers/strategies.py` — grep for `get_strategy_history` and `strategy_history` |
| **A4** | Remove Frontend surface | `bifrost-trade-frontend/src/components/strategy/StrategyHistorySection.tsx` (delete), `src/pages/strategy/StructuresPage.tsx` (unwire import), `src/api/strategy.ts` (delete `fetchStrategyHistory`), `src/types/strategy.ts` (delete `StrategyHistoryRow/Params/Response`), `src/types/positions.ts` (re-export cleanup) |
| **A5** | Idempotent DROP TABLE + schema-report update | Add `DROP TABLE IF EXISTS strategy_history CASCADE` guarded call inside a `_retire_strategy_history` helper in core `ddl.py`; remove `strategy_history` from `scripts/db/_schema_report.py::EXPECTED_TABLES_BY_CATEGORY` |
| **A6** | Version bump `bifrost-core` → **`0.12.0`** (MINOR — dropped a public reader function) | `bifrost-trade-core/pyproject.toml`, `bifrost-trade-core/CLAUDE.md`; `bifrost-trade-api/pyproject.toml` pins `>=0.12.0`; `bifrost-trade-infra/.env.example` → `v0.12.0` |
| **A7** | Trade DB verification — apply DDL in DEV/STG/PROD, confirm table absent + api-account healthy | run `db-init`; extend `verify_wave2_api_account.sh` or add `verify_wave3_strategy_history_retired.sh` |

### Track B — Golden Source `raw_broker.transactions` UNIQUE hardening

Current index: `UNIQUE(account_id, ts, amount, type)`. New:
`UNIQUE(account_id, ts, amount, type, report_date)`. `report_date` is
100% non-null in current data (2026-08-24 sample: 102/102 rows), so the
migration is safe — but the new UNIQUE **must** be created before
Plugin upsert code switches its `ON CONFLICT` target, otherwise upsert
will fall back to plain INSERT and duplicate.

| Phase | Change | Files |
|---|---|---|
| **B1** | Backfill guard — verify `report_date IS NULL` count in `raw_broker.transactions` is 0 across DEV/STG/PROD (production Golden Source is single instance, so one check suffices) | ad-hoc `psql` query captured in verify script |
| **B2** | DDL migration — `CREATE UNIQUE INDEX CONCURRENTLY raw_broker_transactions_dedupe_v2 ON raw_broker.transactions (account_id, ts, amount, type, report_date)` then swap the CONSTRAINT | `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/schema/…` (or wherever brokerage DDL is applied) — path likely `bifrost-trade-core/src/bifrost_core/persistence/postgres/brokerage_ddl.py` since core owns the transactions DDL |
| **B3** | Upsert `ON CONFLICT` target — change from `(account_id, ts, amount, type)` to `(account_id, ts, amount, type, report_date)` in `upsert_account_transactions` | `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py` (~line 1236). This means Track B **also** needs a core bump — fold into A6 → `0.12.0` |
| **B4** | Plugin ingest smoke — trigger Flex cash-transactions ingest on DEV; confirm existing rows do not duplicate; confirm same-day-different-report-date rows now co-exist | `bifrost-platform-plugin-flex-query/Makefile` verify targets or a new `verify_wave3_broker_dedupe.sh` |
| **B5** | Plugin version bump (only if the Plugin runs its own DDL step; otherwise skip — Plugin only depends on core `0.12.0`) | `bifrost-platform-plugin-flex-query/pyproject.toml` |

### Track C — Roll-up and documentation

| Phase | Change |
|---|---|
| **C1** | Update `bifrost-trade-infra/docs/MIGRATION_TRACKING.md` with a new "DB Hygiene Wave 3" entry (Wave 3 DONE date, changes summary, breaking notes) |
| **C2** | Update `bifrost-trade-infra/docs/WAVE2_ROLLOUT.md` → new `WAVE3_ROLLOUT.md` sibling with the same delivery-pipeline flow (Kaniko rebuild → rollout restart → `verify_wave3_*.sh`) |
| **C3** | Local `git tag v0.12.0` on `bifrost-trade-core` (Owner controls push) |

## 5. Rollback posture

Track A: schema-destructive on read (drops a table with 0 rows). If a
regression appears the rollback is `bifrost-core` image revert; the
table itself is empty so nothing is lost. **One-way door once merged**.

Track B: `CREATE UNIQUE INDEX CONCURRENTLY` is non-blocking and reversible
via `DROP INDEX CONCURRENTLY` before the constraint swap. After the swap
the rollback requires re-creating the old UNIQUE — still safe because
existing rows already respect both keys (report_date is present).

## 6. Version and rollout coupling

Both tracks bump `bifrost-core` to a **single** `v0.12.0` release; A and
B ship in one image. Rollout uses the same `bifrost-deliver-stg` /
`-prod` Tekton pipelines as Wave 2.

## 7. Verification handles (extend, do not replace)

- `scripts/verify_wave2_api_account.sh` — after Wave 3, also assert that
  `to_regclass('public.strategy_history') IS NULL` and that
  `pg_indexes` shows the 5-column dedupe index. Add these as an
  *append-only* patch to keep Wave 2 semantics intact.
- New `scripts/verify_wave3_strategy_history_retired.sh` — per-env probe
  that (a) the table is gone, (b) Trade API no longer exposes
  `/api/strategies/history` (or whatever the endpoint was), (c) the
  frontend build succeeds without the section.
- New `scripts/verify_wave3_broker_dedupe.sh` — asserts the 5-column
  UNIQUE index exists on Golden Source and that a synthetic
  same-`(account,ts,amount,type)` but different-`report_date` row can
  coexist.

## 8. Kick-off — CLEARED

K-W3.1 / K-W3.2 recorded in the banner. Phase execution starts with **A1**
on Owner "start" command. There are no other blockers.

Consequences of K-W3.1 = SINGLE:
- Wave 2 changes (jsonb-collapsed strategy tables + `ops_audit_log` DDL
  in core) ride with Wave 3 in the same `v0.12.0` image. `verify_wave2_*`
  scripts stay valid; they will be run *after* the merged rollout.
- `bifrost-trade-core` local tag `v0.11.0` remains as historical marker;
  the pushed release will be `v0.12.0`.

Consequences of K-W3.2 = SILENT:
- A4 deletes `StrategyHistorySection.tsx` outright; no intermediate
  "deprecated" banner.
- No user-visible release note beyond the standard changelog entry.

## 9. Non-goals (unchanged from pre-scope)

- Cross-repo consolidation (Ops Console catalogs, Platform data-clone) —
  done in Wave 2.
- Live trading enablement — remains BLOCKED per D10.
- Any change to `preference_*` tables — retained decision from Wave 2.
- Any change to `strategy_dim` / `strategy_allocation*` — active feature
  surfaces, kept as is.
- `market.*` / `features_*` schema changes on Golden Source — belongs to
  Research/Plugin waves, not Trade DB hygiene.
- `raw_broker.transactions.raw_extra` — D-W3.2 recorded **LEAVE**.
