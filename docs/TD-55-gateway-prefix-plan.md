# TD-55 — one gateway prefix per process (migration plan)

Status: **Owner approved option B on 2026-10-04** (`/stocks/REQUEST-td55-gateway-prefix-plan-2026-10-04.md`,
"Owner 批复"): one prefix per process, add first, retire later. Phases A–B below are **B1** (implemented,
lane AB, not yet released); C–D are **B2** (after 7 days of zero traffic on the old prefixes; removal is a
separate Owner nod). Phase E is not planned.

### B1 as built

| Prefix | Process (Service) | Role |
|---|---|---|
| `/api/monitor` | api-monitor (`api-monitor`) | process prefix; ops at `/api/monitor/ops/*`, docs at `/api/monitor/research/docs/*` |
| `/api/account` | api-account (`api-account`) | **new** process prefix (`strip-api-account`) |
| `/api/market` | api-market (`api-market`) | process prefix |
| `/api/research` | api-research (`api-research`) | process prefix |
| `/api/docs`, `/api/ops` | api-monitor (`api-docs`, `api-ops`) | alias until B2 |
| `/api/trading`, `/api/strategy`, `/api/portfolio` | api-account (`api-trading`, `api-strategy`, `api-portfolio`) | alias until B2 |

- `make check-trade-gateway-routes` (`scripts/check_trade_gateway_routes.py`) renders the three overlays and
  checks every prefix above in both IngressRoutes and on every Host: route → Service:port, strip of exactly
  that prefix, Service selector → process. On `main` before B1 it reports the 8 missing `/api/account` routes.
- Callers moved: frontend (`devApiUrl`, `tradeFetch`, health board), platform (matrix, release smoke,
  Tier B, Satellite, data probe, probe bridge, Trade MCP, registry), Research (the `api-account` Service),
  release checks (`scripts/release/probes.json`, snapshot reads). Nothing removed.
- **Order:** infra first (an env without the `/api/account` route answers it with the SPA), then frontend,
  platform and Research.

### B2 measurement (Traefik per-route counts)

