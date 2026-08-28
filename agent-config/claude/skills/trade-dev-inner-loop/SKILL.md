---
name: trade-dev-inner-loop
description: >-
  Trade DEV Inner Loop (D-IL1–D-IL4) — 本机 Vite :5173 对 K3s bifrost-dev API 的开发验收闭环。
  Use when executing program trade-dev-inner-loop, or when Owner asks about DEV inner loop,
  本地验收, dev:k3s, :30882, or where a frontend change should be accepted before release.
---

# SKILL — trade-dev-inner-loop

Execute Program `trade-dev-inner-loop` (Trade DEV Inner Loop).

## Authority

1. `bifrost-trade-infra/docs/TRADE_DEV_INNER_LOOP.md` — contract
2. `bifrost-platform/config/programs/active/trade-dev-inner-loop.yaml` — phases
3. `bifrost-platform/console/src/lib/architecture/tradeDevInnerLoopCatalog.ts` — Console/Agent pack
4. Locked: D-IL1–D-IL4 · D10 BLOCKED

## Repos to touch

| Repo | Typical changes |
|------|-----------------|
| `bifrost-platform` | Program YAML, catalogs, Agent Protocol, Vision surface |
| `bifrost-trade-frontend` | AGENTS/CLAUDE, `dev:k3s`, env presets |
| `bifrost-trade-infra` | Contract doc, Makefile, assert/probe/bounce scripts |

## Verify commands

```bash
test -f bifrost-trade-infra/docs/TRADE_DEV_INNER_LOOP.md
cd bifrost-trade-infra && ./scripts/assert_redis_ib_topology.sh --dry-run
cd bifrost-trade-infra && ./scripts/probe_dev_live_readiness.sh --dry-run
cd bifrost-trade-frontend && npm run lint   # if package.json/scripts changed
cd bifrost-platform/console && npm run type-check   # if catalog/UI changed
```

## Hard rules

- Do **not** auto `trigger_data_clone` without Owner admin confirm
- Do **not** dump redis-live-prod → redis-dev
- Do **not** unlock D10 / scale daemon live trading
- Do **not** git commit/push unless Owner asks
- UI accept = local `:5173` → `30882`, never Prod browser as daily QA
