---
id: 2026-10-06-td85-raw-broker-data-writer-revoke
envs: prod
when: after
done: prod
---
# TD-85 D6 follow-up: data_writer loses everything in raw_broker (Golden Source only)

Owner-approved 2026-10-06 ("收掉，按你推荐的来"). Since D6, `data_writer` is the market-data plugin's login (56 sessions,
2026-10-06), and the plugin names no `raw_broker` object (`git grep raw_broker` on market-data origin/main: none). Every
core db-init up to 0.48.1 still granted it S/I/U/D/T on every raw_broker table and view, USAGE/SELECT on the sequences,
USAGE on the schema and the same through bifrost's default privileges. Core 0.48.2 (core 756bdb5) stops granting it.

**Run only after every env runs core >= 0.48.2** — STG / PROD through the release, DEV through `release.sh dev`
(check `/api/account/health` `core_version` on all three). Any db-init on 0.48.1 or older grants it all back.

Read-only 2026-10-06 (`…-check.sql`): usage t, 77 object privileges, 6 default-privilege entries.

| # | statement | object | owner after | reversible? | rollback (`sql/…-rollback.sql`) |
|---|-----------|--------|-------------|-------------|----------------------------------|
| 1 | `REVOKE ALL ON ALL TABLES IN SCHEMA raw_broker FROM data_writer` (tables and views) | table / view ACLs | bifrost | yes | `GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES …` |
| 2 | `REVOKE ALL ON ALL SEQUENCES IN SCHEMA raw_broker FROM data_writer` | sequence ACLs | bifrost | yes | `GRANT USAGE, SELECT ON ALL SEQUENCES …` |
| 3 | `ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA raw_broker REVOKE ALL ON TABLES / SEQUENCES FROM data_writer` | default ACLs | — | yes | the two `ALTER DEFAULT PRIVILEGES … GRANT` |
| 4 | `REVOKE USAGE ON SCHEMA raw_broker FROM data_writer` | schema ACL | bifrost | yes | `GRANT USAGE ON SCHEMA raw_broker TO data_writer` |

Other grantees (brokerage_reader / writer, trade_app_*, flex_writer, analytics_writer) are untouched. Rehearsed
2026-10-06 on a throwaway postgres:17 (bifrost-owned schema, table, sequence, view, the 0.48.1 grants): before t/12/6,
after f/0/0, another grantee kept its SELECT, second run no-op, rollback back to t/12/6.

After it: watch market-data for `permission denied` on raw_broker (Loki `{namespace="data", app="bifrost-postgres"}`,
user data_writer) for one plugin day; none is expected.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-raw-broker-data-writer-check.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-raw-broker-data-writer-revoke.sql
verify:  the dry-run again: usage f, 0, 0
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-raw-broker-data-writer-rollback.sql
