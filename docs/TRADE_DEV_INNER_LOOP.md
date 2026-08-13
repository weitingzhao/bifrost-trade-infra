# Trade DEV Inner Loop Contract

**Program:** `trade-dev-inner-loop`  
**Status:** active (Owner sign-off pending)  
**Catalog:** `bifrost-platform/console/src/lib/architecture/tradeDevInnerLoopCatalog.ts`  
**Skill:** `.cursor/skills/trade-dev-inner-loop/SKILL.md`

This document is the authoritative Product-mode contract for day-to-day Trade UI development against K3s `bifrost-dev`. Live trading remains **D10 BLOCKED**.

---

## Locked decisions (D-IL*)

| ID | Decision |
|----|----------|
| **D-IL1** | UI default acceptance = local Vite `:5173` + `.env.development.local` → `http://192.168.10.73:30882` (`bifrost-dev`) |
| **D-IL2** | Business ledger freshness = CNPG `trigger_data_clone` → `bifrost_dev` (optional `bifrost_stg`) |
| **D-IL3** | Market Live = shared `redis-ib` + DEV `api-market` reading `redis_ib`. **Forbidden:** clone `redis-live-prod` → `redis-dev` |
| **D-IL4** | Satellite / Prod publish = **L2 gate only** — not daily visual regression |

### Non-goals

- Do not dump `redis-live-prod` into `redis-dev`
- Do not pin local FE long-term to Prod writable APIs
- Do not unlock D10 / do not scale daemon for live trading
- Do not change Prod write paths “for developer convenience”

---

## Acceptance tiers (L0 / L1 / L2)

| Tier | Name | What it proves | Typical tools |
|------|------|----------------|---------------|
| **L0** | Observe | Topology + freshness + Live path health are known | `get_data_freshness`, `make assert-redis-ib-topology`, `make probe-dev-live-readiness`, `bdev status` / `list_dev_sessions` |
| **L1** | Actuate (DEV) | Non-prod data refresh + DEV consumer bounce; local FE smoke | Owner-gated `trigger_data_clone`, `rollout_restart` DEV `api-*`, Vite smoke pack |
| **L2** | Publish gate | Code reached STG/Prod via delivery pipelines | `git push` → Tekton `bifrost-deliver-stg` → smoke → Owner promote → Prod |

**Rule:** Daily UI acceptance stops at **L0+L1 on local Vite**. Prod browser refresh is **never** the accept surface for feature work (D-IL4).

---

## Redis dual-bus model

```
┌─────────────────────┐     ┌──────────────────────────────┐
│ CNPG bifrost_dev    │     │ redis-ib (data NS, shared)   │
│ ledger / config /   │     │ ticks · account · operator   │
│ strategy tables     │     │ health hashes                │
└─────────┬───────────┘     └──────────────┬───────────────┘
          │                                │
          ▼                                ▼
   DEV api-* (PG)                 DEV api-market (redis_ib)
          │                                │
          └────────────┬───────────────────┘
                       ▼
              Local Vite :5173
         (env → 192.168.10.73:30882)
```

| Bus | Role | Refresh mechanism |
|-----|------|-------------------|
| **PostgreSQL `bifrost_dev`** | Business ledger (instances, ledger, gates, history) | `trigger_data_clone` from `bifrost_prod` |
| **`redis-ib`** | Live market / account bus from IB Gateway Plugin | Live Gateway writers — **not** RDB dump from `redis-live-prod` |
| **`redis-live-{env}` / `redis-dev`** | Env Celery/legacy live Redis | Isolated; **do not** use as Live accept path for Market |

Trade NS `bifrost-dev` exposes short name `redis-ib` via ExternalName → `redis-ib.data.svc.cluster.local` (see `bifrost-platform-plugin/k8s/external-names/bifrost-dev/redis-ib.yaml`).

---

## Local FE presets (D-IL1)

| File | Purpose |
|------|---------|
| `.env.development.k3s` | Preset: all Trade APIs → `192.168.10.73:30882` |
| `.env.development.local` | Vite loads this (gitignored / local override) — keep aligned with k3s preset for inner loop |
| `.env.development` | Local docker/compose API ports — **not** default accept path |

```bash
cd bifrost-trade-frontend
npm run dev:k3s          # copies k3s preset → .env.development.local, then vite
# or: bdev restart trade-ui   # session should use same env
```

