---
name: stock-readiness-retire
description: >-
  Retire Trade DB public.stock_readiness_daily — analysis, DDL cleanup, API hygiene.
  Use when executing program stock-readiness-retire or Owner asks about SRD / readiness snapshot table.
---

# Stock Readiness Daily Retire

## Program

- **id:** `stock-readiness-retire`
- **lane:** `stock-readiness-retire` (Satellite · Migrate)
- **Blueprint:** `bifrost-platform/config/programs/active/stock-readiness-retire.yaml`
- **D10:** BLOCKED — do not unsuspend `market-data-readiness-refresh`

## What the table was

`public.stock_readiness_daily` — per-symbol daily SEPA readiness snapshot on **Trade OLTP DB**:
universe inclusion, price bar coverage, financials presence, `fundamental_eval` / `technical_eval` jsonb.

PK: `(as_of_date, symbol, universe_rule_version, price_source)`.

## P1 analysis summary (2026-08-23)

### Verdict

**RETIRE** — no ongoing business meaning under production defaults.

| Layer | Default path | Uses `stock_readiness_daily`? |
|-------|--------------|-------------------------------|
| Trade API | `SEPA_USE_ANALYTICS=true` | No — marts + Research proxy |
| Trade FE | via API only | No |
| Platform Gallery rollup | Plugin `/readiness/snapshot-coverage` | No |
| Data Readiness runbook gaps | Plugin HTTP | No |
| dbt writer | `dw_stock.mart_sepa_*` on Golden Source | No (replacement) |
| Plugin CronJob | `market-data-readiness-refresh` | Would UPDATE — **suspend: true** |

Legacy path (`SEPA_USE_ANALYTICS=false`) still has ~20 SQL branches in `data_readiness.py` — footgun if table DROPped.

### Replacement map

| SRD concept | Replacement |
|-------------|-------------|
| `fundamental_eval` | `dw_stock.mart_sepa_fundamental_eval` → `analytics.sepa_fundamental_eval` |
| `technical_eval` | `dw_stock.mart_sepa_technical_eval` |
| Screener row | `dw_stock.mart_sepa_screener_wide` |
| Criteria stats | `mart_sepa_criteria_stats` |
| Tier / momentum | `mart_sepa_tier_*` |
| Price/financial gaps | Plugin `GET /market/readiness/*` |

Pipeline: dbt CronJob (plugin-market-data NS) → Golden Source → Research API `:8795` → Trade `analytics_reader.py`.

### Live STG smoke (2026-08-23)

- `GET criteria-stats`: `ok: true`, `universe_count: 5356`, fundamental cached ~3555
- `GET symbols-snapshot`: `count: 0` — **mart_sepa_screener_wide still empty** (252d bar depth; not SRD-specific)

### Technical debt

1. `bifrost_core.persistence.postgres.ddl.py` — still `CREATE TABLE` (DEPRECATED comment)
2. `readiness_snapshot.py` — large writer + `compute_sepa_criteria_stats` legacy
3. `data_readiness.py` — legacy branches when analytics false
4. FE `ReadinessResultsTable.tsx` — stale empty hint mentions table name
5. Docs: `workLanes.ts` RETAIN vs MIGRATION_TRACKING §15 DROP

### Ground truth

- MIGRATION_TRACKING §15: table **DROPped** dev/stg/prod 2026-08-20/21
- market-data-gs-closeout P3 acceptance (2026-08-15): RETAINED — **superseded by §15**

## Key files

| Repo | Path |
|------|------|
| core DDL | `bifrost-trade-core/src/bifrost_core/persistence/postgres/ddl.py` |
| API routes | `bifrost-trade-api/src/bifrost_api/research/routers/data_readiness.py` |
| Writers | `bifrost-trade-api/src/bifrost_api/research/sepa/readiness_snapshot.py` |
| Analytics gate | `bifrost-trade-api/src/bifrost_api/research/analytics_reader.py` |
| dbt marts | `bifrost-research/src/bifrost_research/dbt/models/marts/mart_sepa_*.sql` |
| Plugin (suspended) | `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py` |
| FE | `bifrost-trade-frontend/src/hooks/useSymbolsReadinessSnapshot.ts` |

## Phases

| ID | Title | Status |
|----|-------|--------|
| P1 | Analysis + verdict | done |
| P2 | Owner RETIRE lock | pending |
| P3 | Code + DDL hygiene | pending |
| P4 | Verify + deliver | pending |
| P5 | Doc/catalog sync | pending |

## Verify commands

```bash
# STG analytics path
curl -sf 'http://192.168.10.73:30880/api/research/research/data/readiness/criteria-stats'

# Lint
cd bifrost-trade-api && ruff check src/
cd bifrost-trade-core && make lint && make test

# Deliver (after P3)
cd bifrost-trade-infra && APPLY_OVERLAY=1 make k3s-deliver-stg
cd bifrost-trade-infra && APPLY_OVERLAY=1 make k3s-deliver-prod
```
