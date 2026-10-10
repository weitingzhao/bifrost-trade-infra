# Data integrity audit — 2026-10-10

Read-only inspection of the DEV gateway, shared Golden Source using
`agent_reader`, and source readers. Closed session: 2026-10-09; Research API
0.205.0. No data repair, service restart, release or subscription change.
TD-274 was committed separately: frontend `43477399`, infra `d7f3a56`.

## Findings in business order

| Finding | Current evidence | Business consequence | Work |
|---|---|---|---|
| Warm-up NULLs counted as readable IV lenses | Coverage reports 702/725 for both IV lenses; latest rows within the API's seven-day window have 631 non-NULL ranks/percentiles and 71 NULLs. APT has 2 sessions; its IV Rank exhibit is fresh with NULL rank and percentile, without a warm-up caveat. | Coverage says 96.8% while effective numerical coverage is 87.0%. A user enters a supposedly readable face and finds no verdict. | TD-302, recommended next implementation |
| CTVA split adjustment remains wrong | 09-30 close 77.65 → 10-01 12.57; adjusted and unadjusted closes remain equal through 10-09. RV20 on 10-09 = 6.48478553 (~648.5% annualised), VRP20 = -5.8814841. | Return-based screens and volatility readings can be numerically present but misleading. | Existing TD-149; respect its 10-16 review/Owner-approved repair boundaries |
| Historical term coverage is incomplete | 50–100 DTE ATM-IV name-days: week 06-22 2857/3234 (88.3%); 08-03 59/3223 (1.8%); 08-10 64/3159 (2.0%); 09-28 3252/3349 (97.1%); 10-05 3229/3469 (93.1%). | Current coverage cannot establish historical backtest completeness. Missing periods select which conditions can be tested. | Existing TD-172 |
| Long IV cone remains withheld | API: SPY 90-day tenor reads 35/252 sessions; NVDA 43/252, both below the 60-session minimum. No 180-day tenor is served. The current 7/30-day tenors each read 252 sessions. | Calendar/long-tenor comparisons have less evidence than short-term analysis. | Existing TD-142 |
| Term structure cannot enter screening | AAL's term-slope exhibit is fresh for 10-09, near 28 DTE / far 70 DTE, eight fitted expiries; coverage still declares `term_slope` unscreenable because no set-based reader exists. | Existing data works one name at a time but cannot drive discovery/filtering. | TD-301 |
| Doctor misstates recovered failures as lost records | Cached Doctor reports 131 failed option_daily jobs and says rows were trimmed. SQL finds all 131 originals, all with transient HTTP 401 and three attempts (22:59:56–23:01:13Z on 10-09); all 131 newer jobs with the same payload hash completed by 02:30:34Z on 10-10. 64 contracts have traded daily bars; successful zero-bar contracts are not automatically data loss. | A recovered incident appears as an unrecoverable gap. The retained error evidence is hidden by the actionable-retry filter. | TD-300 |

## Current daily collection is broadly reaching analysis

The current option universe has 725 names: 22 resident, 628 core, 75 edge.
Nineteen have no option-contract catalogue rows; the Doctor's optionable
denominator is 706, not 725. Its whole-chain checks validate 110544/110550
live contracts; its windowed checks validate 681/681 names with a live chain
for the session. Windowed collection is intentionally not a full strike chain.
These checks establish collection presence, not complete Greeks, every tenor,
or sufficient historical depth.

| Tier | Universe | Stock close | OI | GEX | VRP | SVI surface | Traded option bars |
|---|---:|---:|---:|---:|---:|---:|---:|
| resident | 22 | 21 | 22 | 22 | 21 | 22 | 22 |
| core | 628 | 628 | 625 | 624 | 625 | 625 | 623 |
| edge | 75 | 75 | 56 | 55 | 73 | 53 | 49 |

Counts above are exact distinct names in the 10-09 tables, restricted to the
current universe. Missing SPX stock close is a subscription boundary; Doctor
states its derived SPYx10 spot is adequate for strike placement, not an IV
solve. Core GEX gaps are CPAY, GRML, NVR, VYLR: CPAY's catalogue first landed
10-10 06:20Z (after the batch); GRML/NVR have no contract rows and prior void
records; VYLR has 88 OI rows whose total OI is zero, so suppressing GEX is
consistent with the exposure guard. These are not four identical engine bugs.

GEX name coverage rose 675 → 701 from 10-01 to 10-09. Surface coverage rose
674 → 700. Current-day bar counts or a globally recent `computed_at` still do
not measure the full historical decision window.

## Explicit boundaries and safeguards that are working

- The capability API identifies option trades/quotes as outside the current
  plan. Flow has 702 OI/volume-proxy rows on 10-09 and zero genuine tape rows;
  coverage's `order_sentiment=0` is expected, not a failed daily collector.
  `every_face=0` follows from requiring that unavailable lens.
- IV percentile computation withholds scores below 126 sessions: 702 stored
  rows, 631 numerical scores, zero premature non-NULL scores below the gate.
  The problem is the coverage reader, not fabrication by the engine.
- Slot-specific freshness rows now exist for calendar, corporate,
  fundamentals-rotate, option-refresh and reference. TD-101's original shared
  freshness defect is not reproduced by this snapshot.
- Signal Health reports `overall=ok` because its measured tables are fresh.
  It is not a global completeness verdict. Its canonical-P&L row count is an
  estimate; the dominant quality is `iv_interpolated`, not executable fills.

## Follow-up and limits

Start with TD-302: count usable non-NULL readings, preserve missing versus
warm-up semantics, and add regression tests for a present-but-NULL row. Then
TD-301 connects existing term data to discovery; TD-300 separates historical,
retained, recovered and still-actionable failures.

TD-172/TD-142 need a bounded backfill proposal (symbols, sessions, contracts,
expected outputs) before any write. Do not upgrade subscriptions or reinterpret
proxy flow as tape. This pass did not exhaustively audit NAV/commission history,
all intraday sessions, SEC/fundamental historical coverage, or every Greek's
numerical correctness. Local raw endpoint responses are outside Git; only
aggregate, public-market evidence is recorded here.

Reproduction: `scripts/audit-data-integrity.sql`, run with psql as
`agent_reader` against `bifrost_golden_source`; API reads are `/research/screen/coverage`,
`/research/signal-health`, `/research/exhibit/{lens}`, `/research/volatility/iv-cone`
under `/api/plugin/research`, and `/market/doctor?probes=false` /
`/market/capabilities` under `/api/plugin/market-data` on the DEV gateway.
