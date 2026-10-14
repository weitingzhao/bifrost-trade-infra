---
id: 2026-10-14-w31-agentrt-connect
envs: dev stg prod
when: after
done:
---
# W-31: agent runtime connect

Run after all six roles and the target CNPG Database exist, before migration.
PUBLIC and cross-environment CONNECT are denied. The five allowed identities are
the local owner/runtime, agent_reader, role_matrix_reader and bifrost (logical backup).
Read-only backup default privileges cover migration-created schemas, tables and sequences.
Rerunning also grants SELECT/USAGE on existing agentrt objects.
Rollback quarantines the database; it never restores PUBLIC access or drops data.
Verify checks effective privileges (including inherited grants), not passwords or a TCP login.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform_dev'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_dev -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform_stg'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform_stg -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -At -c "SELECT datname, pg_get_userbyid(datdba), datacl FROM pg_database WHERE datname = 'bifrost_platform'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_platform -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-connect-rollback.sql

