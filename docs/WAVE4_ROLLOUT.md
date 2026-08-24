# Wave 4 rollout — Flex token Secret + ops_audit_log partition (bifrost-core v0.13.0)

Owner-facing runbook for Wave 4 DB hygiene.

## What ships

| Item | Change | Repos |
|------|--------|-------|
| A | Flex tokens: env `FLEX_*_TOKEN` (K8s Secret `bifrost-flex-tokens`) preferred over Trade DB plaintext; summary exposes `source` | `bifrost-flex-query` **0.4.0** |
| B | `ops_audit_log` → `PARTITION BY RANGE (timestamp)` + `timestamptz`; 90-day drop on `_ensure_tables` | `bifrost-core` **0.13.0**, `bifrost-trade-api` audit_store |
| Clone | `pg_dump` uses `public.ops_audit_log*` pattern (parent + partitions) | `bifrost-platform` |

**Out of scope:** `contract_quote_live` removal, `account_execution_*` natural keys, Alembic, pg_partman.

**Celery note:** Trade worker Celery/beat was already retired. Retention runs via `_ensure_tables()` and `bifrost-trade-core/scripts/db/drop_ops_audit_partitions.py`.

## Prerequisites

```bash
cd bifrost-trade-core && grep '^version' pyproject.toml   # 0.13.0
cd bifrost-trade-api && grep bifrost-core pyproject.toml  # >=0.13.0
cd bifrost-platform-plugin-flex-query && grep '^version' pyproject.toml  # 0.4.0
cd bifrost-trade-infra && grep BIFROST_CORE_REF .env.example  # v0.13.0
```

Put Flex tokens in trade-infra `.env`:

```bash
IB_FLEX_HOST_TOKEN=...
IB_FLEX_SECONDARY_TOKEN=...
make sync-flex-tokens
```

## Delivery path

Same Tekton pipeline as Wave 2/3 (`bifrost-deliver-stg` / `-prod`).

1. Tag & push `bifrost-core` `v0.13.0`
2. Build/push `bifrost-flex-query:0.4.0` and apply plugin k8s (envFrom already in base)
3. Deliver STG API/worker images → restart DEV on `:stg` → verify
4. Deliver PROD → verify

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
kubectl -n bifrost-dev rollout restart deploy/api-account deploy/api-monitor
kubectl -n plugin-flex-query rollout restart deploy/flex-query-api deploy/flex-query-worker
```

API `_ensure_tables` migrates heap `ops_audit_log` → partitioned on first connect.

## Verify

```bash
cd bifrost-trade-infra
./scripts/verify_wave4_flex_secret.sh
./scripts/verify_wave4_audit_partitioned.sh all
./scripts/verify_wave4_audit_retention.sh all
# Optional clone preservation (after Owner clone):
# ./scripts/verify_clone_audit_preservation.sh dev seed
# ... Owner runs clone ...
# ./scripts/verify_clone_audit_preservation.sh dev verify --clean
```

## Rollback

- Item A: remove/empty Secret → Plugin falls back to DB columns (non-breaking).
- Item B: partitioned table is one-way after rename-swap; restore from CNPG backup if needed. API float epoch contract unchanged.

## Sign-off checklist

- [ ] `bifrost-core v0.13.0` tagged & pushed
- [ ] Plugin `bifrost-flex-query` 0.4.0 image built & rolled
- [ ] `bifrost-trade-api` images delivered (audit_store `to_timestamp`)
- [ ] `bifrost-platform` data_clone wildcard patch deployed
- [ ] `make sync-flex-tokens` applied; verify_wave4_flex_secret green
- [ ] verify_wave4_audit_partitioned green on DEV/STG/PROD
- [ ] `MIGRATION_TRACKING.md` Wave 4 entry signed off
