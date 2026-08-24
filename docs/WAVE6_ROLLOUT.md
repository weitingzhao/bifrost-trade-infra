# Wave 6 rollout — Retire `ops_audit_log` (platform audit sink, bifrost-core v0.15.0)

Owner-facing runbook for Wave 6 DB hygiene + audit sink migration.

## What ships

| Item | Change | Repos |
|------|--------|-------|
| A | `POST /api/v1/audit/append` (operator) for Trade satellite ingest | `bifrost-platform` |
| B | `PlatformAuditClient` fire-and-forget → platform-api; `GET /ops/audit` removed | `bifrost-trade-api` |
| C | `ops.platform_audit` config + `PLATFORM_SATELLITE_AUDIT_TOKEN` + egress NetworkPolicy | `bifrost-trade-infra` |
| D | DROP `ops_audit_log` on `_ensure_tables()`; delete partition DDL/helpers | `bifrost-core` **0.15.0** |
| E | Remove `data_clone` ops_audit_log backup/exclude/restore | `bifrost-platform` |

**Retained:** market-ingest control plane, Ops auth tokens, `_audit()` call sites (sink changed).

**Removed:** `public.ops_audit_log` table, Trade PG persistence, `/api/ops/audit` read path.

## Prerequisites

```bash
cd bifrost-trade-core && grep '^version' pyproject.toml       # 0.15.0
cd bifrost-trade-api && rg 'platform_audit|ops/audit' src
cd bifrost-platform/api && go test ./internal/actuation/... ./internal/cluster/...
```

Before rollout:

1. Sync `PLATFORM_SATELLITE_AUDIT_TOKEN` — **same value** in:
   - Trade: `bifrost-{dev,stg,prod}-secrets` (api-monitor `envFrom`)
   - Platform: `bifrost-platform-satellite-tokens` in `bifrost-platform-{stg,prod}`
2. Deliver **platform-api** with `POST /api/v1/audit/append` before flipping Trade `platform_audit.enabled: true`.
3. D10 remains BLOCKED.

## Secret sync

```bash
# Platform NS (example STG)
kubectl apply -f k8s/overlays/platform-stg/bifrost-platform-satellite-tokens.yaml -n bifrost-platform-stg

# Trade NS — add PLATFORM_SATELLITE_AUDIT_TOKEN to existing bifrost-stg-secrets
kubectl -n bifrost-stg create secret generic bifrost-stg-secrets \
  --from-literal=PLATFORM_SATELLITE_AUDIT_TOKEN='<same-token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Delivery path

1. Tag and push `bifrost-core` `v0.15.0`.
2. Deliver platform STG/PROD with audit append endpoint + satellite token env.
3. Build Trade `api-monitor` with core 0.15.0 + platform audit client.
4. Deliver Trade DEV → smoke → STG → PROD.
5. Deliver platform `data_clone` cleanup (after core 0.15.0 landed in all envs).

## Verify

```bash
# Platform append (operator / satellite token)
curl -s -X POST http://127.0.0.1:8780/api/v1/audit/append \
  -H "Authorization: Bearer $PLATFORM_SATELLITE_AUDIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"actor":"smoke","action":"wave6_smoke","target":"test","status":"ok"}'

curl -s http://127.0.0.1:8780/api/v1/audit | jq '.records[0].action'  # wave6_smoke

# Trade — /ops/audit should 404
curl -s -o /dev/null -w "%{http_code}" "$TRADE_BASE/api/ops/audit"   # 404

# PG — table absent after api-monitor restart with core 0.15.0
psql -d bifrost_dev -c "SELECT to_regclass('public.ops_audit_log');"  # NULL

# Optional archive before rollout (STG/PROD)
pg_dump -Fc -t 'public.ops_audit_log*' bifrost_stg > ops_audit_log-stg-$(date +%Y%m%d).dump
```

## Rollback

- Trade: set `ops.platform_audit.enabled: false` — actuators work, audit stdout-only.
- Platform: revert audit append route; Trade falls back to `audit_sink_failed` logs.
- Core: rollback to `0.14.0` recreates partitioned DDL; restore from archive if needed.

## Sign-off checklist

- [x] `bifrost-core v0.15.0` tagged
- [x] Platform `POST /api/v1/audit/append` live STG+PROD
- [x] Satellite token synced Trade ↔ Platform
- [ ] Trade market-ingest control → record visible on `GET /api/v1/audit` (Owner manual)
- [x] `ops_audit_log` NULL in all Trade DBs
- [x] `data_clone` no longer references ops_audit_log (platform code; prod platform delivered)
- [x] STG/PROD legacy rows archived (PROD: `/tmp/ops_audit_log-prod-20260824.dump`)
