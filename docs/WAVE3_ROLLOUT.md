# Wave 3 rollout — bifrost-core v0.12.0 (Wave 2 + Wave 3 single cutover)

Owner-facing runbook for delivering Wave 2 + Wave 3 DB hygiene as one
`bifrost-core v0.12.0` image cutover (K-W3.1).

## What ships in v0.12.0

| Track | Change | Runtime impact |
|---|---|---|
| Wave 2 | strategy KV → jsonb; `ops_audit_log` DDL in core; clone excludes audit data | `api-account` must use new readers |
| Wave 3 A | DROP `strategy_history` (DDL / writer / reader / API `/history` / FE section) | Silent UI removal; table gone after `db-init` / pod `_ensure_tables` |
| Wave 3 B | `raw_broker.transactions` UNIQUE → `(account_id, ts, amount, type, report_date)` | Flex upsert `ON CONFLICT` target updated; Plugin uses core |

## Prerequisites

```bash
cd bifrost-trade-core && git describe --tags   # expect v0.12.0 after local tag
cd bifrost-trade-api && grep bifrost-core pyproject.toml   # >=0.12.0
cd bifrost-trade-infra && grep BIFROST_CORE_REF .env.example  # v0.12.0
```

Preflight (already run during Wave 3 execution):

- `raw_broker.transactions` has 0 NULL `report_date` rows
- `strategy_history` had 0 rows in DEV/STG/PROD before DROP

## Delivery path

Same as Wave 2 — Tekton `bifrost-deliver-stg` / `-prod` copies
`bifrost-trade-core/src` into the API image (`Dockerfile.api-stg`).

```
Ops Console → Program → Deploy Mainline → bifrost-deliver-stg → Run
# after STG green:
Ops Console → Program → Deploy Mainline → bifrost-deliver-prod → Run
```

DEV (uses `:stg` tag):

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
kubectl -n bifrost-dev rollout restart deploy/api-account
kubectl -n bifrost-dev rollout status  deploy/api-account --timeout=120s
```

Also restart `api-monitor` if ops audit_store path matters in that pod,
and any Flex Plugin worker that embeds core for upsert.

## Verify

```bash
cd bifrost-trade-infra
./scripts/verify_wave2_api_account.sh all          # Wave 2 + append-only Wave 3 checks
./scripts/verify_wave3_strategy_history_retired.sh all
./scripts/verify_wave3_broker_dedupe.sh
```

## Rollback

- Track A (`strategy_history`): one-way after DROP (table was empty).
- Track B: restore old UNIQUE with
  `DROP CONSTRAINT raw_broker_transactions_dedupe_v2` then
  `ADD CONSTRAINT … UNIQUE (account_id, ts, amount, type)` — only if image
  is also rolled back to pre-0.12.0 upsert code.
