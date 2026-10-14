---
id: 2026-10-14-w31-agentrt-1-roles
envs: dev stg prod
when: after
done:
---
# W-31: agent runtime roles

Create the two logins per environment, enforce safe flags and connection limits.
No passwords are stored here. Owner sets passwords out of band after this step.
Rollback sets NOLOGIN and preserves objects; existing sessions are not terminated.

Order matters for Trade deliveries: the role-matrix checker on main reads every login
role in the cluster, and `release-check.sh before` runs it before every Trade delivery.
Six new logins it does not know would stop all Trade deliveries. So, inside one
`release.sh hold` window: run this step for dev, stg and prod, then at once merge branch
`w31/agentrt-21-infra-roles` (it lists the six roles with `connect: []` and nothing
else) and `kubectl apply -k k8s/data/role-matrix`. Only then release the window.

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=dev -At -c "SELECT rolname FROM pg_roles WHERE rolname IN ('agentrt_owner_dev','platform_agentrt_dev')"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=dev -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-rollback.sql

## stg
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=stg -At -c "SELECT rolname FROM pg_roles WHERE rolname IN ('agentrt_owner_stg','platform_agentrt_stg')"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=stg -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-rollback.sql

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=prod -At -c "SELECT rolname FROM pg_roles WHERE rolname IN ('agentrt_owner_prod','platform_agentrt_prod')"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=prod -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-rollback.sql