trade-ui bdev session: Vite on `:5173`; API base must be NodePort `30882`, not Prod ingress.

---

## Smoke page pack (local accept)

Run with Vite at `http://127.0.0.1:5173` and APIs on `30882`.

### 1) Strategy → Instances

| Check | Pass | Fail signal |
|-------|------|-------------|
| Page loads without blank shell | Table/empty state renders | Hard error / infinite spinner |
| Instance list reflects `bifrost_dev` | Rows or explicit empty from API | 5xx / CORS / wrong host |
| Open one instance detail | Inspector/drawer shows fields | Stale schema errors after clone |

### 2) Market → Live

| Check | Pass | Fail signal |
|-------|------|-------------|
| Live page connects | Quotes or structured empty/watchlist hint | Silent blank |
| Failure class readable | Copy distinguishes PG / Gateway / api-market (see Failure UX) | Generic “error” only |
| On-demand symbol (if Gateway up) | Tick appears or subscribe ack | See P11 watchlist bridge |

### 3) Portfolio / Ledger (or equivalent ledger surface)

| Check | Pass | Fail signal |
|-------|------|-------------|
| Ledger/history query | Rows or empty match DEV PG | Empty after known Prod activity → freshness issue |
| Filters work | Segment/Select update query | Points at Prod API accidentally |

**Pass rule:** All three pages usable on local Vite against DEV. Fix FE bugs here before any STG/Prod publish.

---

## PG freshness playbook (D-IL2) — Owner-gated

**Agent default:** read-only observe. **Do not** call `trigger_data_clone` unless Owner confirms an admin window.

### Observe

1. MCP `get_data_freshness` (or Console → Rocket → Cluster → Postgres → Data Freshness)
2. Record for `bifrost_dev`: `verdict`, `lag_vs_prod_days`, `last_clone_at`, `age_days` / wall age in `detail`
3. Inner-loop cadence: prefer `last_clone_at` within **≤7 days**, or clone on-demand before ledger-heavy UI work

### Actuate (Owner)

1. Prefer **Full** clone with `targets=["bifrost_dev"]` first (lower blast radius than dual-target)
2. MCP: `trigger_data_clone` with `confirm=true` and `confirmation_token=CLONE-FROM-PROD`
3. Poll `get_data_clone_status` until `done` | `failed` (concurrent → HTTP 409)
4. Optional: also clone `bifrost_stg` in a separate Owner window

### Post-clone consumer bounce

PG connections / statement caches may hold pre-clone views:

```bash
# Documented Makefile wrapper (DEV namespace only)
cd bifrost-trade-infra
make bounce-dev-apis-after-clone
# Underlying: Platform MCP rollout_restart_deployment for api-* in bifrost-dev
# Or Console Cluster → rollout restart DEV Trade API deployments
```

Safe scope: `bifrost-dev` `api-monitor`, `api-market`, `api-trading`, `api-strategy`, `api-portfolio`, `api-ops`, `api-docs`, `api-massive`, `api-research` (names as deployed). **Never** bounce Prod as part of this playbook.

### Cadence

| Signal | Action |
|--------|--------|
| `last_clone_at` ≤ 3d | Usually skip clone |
| 3–7d | Soft warning — clone before ledger-heavy work |
| \> 7d or Owner needs Prod rows | Owner window → Full clone → bounce |
| Briefing STALE (≥7d lag) | Same playbook; see `DATA_SERVICES_AGENT_FLOW` |

Aligns with `dataLayerCatalog.ts` → `DATA_FRESHNESS_BRIEFING_NOTE` and Program `trade-dev-inner-loop`.

### Selective vs full clone (risks)

| Mode | When | Risks |
|------|------|-------|
| **Full** (recommended for inner loop) | DEV ledger looks wrong / schema drift / first refresh | Longer dump/restore; still safer consistency |
| **Selective** | Tiny table set, Owner knows FK graph | Orphan FKs, missing join parents, partial gate/strategy graphs, false “empty” UI |

**Recommendation:** Full → `bifrost_dev`. Use selective only with explicit table list + Owner acceptance of partial consistency.

### Metric nuance (P16)

