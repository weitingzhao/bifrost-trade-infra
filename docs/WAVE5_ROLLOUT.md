# Wave 5 rollout — Trade Celery retirement and queue cleanup (bifrost-core v0.14.0)

Owner-facing runbook for Wave 5 runtime cleanup.

## What ships

| Item | Change | Repos |
|------|--------|-------|
| A | Celery/Flower frontend surfaces and Trade API worker/queue endpoints removed; `/api/ops/` remains routed to `api-monitor:8765` | `bifrost-trade-frontend`, `bifrost-trade-api`, `bifrost-trade-infra` |
| B | Trade worker Celery runtime removed; market ingest now uses Kubernetes control + Plugin PG-as-broker workers | `bifrost-trade-worker`, `bifrost-trade-api` |
| C | Celery config, image dependencies, compose services, verification probes, and redis-queue manifests removed | `bifrost-trade-infra` |
| Core | `celery_redis_url_from_config` and Celery monitor roll-up removed | `bifrost-core` **0.14.0** |

**Retained:** market-ingest roots and Kubernetes executor, Ops authentication tokens, audit persistence, control profiles, daemon scale guard, and the `api-ops` Service/RBAC compatibility alias.

**Deferred:** deleting the already-running `redis-queue-stg` / `redis-queue-prod` objects and their persisted data from the live cluster is Phase 8 work after Owner sign-off. Wave 5 removes desired-state references so they cannot be recreated by normal delivery.

## Prerequisites

```bash
cd bifrost-trade-core && grep '^version' pyproject.toml       # 0.14.0
cd bifrost-trade-worker && rg -n 'celery|flower' pyproject.toml src
cd bifrost-trade-api && rg -n 'celery_redis_url_from_config' src
cd bifrost-trade-infra && grep BIFROST_CORE_REF .env.example  # v0.14.0
```

Before rollout:

1. Confirm D10 remains `BLOCKED`; do not scale the trading daemon up.
2. Confirm market-ingest enqueue, Ops auth capabilities, and audit writes pass in DEV.
3. Capture `redis-queue-stg` / `redis-queue-prod` state for the Phase 8 teardown record; do not delete them during this wave.

## Delivery path

Use the existing Tekton delivery pipelines. The `CELERY_RETIRED` prune list intentionally remains in `task-deliver-stg.yaml` to remove resurrected workloads.

1. Tag and push `bifrost-core` `v0.14.0`.
2. Build Trade API/worker images without Celery or Flower dependencies.
3. Deliver STG and verify `/api/ops/` through the `api-ops` compatibility Service backed by `api-monitor`.
4. Run Owner sign-off for market ingest, auth, audit, and daemon freeze.
5. Deliver PROD using the same artifacts.
6. Schedule physical redis-queue deletion separately in Phase 8.

## Verify

```bash
cd bifrost-trade-infra

kubectl kustomize k8s/overlays/dev >/dev/null
kubectl kustomize k8s/overlays/stg >/dev/null
kubectl kustomize k8s/overlays/prod >/dev/null

rg -n 'redis-queue|CELERY_BROKER|celery-worker|flower|ops_port|celery_redis_url' \
  config/ k8s/data/redis/ nginx/ .env.example Makefile

./scripts/k3s/verify-phase-b-stg-v2.sh
./scripts/k3s/verify-w10-observability.sh
```

Expected residue: Tekton `CELERY_RETIRED` only when searching the full repository. Historical migration documents may still describe the retired runtime.

## Rollback

- Application rollback: redeploy the previous Wave 4 API/worker image set and restore the prior config maps.
- Manifest rollback: revert the Wave 5 infra commit to restore redis-queue desired state and legacy verification definitions.
- Data rollback: no queue data is deleted in Wave 5. Phase 8 must take its own backup/sign-off before deleting live queue objects.
- D10 guard: rollback must not scale the trading daemon or remove observe-safe/scale-zero protections.

## Sign-off checklist

- [ ] `bifrost-core v0.14.0` tagged and available to image builds
- [ ] DEV/STG/PROD kustomize builds pass
- [ ] `/api/ops/` resolves through `api-monitor:8765`
- [ ] Market ingest, auth, and audit paths pass
- [ ] No Celery/Flower workloads are delivered
- [ ] Owner approves Phase 8 redis-queue teardown separately