Traefik exposes no per-router metric here; `traefik_service_requests_total` is per route service, named
`<namespace>-<ingressroute>-<sha256(match)[:20]>@kubernetescrd`. `python3 scripts/check_trade_gateway_routes.py
--promql 7d` renders the overlays, hashes every alias route's `match` and prints the query (and one
`# service  env gateway host prefix` line per route to read the result). Run it through the apiserver proxy:

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
q="$(python3 scripts/check_trade_gateway_routes.py --promql 7d | tail -1)"
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$q")"
```

An empty result = zero requests on every alias route for 7 days. The query adds `(X unless X offset 7d)` to
`increase(X[7d])` because a series only appears on its first request and `increase()` never counts the sample
that creates it. Prometheus keeps 10 days. Traefik metrics do not see in-cluster callers that use the alias
**Services** by name (Research did, until 0.162.0): before deleting the Services, also run
`kubectl get deploy,sts,cronjob,job -A -o yaml | grep -nE 'api-(trading|strategy|portfolio|ops|docs)\.'` (expect no lines).

## Why

Four API processes answer under eight gateway prefixes. Each prefix is an alias, not a boundary:

| Process | Prefixes today | Alias Services |
|---|---|---|
| api-monitor (:8765, also serves docs and ops) | `/api/monitor`, `/api/ops`, `/api/docs` | `api-ops`, `api-docs` |
| api-account (:8769, serves trading, strategy, portfolio) | `/api/trading`, `/api/strategy`, `/api/portfolio` | `api-trading`, `api-strategy`, `api-portfolio` |
| api-market (:8772) | `/api/market` | — |
| api-research (:8773, the Trade research app) | `/api/research` | — |

What it has cost so far:
- **D10 guard hole (TD-07):** `/control/*` was reachable through `/api/ops` and `/api/docs`, which the preflight regex did not cover. Fixed by narrowing the alias routes, but every path-keyed rule still has to enumerate aliases.
- **Wrong URLs by agents:** `/api/account/health` (the process's own name) does not exist and falls through to the SPA; the Trade MCP advertised `/api/trading/positions`, which no app serves.
- **Health counted three times:** a probe catalog that lists `api-trading`, `api-strategy` and `api-portfolio` counts one healthy process as three.

Inside the apps, routes also repeat their domain, so a URL stutters:
`/api/research/research/*`, `/api/portfolio/portfolio/*`, `/api/market/market/holidays`, `/api/monitor/api/messages`; the singular `/api/strategy` sits over plural `/strategies`.

## Target

One prefix per process, named after the process:

| Process | Target prefix |
|---|---|
| api-monitor | `/api/monitor` (docs and ops paths move under it: `/api/monitor/ops/*`, `/api/monitor/research/docs/*`) |
| api-account | `/api/account` |
| api-market | `/api/market` |
| api-research | `/api/research` |

The internal route stutter is a separate, larger API change (phase E) and is not required for the prefix move.

## Phases

Each phase leaves everything working; the old names keep answering until phase D.

**A. Add the new prefixes as aliases** (infra only)
- IngressRoutes in `k8s/overlays/{dev,stg,prod}/trade-ingressroute.yaml` and `trade-ip-ingressroute.yaml`: add `PathPrefix(/api/account)` → `api-account` (strip `/api/account`). `/api/monitor` already reaches every docs and ops path.
- Verify with GET-only probes per env: each old path and its new twin answer the same JSON.

**B. Move every client to the new prefixes**
- Frontend: `src/lib/devApiUrl.ts` gets `accountUrl`; `tradingUrl` (19 call sites), `strategyUrl` (40) and `portfolioUrl` (12) become one helper; `src/lib/tradeFetch.ts` adds `account` to its Trade prefixes; `vite.config.ts` needs no change (it proxies `/api`).
- Platform: `api/internal/probe/probe.go` probes four processes, not eight prefixes (`/api/monitor/status`, `/api/account/health`, `/api/market/health`, `/api/research/health`); `satellite/service.go` and `promote/tier_b.go` read `/api/monitor/ops/...` instead of `/api/ops/...`; Console catalogs that name the old prefixes are updated text; the Trade MCP's `DOMAINS` lists four.
- Research: the in-cluster env (`TRADE_API_TRADING_URL`, `TRADE_API_STRATEGY_URL` in `k8s/{api,mcp,engines,orchestration}`) points at `api-account` instead of the alias Services. This rolls research-api and research-mcp; Dagster is outside Argo and needs a manual apply.
- Guard: `preflight.js` rule 2 already matches `/control/` under any prefix; add `/api/account` to its tests.

**C. Watch the old prefixes for one release**
- Traefik access logs (or a header middleware on the old routes) count who still calls `/api/trading|strategy|portfolio|ops|docs`. Stale browser tabs are expected for a while (an open tab keeps its old bundle).

**D. Retire the old prefixes**
- Remove their IngressRoute rules and the alias Services `api-trading`, `api-strategy`, `api-portfolio`, `api-ops`, `api-docs` once phase C shows no callers. Owner decision at that point, with the traffic numbers.

**E. (Optional, separate decision) De-stutter internal routes**
- Drop the repeated domain inside the apps (`/research/...`, `/portfolio/...`, `/market/holidays`, `/api/messages`) with both paths served for a version. This changes every FE call site and the OpenAPI paths, so it belongs with the contract track's legacy-key removal rather than with the gateway move.

## Order and risk

- A and B are additive and can ship in one Trade release plus one platform release. B's frontend part rides the next Trade deliver; the platform part rides a platform deliver; Research is its own manifest change.
- Nothing in A–C touches D10: no daemon, no control-route behaviour; only the paths change.
- Rollback at any phase before D: revert the client change; the old prefixes still answer.

## Decisions needed

1. Approve the target table (in particular `/api/account` as api-account's only prefix, and docs/ops moving under `/api/monitor`).
2. Approve phases A–C now; D after the traffic numbers.
3. Phase E: do it with the contract track later, or not at all.