- API `verdict` uses **`lag_vs_prod_days`** (non-prod vs prod activity), not wall-clock age alone.
- Prod and DEV can both show old `wall_age` while `lag_vs_prod=0` → verdict `fresh`.
- Inner-loop operators should still watch **`last_clone_at`** (≤7d cadence) even when lag badge is green.

---

## Live path (D-IL3)

### Topology assert

```bash
cd bifrost-trade-infra
make assert-redis-ib-topology          # needs kubeconfig
make assert-redis-ib-topology DRY_RUN=1
```

Checks:

- Manifest ExternalName target is `redis-ib.data.svc.cluster.local`
- Live `bifrost-dev` Service `redis-ib` is ExternalName (when cluster reachable)
- Script refuses any “clone redis-live-prod → redis-dev” guidance (hard fail message)

### Live readiness probe

```bash
make probe-dev-live-readiness          # HTTP probes against 30882 + platform-api when up
make probe-dev-live-readiness DRY_RUN=1
```

| Color | Meaning |
|-------|---------|
| **Green** | api-market health OK + quotes path responds; Gateway/redis-ib evidence OK or skipped with note |
| **Yellow** | Partial: API up but no ticks / Gateway degraded / watchlist empty |
| **Red** | api-market unreachable or topology assert failed |

### Watchlist / on-demand bridge (empty after clone)

Clone refreshes **PG**, not Gateway subscriptions.

1. Open Live / Watchlist on local Vite
2. If list empty: add symbols in UI (writes DEV PG watchlist)
3. Gateway on-demand STK subscribe should populate `redis-ib` ticks (IB Gateway Plugin dogfood path)
4. If still empty: run Live readiness probe — distinguish empty watchlist vs Gateway down vs api-market down

### Failure UX copy (English — Agents / Console)

| Class | User-facing hint | Operator action |
|-------|------------------|-----------------|
| **PG stale / missing ledger** | “DEV ledger may be behind Prod. Refresh bifrost_dev (Data Clone), then reload.” | `get_data_freshness` → Owner clone → bounce APIs |
| **IB Gateway / redis-ib down** | “Live bus unavailable (Gateway or redis-ib). Quotes paused — ledger pages may still work.” | Subcontractors → IB Gateway; assert redis-ib ExternalName; check TWS |
| **api-market down** | “Market API unreachable on bifrost-dev. Check :30882 /api/market health.” | `rollout_restart` DEV `api-market`; ingress/NodePort |

Do not collapse these three into a single “Live broken” string.

---

## Dogfood path (Instances-class change)

Evidence template (fill when validating a FE change):

1. `npm run dev:k3s` → `http://127.0.0.1:5173`
2. Confirm Network tab hosts are `192.168.10.73:30882` (not Prod)
3. Change Instances UI → smoke pack § Instances
4. If ledger looks wrong → freshness playbook (Owner), not Prod FE
5. Only after local pass: pre-push → push → STG (L2)

Uncommitted FE work is fine for dogfood notes — **do not** force commit for this Program.

---

## Publish checklist (D-IL4)

| Step | Action | Notes |
|------|--------|-------|
| 1 | Local accept (L1 smoke pack) | Required |
| 2 | `scripts/agent-pre-push.sh` / lint+build | FE |
| 3 | `git push` | Unpushed = **Prod unchanged** |
| 4 | Tekton / Console `bifrost-deliver-stg` | STG smoke |
| 5 | Owner promote + release gate | Prod |
| 6 | Prod browser | **L2 confirmation only** — not daily visual QA |

---

## Commands quick reference

```bash
# Observe
# MCP: get_data_freshness · list_dev_sessions
cd bifrost-trade-infra && make assert-redis-ib-topology DRY_RUN=1
cd bifrost-trade-infra && make probe-dev-live-readiness DRY_RUN=1

# Local FE
cd bifrost-trade-frontend && npm run dev:k3s

# Owner-gated (do not auto-run)
# MCP: trigger_data_clone · get_data_clone_status
# make bounce-dev-apis-after-clone
```

---

## Related authorities

- Ops Console Governance catalogs: `tradeDevInnerLoopCatalog.ts`, `dataLayerCatalog.ts`, `agentProtocolCatalog.ts`
- IB Gateway Plugin: `ibGatewayPluginCatalog.ts` · ExternalName manifests in `bifrost-platform-plugin`
- Vision V1 history: Dual Flywheel Vision archive (SIGNED) — this Program operationalizes daily habit on top of V1
