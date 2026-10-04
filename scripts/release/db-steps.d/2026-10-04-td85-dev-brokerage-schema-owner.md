---
id: 2026-10-04-td85-dev-brokerage-schema-owner
envs: dev
when: before
done: dev
---
# TD-85 D8 complement: DEV schema `brokerage` owned by bifrost

D8 (Owner-approved 2026-10-04: DEV `brokerage` / `market` owner postgres → bifrost) moved the 20 FDW objects and
schema `market`, but schema `brokerage` stayed with postgres, so bifrost has USAGE only there (read-only
2026-10-04: `bifrost_create_brokerage = f` on DEV, `t` on STG / PROD). R4 (`2026-10-08-r4-drop-compat`) rebuilds the
env views in `brokerage` as bifrost and would be refused on DEV. One statement, reversible. Run before R4 on DEV.

Commands run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -At -c "SET default_transaction_read_only=on;" -c "SELECT nspname, nspowner::regrole, has_schema_privilege('bifrost', oid, 'CREATE') FROM pg_namespace WHERE nspname = 'brokerage'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dev-brokerage-schema-owner.sql
verify:  the dry-run again: brokerage | bifrost | t
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td85-dev-brokerage-schema-owner-rollback.sql
