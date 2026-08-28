---
name: trade-iv-radar
description: >-
  Wave A — Trade Research IA (Ideas/Volatility/Structure/Risk/Lab) + IV Radar
  (IV Rank regime). Use when executing program trade-iv-radar phases or Owner
  says IV Radar / Research menu / vol regime.
---

# Trade IV Radar (Wave A)

## Program

- **id:** `trade-iv-radar`
- **lane:** `trade-iv-radar` (Satellite · Build · Trade IV Radar — independent lane)
- **Blueprint:** `bifrost-platform/config/programs/active/trade-iv-radar.yaml`
- **D10:** observe-only — no place_order / no daemon arming
- **Out of scope:** A2 Event Radar, GEX, full-market scanner, live trading

## Owner decisions (locked)

1. Research nav: **Ideas / Volatility / Structure / Risk / Lab**
2. Nav label **Contract Greeks** (was IV & Greeks)
3. **Data Readiness** → Settings beside Coverage
4. IV Radar: Rank primary, Percentile column; independent page
5. Universe: **Benchmarks ∪ optionable Watchlist ∪ Holdings** (no full scan)
6. Benchmarks default: `SPY`, `QQQ`, `IWM`

## Phases

| ID | Title | Verify |
|----|-------|--------|
| P1 | Research IA M1 | `cd bifrost-trade-frontend && npm run lint && npm run build` |
| P2 | IV Radar data layer | same |
| P3 | IV Radar page UI | + `npm run check:legacy-css` |
| P4 | Wave A acceptance | + `npm run check:legacy-css` |

## Key files

- `bifrost-trade-frontend/src/layout/navConfig.ts`
- `bifrost-trade-frontend/src/layout/SettingsLayout.tsx`
- `bifrost-trade-frontend/src/lib/router.tsx`
- `bifrost-trade-frontend/src/lib/devApiUrl.ts` → `marketDataPluginUrl`
- Plugin: `GET /market/analytics/iv-percentile` (via platform proxy `:8780`)

## Industry vocabulary (UI English)

| Term | Meaning |
|------|---------|
| Benchmarks | SPY/QQQ/IWM market weather |
| Watchlist | optionable research candidates |
| Holdings | portfolio underlyings |
| IV Rank | position in 1y high–low range (primary buckets) |
| IV Percentile | % of history days with lower IV (column) |
| IV Radar | underlying **regime** page |
| Contract Greeks | contract history Greeks page |
| Option Discovery | chain / term / structure |

## Daily ritual (teach Owner after P4)

1. Open **IV Radar** → read **Benchmarks** regime  
2. Switch **Holdings** — is book expensive/cheap?  
3. **Watchlist** — candidates in Low/High  
4. Drill 1–2 symbols → **Option Discovery** (structure)  
5. Stop before execution (D10)

## Agent protocol

- Batch: `.claude/skills/batch-execution/SKILL.md`
- Per phase: MCP `create_session` then work then `report_phase_progress`
- UI Chinese dialogue; UI strings English
- Dense UI mandatory for P3
