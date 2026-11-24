# Metric, rule and label names

Owner of this page: the metrics seat (`agent-config/charters/8-3-metrics.md`).
It writes down the names that already work, so a new scrape or rule fits the
ones before it and a page can take readings by name instead of by a hand-written
query. It is not a check: nothing fails on it. Making it a check would change
the referee (law 94) and goes to the Owner as a proposal.

## Metrics an app exports

- Prefix `bifrost_<area>_`, snake case, Prometheus base units:
  `_seconds`, `_bytes`, `_ratio` (0–1), `_total` for counters.
  Examples: `bifrost_bus_relay_published_total`, `bifrost_full_ci_red`.
- HTTP servers use the client library's `http_requests_total` and
  `http_request_duration_seconds` with a `handler` label (the route pattern,
  never the raw path).
- A third-party exporter keeps its own names (`cnpg_*`, `nats_*`, `loki_*`,
  `tekton_*`, `argocd_*`). Do not rename them in relabeling.

## Recording rules

- `bifrost_<area>:<what>[_<window>]`: area before the colon, the reading after it,
  window last (`_5m`, `_1h`, `_1d`).
  Examples: `bifrost_node:disk_busy_ratio_5m`, `bifrost_metrics:coverage_ratio`.
- Areas in use: `alerts`, `ci`, `http`, `metrics`, `module`, `node`, `pg`. A new area is fine; say
  in the rule's comment what it covers.

## Alerts

- `Bifrost<Thing><Condition>` in CamelCase: `BifrostLokiNotReady`,
  `BifrostPostgresInstanceMissing`. Two rules never share a name, even in
  different files (the Gitea pair was split on 2026-11-20 for this).
- Every alert has `severity` (`critical`, `warning`, `info`) and a `summary`
  annotation.

## Labels

- `namespace`, `pod`, `container` come from the scrape; do not overwrite them.
- `service` names the workload a series belongs to. ServiceMonitors get it from
  the Service. PodMonitors (no Service) set it by relabeling to the workload
  name, e.g. `service="platform-workers"`. Rules that group
  `by (namespace, service)` rely on it.
- `app.kubernetes.io/component` on each ServiceMonitor or PodMonitor must be one
  of the classes in `scripts/check_http_metrics_coverage.py`
  (`APP_COMPONENTS` / `INFRA_COMPONENTS`).
- Runtime keys outside Prometheus: `<namespace>/<workload>`, `node/<name>`,
  `host/<name>`.

## Names that predate this page

Left as they are because something reads them by name. Renaming one means
moving its readers in the same change.

| Name | Read by | Why it stays |
|---|---|---|
| `ComputePainDbDiskFlush`, `ComputePainDbReplication`, `ComputePainProdThrottle`, `ComputePainDbGuestLoad` | platform bus subscriptions (`rocket.yaml` `except: ComputePain`), `effect/problems.yaml` | routed to the compute seat by name prefix |
| `bifrost:traefik_empty_backend_503:total`, `bifrost:traefik_route_miss_404:total` | the two Traefik alerts in `bifrost-alerting-rules.yaml` | no area before the colon; would be `bifrost_traefik:…` |
| platform-workers `job="monitoring/bifrost-platform-workers"` (platform-api is `job="platform-api"`) | nothing found by name (2026-11-20) | `job` is left alone; `service` is the key to group on |
