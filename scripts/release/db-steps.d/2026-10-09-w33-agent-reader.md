---
id: 2026-10-09-w33-agent-reader
envs: prod
when: after
done:
---
# W-33: read-only login agent_reader

Not executed. Owner confirmed on 2026-10-09 to follow LANE-W33B section 5 as written.
`agent_reader` is LOGIN, not a superuser, a member of `pg_read_all_data`, with
`default_transaction_read_only=on`, `statement_timeout=120s`,
`idle_in_transaction_session_timeout=60s`, and `CONNECTION LIMIT 8`.
CONNECT only on `bifrost_dev`, `bifrost_stg`, `bifrost_prod`, and `bifrost_golden_source`.

The password is not in this file, not in git, and not in the cluster.
After the role exists, the Owner sets a password out of band and writes one line in
`~/.pgpass` (mode 600). Do not create a Secret for it.

Rollback revokes CONNECT and sets NOLOGIN. It does not drop the role.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -At -c "SELECT rolname FROM pg_roles WHERE rolname = 'agent_reader'"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-verify.sql
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-rollback.sql
