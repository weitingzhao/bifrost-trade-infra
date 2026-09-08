---
name: market-data-subscription-focus
description: >-
  Massive Plugin subscription focus — exploit Options Starter, Stocks Starter and
  Financials & Ratios fully before any upgrade; stop unentitled pulls. Use when
  executing program market-data-subscription-focus phases, or when Owner asks about
  Massive / Polygon entitlements, ingest dedup, snapshot OI, ratios / short data, or
  option history backfill.
---

# SKILL — market-data-subscription-focus

Execute Program `market-data-subscription-focus` (Massive Plugin, three subscriptions).

## Authority

1. `bifrost-platform-plugin-market-data/docs/SUBSCRIPTION_FOCUS_PROGRAM.md` — entitlement matrix, phase progress, Owner decisions
2. `bifrost-platform/config/programs/active/market-data-subscription-focus.yaml` — phases, verify_cmd, acceptance
3. Assessment page: https://claude.ai/code/artifact/727e00e9-5903-48cd-9c50-118171f1823a
4. Locked: D10 BLOCKED · unentitled data (trades / quotes / last-trade / indices) is not pulled until an upgrade

## Facts that shape every phase (measured 2026-09-06 in the API pod)

- Paid Starter = unlimited calls (15 requests in 0.9s, no 429). `tier: starter` is a soft 8 req/s per process; `polygon.rate_per_sec` / `burst` override.
- Stock aggregates rolling 5 years; option aggregates rolling 2 years; expired contracts enumerable to 2022.
- Ratios, short interest and short volume are fetchable full-market by date (1,000 / page). Two traps measured 2026-09-08: `ratios?date=D` **ignores D** and always returns the latest values, so ratio history cannot be backfilled, only accumulated forward; and `short-interest` with a 45-day lookback returns several settlements at ~15,000 rows each, so a low `max_pages` truncates it mid-alphabet while the job still reports success. Every whole-market handler now raises on `truncated` — treat a partial market as a failure, never a result.
- Vendor ratio coverage is ~5,000 tickers. The SEPA universe is larger, so ratio-condition coverage tops out near 75%; the shortfall is micro caps and recent listings the vendor computes no ratios for, not a bug.
- `/stocks/v1/float` and `/stocks/filings/*` return 404 — do not reintroduce them.
- Scheduling is Dagster (Research NS) → `POST /market/ingest/enqueue-slot`; Plugin CronJobs stay suspended.
- `raw_market.option_snapshot.snapshot_ts` is the **observation time** (EOD = 16:00 NY anchor of the session), not the contract's last trade — that is `last_trade_ts` (plugin 0.13.0 / Wave 9). A chain download only ever shows the current session, so a catch-up is truthful only before the next open: `trading_calendar.chain_session()` decides, and the handler answers `skipped: stale_session` for anything else.
- P4 backfills (Owner-approved 2026-09-08): `stock_daily` reaches back 5 years, but the plan's window **rolls** — the oldest day expires daily and anything past it answers "past historical entitlements", which is a plan boundary, not a defect. Option history goes through `option_backfill_plan`, one underlying-month per job (SPY and SPX each list 50,000+ contracts in two years); it reads `stock_daily` closes for the ±30% strike filter, so the stock backfill must land first.
- `raw_market.treasury_yield` holds the risk-free leg (7 tenors, free on every plan). Intraday chains run on a **New York** clock in Dagster, not UTC, and trim gives intraday rows their own 30-day window (EOD keeps 90 sessions).
- Health is per-session coverage, not row presence: each underlying's chain must cover >= 95% of its live `option_contract` rows; `stock_daily` / `stock_snapshot` floors are 12,000. `doctor.eod_critical` is what gates the Research dbt batch.
- **Doctor first, guess never**: `GET /market/doctor` = what the session should hold vs what it does, one prescription per gap; `POST /market/doctor/heal` executes them (write token). Console Doctor panel, MCP `market_data_doctor` / `market_data_heal` and Dagster `market_self_heal` (00:45 UTC Tue–Sat) all run the same prescriptions.

## Repos to touch

| Repo | Typical changes |
|------|-----------------|
| `bifrost-platform-plugin-market-data` | scheduler slots, handlers, dashboard verdict, DDL (P3, Owner-gated), backfill |
| `bifrost-research` | Dagster market schedules / RetryPolicy, dbt staging contracts (ratios, short_*) |
| `bifrost-trade-frontend` | Option Discovery: no unentitled vendor calls |
| `bifrost-platform` | program YAML, Console copy for retired routes |

## Verify commands

```bash
cd bifrost-platform-plugin-market-data && make lint && make test
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
kubectl -n plugin-market-data get deploy -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[0].image}{"\n"}{end}'
curl -s http://127.0.0.1:8780/api/v1/plugins/market-data/api/market/ingest/queue-dashboard | python3 -c 'import json,sys; print(json.load(sys.stdin)["husbandry"])'
curl -s http://127.0.0.1:8780/api/v1/plugins/market-data/api/market/doctor | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["session"], d["verdict"], d["summary"]); [print("-", f["severity"], f["title"], "→", f["fix"]) for f in d["findings"] if f["severity"] != "ok"]'
```

## Release path (Plugin is not under Argo)

push GitHub → `make -C bifrost-trade-infra k3s-sync-gitea-mirrors` → `kubectl -n cicd create -f` the
`pipelinerun-build-market-data.yaml` template with the new image tag → confirm the tag in
`192.168.10.73:30500/v2/bifrost-market-data/tags/list` → `kubectl apply -k k8s/base` → `make verify-market-data`.

## Hard rules

- Do **not** enqueue option-trades, I:SPX / I:VIX, trades / quotes / last-trade — 403 by plan
- Do **not** unsuspend Plugin husbandry CronJobs (Dagster owns the batch)
- Do **not** re-key `raw_market.option_snapshot`; Wave 9 settled it (observation time). Never write a `trade_date` the live chain no longer reflects
- Do **not** unlock D10 / scale daemon
- Weekend cron fires must skip session slots (fire-date gate); never "catch up" by re-fetching a done session
