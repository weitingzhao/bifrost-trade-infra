# Trade / Platform secrets runbook

Secrets must not live in git-tracked ConfigMap YAML. Use K8s Secrets + env overrides.

## Source of truth

| Secret | Where | Env keys consumed by code |
|--------|-------|---------------------------|
| Trade NS `bifrost-{dev,stg,prod}-secrets` | gitignored `k8s/base/secrets/bifrost-*-secrets.yaml` | `REDIS_IB_*`, `PGPASSWORD`, `GOLDEN_SOURCE_PASSWORD`, `OPS_*`, `MASSIVE_API_KEY` / `POLYGON_API_KEY`, `MARKET_DATA_WRITE_TOKEN` |
| Plugin `redis-ib-acl` | `bifrost-platform-plugin` `.env` → `make install-redis-ib` | ACL file on redis-ib |
| Platform `redis-ib-platform` | gitignored Secret in `bifrost-platform-{stg,prod}` | `REDIS_IB_PLATFORM_PASS` |
| Platform `bifrost-platform-role-tokens` | infra `.env` `PLATFORM_{STG,PROD}_{VIEWER,OPERATOR,ADMIN}_TOKEN` → `make k3s-apply-platform-role-tokens` | STG `PLATFORM_{VIEWER,OPERATOR,ADMIN}_TOKEN` · PROD `PLATFORM_PROD_{VIEWER,OPERATOR,ADMIN}_TOKEN` |
| Monitoring `alertmanager-webhook-auth` | same target (key `token` = STG operator) | Alertmanager `bearer_token_file` |
| Local Compose | infra `.env` | same env keys |

Examples (placeholders only): `k8s/base/secrets/bifrost-*-secrets.example.yaml`.

`REDIS_MASSIVE_*` / `redis-massive` are retired together with the Polygon WS ingestor (2026-09-27);
leftover keys in existing Secrets or `.env` are unused and can be dropped on the next refresh.

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
kubectl -n bifrost-stg rollout restart deploy/daemon
```

## redis-ib users per Trade env (TD-21)

Each Trade env authenticates to redis-ib as its own user: `trade-dev`, `trade-stg`, `trade-prod`.
`trade-prod` is PROD's alone. `trade-dev` / `trade-stg` read the bus and write only their own
operator stream (`ib:operator:cmd:dev` / `:stg`, set in the overlay config) plus on-demand quote
registrations; on those streams the gateway answers read ops only. The plugin's
`tests/test_redis_ib_acl.py` pins what each user may do.

Owner-run, from `bifrost-platform-plugin` (passwords never leave `.env` and the Secrets, never printed):

1. `scripts/redis-ib-env-users.sh acl [--rotate-dev]` — adds the STG password to `.env`, updates
   Secret `redis-ib-acl`, waits for the pod to see it, `ACL LOAD`. No redis-ib restart: it keeps
   nothing on disk, so a restart empties the bus. A file Redis rejects leaves the old users in force.
2. `scripts/redis-ib-env-users.sh switch dev` (then `stg`) — points `bifrost-<env>-secrets` at the
   env's user and restarts that env's Trade pods. Refuses until the env's config sends RPCs to its own stream.
3. `scripts/redis-ib-env-users.sh check` — connections per user and anything redis-ib refused.
4. `scripts/redis-ib-env-users.sh rollback dev|stg` — back to `trade-prod`.

## Rotate redis-ib

1. Generate new passwords in plugin `.env` (`REDIS_IB_TRADE_PROD_PASS`, …).
2. `make -C ../bifrost-platform-plugin install-redis-ib`, then `scripts/redis-ib-env-users.sh acl`
   in the plugin repo so the running redis-ib loads the file (install alone does not reload it).
3. `make -C ../bifrost-platform-plugin sync-redis-ib-secrets` (updates Trade Secrets — each env its own user — + platform `.env` only — **not** tracked YAML).
4. `python3 scripts/materialize_k8s_trade_secrets.py --apply` (or kubectl apply Secrets).
5. Rollout Trade consumers + platform-api + ib-gateway.

## Trade operator / admin tokens (TD-23)

Every write on the Trade API needs a role (`bifrost-trade-api` 0.2.0, `write_guard.py`): operator
for a change, admin for a process exit or an IB disconnect / reconnect. The role comes from
`Authorization: Bearer`, matched against `OPS_OPERATOR_TOKEN` / `OPS_ADMIN_TOKEN` in
`bifrost-<env>-secrets`; without a token the caller is `ops.auth.default_role`. Tokens are never read
from a URL (`?token=` is gone) and never from YAML here.

`scripts/trade-operator-tokens.sh` (Owner-run; no subcommand prints a token):

1. `check <env>`: whether both tokens are set.
2. `ensure <env>`: generate the missing ones, patch the Secret, update the gitignored local copy,
   restart api-monitor / api-account / api-market / api-research. It never replaces a set token.
3. `copy <env> operator|admin`: the token on the macOS clipboard; paste it into the desk's
   **Operator sign-in** (user centre). One slot per browser; an admin token covers operator.
4. `vite-local <env>`: write the operator token as `TRADE_OPERATOR_TOKEN` into the frontend's
   `.env.development.local`; the `:5173` dev proxy adds it server-side (`bdev restart trade-ui`).

To rotate: clear the key in the Secret, `ensure`, then re-paste in each browser.

`default_role` is lowered to `viewer` one env at a time (DEV → STG → PROD), only after that env's
tokens are set and pasted. Until then an anonymous caller is still operator there (admin in DEV).

## Rotate Platform role tokens (cluster platform-api)

No `platform-auth.yaml` carries inline tokens — a role without its env var cannot sign in.
`scripts/sync_platform_k8s_config.sh` still strips any `token:` line on copy as a guard.

Local `:8780` reads `PLATFORM_{VIEWER,REPORTER,OPERATOR,ADMIN,SATELLITE_AUDIT}_TOKEN` from
`bifrost-platform/.env` (the only copy). MCP servers read the same file when their API URL is
loopback; the Console has no build-time token (sign in via header Connect). To rotate: replace
the values, `bdev restart platform-api`, reload MCP servers, re-Connect in the Console.

1. Replace `PLATFORM_{STG,PROD}_{VIEWER,OPERATOR,ADMIN}_TOKEN` in infra `.env` (e.g. `python3 -c 'import secrets;print(secrets.token_urlsafe(32))'`).
2. `make k3s-apply-platform-role-tokens` (also rewrites `alertmanager-webhook-auth`).
3. `kubectl -n bifrost-platform-{stg,prod} rollout restart deploy/platform-api`.
4. Re-enter the token in Ops Console (STG / PROD).

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
