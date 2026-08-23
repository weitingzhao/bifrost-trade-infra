# Trade / Platform secrets runbook

Secrets must not live in git-tracked ConfigMap YAML. Use K8s Secrets + env overrides.

## Source of truth

| Secret | Where | Env keys consumed by code |
|--------|-------|---------------------------|
| Trade NS `bifrost-{dev,stg,prod}-secrets` | gitignored `k8s/base/secrets/bifrost-*-secrets.yaml` | `REDIS_IB_*`, `REDIS_MASSIVE_*`, `PGPASSWORD`, `GOLDEN_SOURCE_PASSWORD`, `OPS_*`, `MASSIVE_API_KEY` / `POLYGON_API_KEY`, `MARKET_DATA_WRITE_TOKEN` |
| Plugin `redis-ib-acl` | `bifrost-platform-plugin` `.env` → `make install-redis-ib` | ACL file on redis-ib |
| Platform `redis-ib-platform` | gitignored Secret in `bifrost-platform-{stg,prod}` | `REDIS_IB_PLATFORM_PASS` |
| Plugin `redis-massive-acl` | market-data plugin `.env` → `install-redis-massive.sh` | ACL file on redis-massive |
| Local Compose | infra `.env` | same env keys |

Examples (placeholders only): `k8s/base/secrets/bifrost-*-secrets.example.yaml`.

## First-time / refresh from current YAML (before scrub)

```bash
cd bifrost-trade-infra
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
python3 scripts/materialize_k8s_trade_secrets.py --apply
```

This writes gitignored Secret files and applies them to `bifrost-{dev,stg,prod}`.

## After ConfigMap scrub / overlay change

```bash
kubectl apply -k k8s/overlays/stg   # or dev / prod
kubectl -n bifrost-stg rollout restart deploy/api-monitor deploy/api-account deploy/api-market deploy/api-research
kubectl -n bifrost-stg rollout restart deploy/daemon deploy/account-sync
```

## Rotate redis-ib / redis-massive

1. Generate new passwords in plugin `.env` (`REDIS_IB_TRADE_PROD_PASS`, `REDIS_MASSIVE_TRADE_PROD_PASS`, …).
2. `make -C ../bifrost-platform-plugin install-redis-ib` (and market-data `install-redis-massive.sh`).
3. `make -C ../bifrost-platform-plugin sync-redis-ib-secrets` (updates Trade Secrets + platform `.env` only — **not** tracked YAML).
4. `python3 scripts/materialize_k8s_trade_secrets.py --apply` (or kubectl apply Secrets).
5. Rollout Trade consumers + platform-api + ib-gateway + polygon-ws-ingestor.

## Rotate Ops tokens

1. Generate new operator/admin tokens.
2. Put them in gitignored `bifrost-*-secrets.yaml` (`OPS_OPERATOR_TOKEN` / `OPS_ADMIN_TOKEN`) and local `.env`.
3. `kubectl apply` Secrets → restart `api-monitor` (ops absorbed).
4. Re-Authenticate in Trade UI.

## Rotate Polygon API key

1. Rotate in Polygon console (cannot be done from this repo alone).
2. Update `MASSIVE_API_KEY` / `POLYGON_API_KEY` in Secrets + `.env`.
3. Restart `api-research`.

Note: after YAML scrub, the key lives only in K8s Secret / `.env`. Git history still has the old value until it is rotated at the vendor.

## Redis ACL install notes

`install-redis-ib.sh` strips `#` comment lines from `acl.conf.example` — Redis ACL files reject comments and will CrashLoop if they remain.

## Rotate Postgres (`bifrost` user)

1. Change password via CNPG / `ALTER ROLE` (and `bifrost-postgres-app` Secret if applicable).
2. Update `PGPASSWORD` + `GOLDEN_SOURCE_PASSWORD` in Trade Secrets + `.env`.
3. Restart all Trade API/worker Deployments.

## Sync scripts (no password write-back)

- `scripts/sync_dev_config.sh` / `sync_prod_config.sh` — write empty `postgres.password` / `massive.api_key`.
- `scripts/sync_redis_ib_trade_config.sh` — updates gitignored Secrets only.

## Verify ConfigMap has no plaintext

```bash
kubectl -n bifrost-stg get cm bifrost-config -o yaml | grep -E 'password:|api_key:|token:' | head
# Expect empty quotes / tokens: [] only — never long hex literals.
```

Do **not** rewrite git history; rotation makes leaked historical values dead.
