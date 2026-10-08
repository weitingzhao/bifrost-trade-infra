---
id: 2026-10-07-td85-role-matrix-reader
envs: prod
when: after
done: prod
---
# TD-85: login for the daily role-matrix CronJob

Not executed. No existing login is read-only and able to CONNECT to all four databases
with a Secret the CronJob can mount. `bifrost-postgres-app` is the owner. `brokerage_reader`
can CONNECT to all four and has no write bits, but its password lives in FDW user mappings,
not in a Secret.

This step creates `role_matrix_reader` (LOGIN, NOINHERIT, not a superuser) and grants
CONNECT on `bifrost_dev`, `bifrost_stg`, `bifrost_prod`, and `bifrost_golden_source` only.
Catalog tables are readable without further grants. The password is not in this file and
not in git. After the role exists, the Owner sets a password out of band and creates:

```
kubectl -n data create secret generic db-role-matrix-reader \
  --from-literal=username=role_matrix_reader \
  --from-literal=password='<set locally>'
```

The CronJob `db-role-matrix` reads that Secret. Do not apply the CronJob before the Secret exists.

Rollback revokes CONNECT and sets NOLOGIN. It does not drop the role.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -At -c "SELECT rolname FROM pg_roles WHERE rolname = 'role_matrix_reader'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-role-matrix-reader.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-role-matrix-reader-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-07-td85-role-matrix-reader-rollback.sql
