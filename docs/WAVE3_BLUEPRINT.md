# DB Hygiene Wave 3 — pre-scope blueprint

> Status: **Blueprint / Owner decisions pending** — do not begin execution
> until the four decision points below are answered.

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

## 3. Owner decisions (blockers before Wave 3 execution)

| # | Question | Impact if deferred |
|---|---|---|
| **D-W3.1** | `strategy_history` — **keep alive** (turn on `append_history=True` in daemon FSM transitions and expose in Frontend) or **drop** (remove core DDL/reader/writer, remove FE section, drop table)? | UI section keeps showing 0 rows; forensics on FSM transitions unavailable |
| **D-W3.2** | `raw_broker.transactions.raw_extra` — **A: leave** or **B: strip promoted keys**? | Cost is small (table is ~102 rows), so leaving is safe. B pays off only if this table grows 100×. |
| **D-W3.3** | `raw_broker.transactions` UNIQUE key — leave `(account_id, ts, amount, type)`, or extend with `report_date` / description hash? | Rare same-day duplicate cash txns collapse silently. Zero incidents observed so far. |
| **D-W3.4** | Wave 3 scope philosophy — **narrow** (only D-W3.1 answered) or **wide** (also address D-W3.2 / D-W3.3 and any Owner-added items)? | Determines whether Wave 3 is a same-day cleanup or a full Golden Source hygiene pass. |

## 4. Proposed Wave 3 phases (subject to Owner decisions above)

Assumes narrow scope (**D-W3.1 = drop**, D-W3.2 = leave, D-W3.3 = leave):

1. **P1 — Remove `strategy_history` write path.** Delete `append_history`
   branch in `bifrost_core.persistence.postgres_sink` and status_sink API;
   `_ensure_strategy_history` migration; DROP TABLE guarded with
   idempotent `IF EXISTS`.
2. **P2 — Remove reader + API surface.** Drop
   `bifrost_core.monitor.reader.strategy.get_strategy_history`,
   `common.get_strategy_history`, and the Trade API endpoint (if wired).
3. **P3 — Remove Frontend section.** Drop `StrategyHistorySection.tsx`,
   `StrategyHistoryRow/Params/Response` types, and unwire it from
   `StructuresPage.tsx`.
4. **P4 — Bump `bifrost-core` to `0.11.1`** (or `0.12.0` if we also change
   the reader API contract), refresh `BIFROST_CORE_REF`, run
   `verify_wave2_api_account.sh` variant to prove the API contract still
   holds.

Assumes wide scope adds:

5. **P5 (optional)** — Plugin upsert change: strip promoted keys from
   `raw_extra`; one-shot backfill in `bifrost_golden_source` (small table,
   safe).
6. **P6 (optional)** — Extend `raw_broker.transactions` UNIQUE index with
   `report_date` or `md5(description)`; migrate via `CREATE UNIQUE INDEX
   CONCURRENTLY` and swap.

## 5. Verification handles (already in place)

- `bifrost-trade-infra/scripts/verify_wave2_api_account.sh` — will keep
  guarding jsonb columns and audit table presence after Wave 3.
- `bifrost-trade-infra/scripts/verify_clone_audit_preservation.sh` — will
  keep guarding audit-preservation across clones.
- `bifrost-trade-core/scripts/db/_schema_report.py` — canonical expected
  table set; update in Wave 3 if `strategy_history` is dropped.

## 6. Non-goals (explicitly out of Wave 3)

- Cross-repo consolidation (Ops Console catalog changes, Platform data-clone
  logic) — done in Wave 2.
- Live trading enablement — remains BLOCKED per D10.
- Any change to `preference_*` tables — retained decision from Wave 2.
- Any change to `strategy_dim` / `strategy_allocation*` — active feature
  surfaces, kept as is.
- `market.*` / `features_*` schema changes on Golden Source — belongs to
  Research/Plugin waves, not Trade DB hygiene.

## 7. Recommended order of Owner conversation

1. Read section 3 (four decisions).
2. Pick scope: narrow vs wide (D-W3.4).
3. Confirm D-W3.1 direction (keep-alive vs drop). This is the only
   decision that touches user-visible UI (StrategyHistorySection).
4. If wide scope, pick D-W3.2 / D-W3.3 defaults.

Once the four decisions land, this blueprint becomes an executable phase
plan and can be lifted into `MIGRATION_TRACKING.md` under a new "Wave 3
DB Hygiene" heading.
