---
id: 2026-10-06-td85-gs-public-connect-revoke
envs: prod
when: after
done:
---
# TD-85 GS follow-up: PUBLIC loses CONNECT on bifrost_golden_source

Owner-approved 2026-10-06 ("GS PUBLIC CONNECT 另开一项，按你推荐的来"). D4 took PUBLIC's CONNECT off the three Trade
databases and left Golden Source to D6; D6 gave the plugins explicit CONNECT so this revoke "cannot cut them off"
but did not check the other roles. This step checks them and closes it. Golden Source is one database shared by all
envs, so the step runs once (filed under prod).

Read-only 2026-10-06 (`…-check.sql`): ACL `=Tc/bifrost` first. Every login role with a session or a workload holds
an explicit CONNECT or owns the database — analytics_writer, brokerage_reader (the Trade FDW, 10 sessions),
brokerage_writer, data_writer, feedback_writer, flex_writer, trade_app_{dev,stg,prod}; bifrost is the owner (db-init,
`data/logical-backup`); postgres is superuser. Only two rely on PUBLIC:

- `market_reader` — the market-data plugin's read role on paper (`create_roles.sql`, SCHEMA.md); no Secret,
  ConfigMap, Deployment, CronJob or local `.env` names it, no session. It loses CONNECT; its grants stay.
- `streaming_replica` — CNPG replication; replication connections do not check database CONNECT (D4 took the same
  from it on the Trade databases).

| # | statement | object | owner after | reversible? | rollback (`sql/…-rollback.sql`) |
|---|-----------|--------|-------------|-------------|----------------------------------|
| 1 | guard (`DO` block): abort if a session here belongs to a role that would lose CONNECT | — | — | read-only | — |
| 2 | `REVOKE CONNECT ON DATABASE bifrost_golden_source FROM PUBLIC` | database ACL (`=Tc` → `=T`) | bifrost | yes | `GRANT CONNECT ON DATABASE bifrost_golden_source TO PUBLIC` |

PUBLIC keeps TEMPORARY, as on the Trade databases. The GS `public` schema is already `=U` (no PUBLIC CREATE).
Open sessions are not affected (CONNECT is checked at connect time); a role without CONNECT fails on its next
connect with `User does not have CONNECT privilege`.

Rehearsed 2026-10-06 on a throwaway postgres:17 (owner bifrost, explicit grants, a login inheriting CONNECT from a
NOLOGIN group, market_reader, streaming_replica): guard aborted while market_reader held a session (ACL unchanged);
then `=Tc` → `=T`, market_reader refused, the explicit grantees and the inheriting login connect and keep TEMP;
second run no-op; rollback back to `=Tc`, market_reader connects again.

After it: watch for `does not have CONNECT privilege` on bifrost_golden_source (Loki `{namespace="data"}`) for one
plugin day; none is expected. A future workload that signs in as a new role needs its own `GRANT CONNECT`.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-gs-public-connect-check.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-gs-public-connect-revoke.sql
verify:  the dry-run again: ACL starts `=T/bifrost`; market_reader and streaming_replica can_connect f, every other row t
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-06-td85-gs-public-connect-rollback.sql
