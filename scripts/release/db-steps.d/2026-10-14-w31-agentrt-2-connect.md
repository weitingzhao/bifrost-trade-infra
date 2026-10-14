---
id: 2026-10-14-w31-agentrt-2-connect
envs: dev stg prod
when: after
done:
---
# W-31: agent runtime connect

Owner apply order: roles (all three envs) → passwords →
`kubectl apply -n data -f k8s/data/databases.yaml` → wait for the three databases →
connect (each env) →
`kubectl apply -n data -f k8s/data/postgres-ingress-network-policy.yaml` → migration.

PUBLIC and cross-environment CONNECT are denied. The local owner/runtime,
agent_reader and role_matrix_reader connect in every environment. Only PROD also
allows bifrost: logical-backup logs in as bifrost and backs up bifrost_platform:agentrt;
DEV and STG are not logical-backup targets and give bifrost no CONNECT or defaults.
PROD's read-only backup default privileges cover migration-created schemas, tables
and sequences. Defaults are global because agentrt does not exist until migration;
the table/sequence defaults grant SELECT only, schema defaults grant USAGE only.
Rerunning also grants SELECT/USAGE on existing PROD agentrt objects.
Rollback quarantines the database; it never restores PUBLIC access or drops data.
Verify checks effective CONNECT, exact backup defaults, and no other grantees of
the owner's defaults (apart from the owner itself). It does not test passwords or TCP login.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform_dev'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform_stg'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-rollback.sql

