# Wave 2 rollout — api-account picks up bifrost-core v0.11.0

Owner-facing runbook for delivering the Wave 2 DB hygiene changes to the
`api-account` pods across DEV → STG → PROD.

Wave 2 code is already merged in each repo (local commits) and DB schema was
migrated at `db-init` time by the core startup path, so this rollout is
purely about **replacing the `api-account` image** so the running pods use
the new readers/writers against the collapsed jsonb columns.

## What Wave 2 changed

| Change | Where | Runtime impact |
|---|---|---|
| `strategy_template_param` / `_characteristic` → `strategy_template.params_json` / `characteristics_json` | `bifrost-core/persistence/postgres/ddl.py` + readers/writers | `api-account` must run new code before serving `/api/strategies/templates` (old code SELECTs dropped KV tables) |
| `strategy_structure_meta` → `strategy_structure.meta_json` | same | same |
| `ops_audit_log` DDL moves from `bifrost-trade-api` into core | `audit_store.py` + core `ddl.py` | `api-monitor` (which runs the ops router) no longer emits DDL on the trade DB |
| `bifrost-core` version | `0.11.0` (local tag) | Consumers pin `>= 0.11.0` |
| Data clone excludes/preserves `ops_audit_log` | `bifrost-platform api/internal/cluster/data_clone.go` | Next `trigger_data_clone` will keep target-side audit trail |

## Prerequisites (verify once before starting)

```bash
# repos have Wave 2 commits
cd bifrost-trade-core       && git log -1 --oneline   # Wave 2 DB hygiene…
cd bifrost-trade-api        && git log -1 --oneline   # ops(audit_store)…
cd bifrost-trade-infra      && git log -1 --oneline   # env: pin BIFROST_CORE_REF…
cd bifrost-platform         && git log -1 --oneline   # cluster(data-clone)…

# core has v0.11.0 tag locally
cd bifrost-trade-core && git tag --list v0.11.0 --format='%(refname:short) %(subject)'
```

## Delivery path (Tekton `bifrost-deliver-stg` / `-prod`)

The `Dockerfile.api-stg` build **copies `bifrost-trade-core/src` directly**
into the image (no `pip install git+…`), so **you do not need to push
`v0.11.0` to GitHub** — but you *do* need to push commits to the
Gitea/Tekton mirror the pipeline reads from.

### DEV (fastest loop)

DEV `api-account` currently runs the `:stg` tag (registry
`192.168.10.73:30500/bifrost-api-account:stg`), so DEV picks up the same
image STG uses. Two paths:

1. **Piggy-back on the next STG delivery** (usual case). After STG delivery
   completes:
   ```bash
   export KUBECONFIG=~/.kube/bifrost-k3s.yaml
   kubectl -n bifrost-dev rollout restart deploy/api-account
   kubectl -n bifrost-dev rollout status  deploy/api-account --timeout=120s
   ```
2. **Fast-track DEV** by kicking a one-off STG-tag build from Ops Console →
   Program → **Deploy Mainline** → `bifrost-deliver-stg` → Run.

### STG

```
Ops Console → Program → Deploy Mainline → "bifrost-deliver-stg" → Run
```

Wait for the PipelineRun to reach `Succeeded=True` (Console shows Kaniko
build → crane retag → kustomize apply → rollout).

### PROD (L2 gate — Owner-only)

```
Ops Console → Program → Deploy Mainline → "bifrost-deliver-prod" → Run
```

L2 gate is guarded by the release-gate check (Tier A smoke on STG must be
green) — Console will refuse if STG hasn't passed the current commit.

## Verify each environment

Use the packaged script (run from `bifrost-trade-infra/`):

```bash
./scripts/verify_wave2_api_account.sh dev
./scripts/verify_wave2_api_account.sh stg
./scripts/verify_wave2_api_account.sh prod
# or:
./scripts/verify_wave2_api_account.sh all
```

Green output looks like:

```
[dev] api-account image=…/bifrost-api-account:stg ready_since=2026-08-…T…
[dev] schema check: {"params_json":true,"characteristics_json":true,"meta_json":true,"kv_dropped":true,"ops_audit_log":true}
[dev] schema OK
[dev] api contract: {"id":…, "has_params": true, "params_len": 4, "has_chars": true}
[dev] api contract OK
```

If **schema OK** but **api contract WARN/FAIL**, the pod is still the old
image — repeat the `rollout restart` after Tekton pipeline finishes.

## Rollback

Wave 2 is schema-additive on the write path (jsonb columns already exist)
but destructive on read (KV tables are dropped). Rolling back the *image*
alone will crash `/api/strategies/templates` because the old reader
SELECTs `strategy_template_param`. If you must roll back:

```bash
# 1. Restore the old KV subtables from the last PROD snapshot in backups/
# 2. kubectl -n bifrost-<env> rollout undo deploy/api-account
```

There is no non-destructive rollback path; treat Wave 2 as a one-way door
once STG passes verification.
