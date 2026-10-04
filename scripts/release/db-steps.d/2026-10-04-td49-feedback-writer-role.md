---
id: 2026-10-04-td49-feedback-writer-role
envs: dev stg prod
when: before
done:
---
# TD-49 D4 / TD-77 E5: role feedback_writer for trade-api's feedback store (api 0.7.5)

Owner-approved 2026-10-03 (`REQUEST-td49-td77-plan-2026-10-03.md`, "Owner 批复" item 4): trade-api gets a role that
can only read and write `ops_feedback`. api 0.7.5 moves the connection into `feedback_store` with its own env
(`FEEDBACK_PG_HOST / PORT / DATABASE / USER / PASSWORD`); nothing else in the research app holds a Golden Source
connection. Until then api-research signs in as `analytics_writer`, Research's role, which can also write
`dw_stock`, `features`, `raw_broker` and `journal`.

**Golden Source is one database for all three envs.** The SQL part (role, grants, password) runs once; it is
idempotent, so it sits in every env's section and a second run changes nothing (the dry-run shows whether it is done).
The Secret part is per namespace. `when: before`: each env's api 0.7.5 needs both before its pods roll.

**Split of duties.** The DDL stays with db-init, which connects as `bifrost` and owns `ops_feedback` (TD-77 B1,
done: all 8 objects are `bifrost`'s, read-only 2026-10-04). `feedback_writer` gets DML only, no CREATE.
`ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback` covers a table a later
`feedback_schema` step adds; a new column is covered by the table grant.

## Statements (`sql/2026-10-04-td49-feedback-writer-role.sql`, one transaction, as postgres)

| # | statement | object | owner after | reversible? | rollback (`sql/…-rollback.sql`) |
|---|-----------|--------|-------------|-------------|---------------------------------|
| 1 | `CREATE ROLE feedback_writer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` (only if absent) | role `feedback_writer` (cluster-wide, no password, no memberships) | — | yes | `DROP ROLE feedback_writer` (last) |
| 2 | `COMMENT ON ROLE feedback_writer IS …` | role comment | — | yes | goes with the role |
| 3 | `GRANT CONNECT ON DATABASE bifrost_golden_source TO feedback_writer` | database ACL (PUBLIC has CONNECT today; explicit so a later PUBLIC revoke does not cut feedback) | `bifrost` (db owner) | yes | `REVOKE ALL ON DATABASE bifrost_golden_source FROM feedback_writer` |
| 4 | `GRANT USAGE ON SCHEMA ops_feedback TO feedback_writer` | schema ACL | `bifrost` | yes | `REVOKE ALL ON SCHEMA ops_feedback FROM feedback_writer` |
| 5 | `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ops_feedback TO feedback_writer` | `report`, `report_image` | `bifrost` | yes | `REVOKE ALL ON ALL TABLES IN SCHEMA ops_feedback FROM feedback_writer` |
| 6 | `GRANT USAGE ON ALL SEQUENCES IN SCHEMA ops_feedback TO feedback_writer` | `report_report_id_seq`, `report_image_report_image_id_seq` | `bifrost` | yes | `REVOKE ALL ON ALL SEQUENCES IN SCHEMA ops_feedback FROM feedback_writer` |
| 7 | `ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO feedback_writer` | `pg_default_acl` row (bifrost, ops_feedback, r) | `bifrost` | yes | `… REVOKE ALL ON TABLES FROM feedback_writer` |
| 8 | `ALTER DEFAULT PRIVILEGES FOR ROLE bifrost IN SCHEMA ops_feedback GRANT USAGE ON SEQUENCES TO feedback_writer` | `pg_default_acl` row (bifrost, ops_feedback, S) | `bifrost` | yes | `… REVOKE ALL ON SEQUENCES FROM feedback_writer` |
| 9 | `ALTER ROLE feedback_writer PASSWORD 'SCRAM-SHA-256$4096:…'` (sent by `scripts/feedback-writer-secret.sh password`; never in a file) | role password | — | yes | `ALTER ROLE feedback_writer PASSWORD NULL`, or the rollback file |

No data is read or changed; no table is locked beyond the catalog rows of the GRANTs (lock_timeout 10s). The store
uses SELECT / INSERT / UPDATE today; DELETE is in the approved set (a report delete cascades to `report_image`).
The rollback leaves the ACLs as explicit owner-only entries (`{bifrost=arwdDxtm/bifrost}`) instead of NULL: the
same rights.

Rehearsed 2026-10-04 on a throwaway docker postgres:17 with the live roles, memberships and database ACL mirrored:
`ensure_feedback_schema` as bifrost → commit twice → `password` → api 0.7.5's `feedback_store` as feedback_writer:
insert with image, list, image, status, reply, read, summary and an update of a row analytics_writer wrote: all ok;
CREATE TABLE in ops_feedback / public, CREATE SCHEMA, ALTER / DROP / TRUNCATE on ops_feedback, SELECT
raw_broker.account, INSERT journal.note, SET ROLE bifrost: all `42501`; a table and a column bifrost added later:
usable (default privileges); `ensure_feedback_schema` as bifrost again: ok; rollback twice, then commit again: ok.

## Owner checklist (in order; every step but 5 is yours)

1. **Role**: dry-run, then commit (any env's section; once is enough).
2. **Password**: `scripts/feedback-writer-secret.sh ensure` (generates `FEEDBACK_PG_PASSWORD` into this repo's
   gitignored `.env` if absent, value never printed), then `scripts/feedback-writer-secret.sh password`.
3. **Secret in each namespace**: `scripts/feedback-writer-secret.sh secret dev stg prod`, then
   `scripts/feedback-writer-secret.sh check` — expect `role feedback_writer: present, password set`, `signs in: yes`,
   and `equal to local` for all three.
4. **Release api 0.7.5** with infra main carrying the `FEEDBACK_PG_*` env (base `k8s/base/apis/manifest.yaml`):
   STG and PROD get it from the Argo sync of the deliver; DEV needs the manifest applied (its section).
   `release.sh db-done <env> 2026-10-04-td49-feedback-writer-role` after steps 1–3, per env.
5. **Verify** (read-only, an agent may do it): `GET …/api/research/research/feedback/summary` and
   `…/feedback/reports?scope=all` answer 200 on the env; the dry-run's last query shows `feedback_writer` with
   `application_name = trade-api-feedback`. Then **you** file one test report from the desk's feedback panel (it lands
   in the one store all envs share) and set it to `wontfix`: the POST path end to end.
6. **Revoke**: the separate step `2026-10-04-td49-revoke-analytics-from-trade-api` (after), env by env, only once
   that env passed 5.

If 0.7.5 rolls before step 3 in an env, the new api-research pod stays `CreateContainerConfigError` (the Secret
key is not optional) and the old pod keeps serving: create the Secret and the rollout finishes.

## dev
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-role.sql
password: scripts/feedback-writer-secret.sh ensure && scripts/feedback-writer-secret.sh password
secret:  scripts/feedback-writer-secret.sh secret dev && scripts/feedback-writer-secret.sh check dev
manifest (DEV is not under Argo): kubectl diff -k k8s/overlays/dev -l app.kubernetes.io/name=api-research
         then kubectl apply -k k8s/overlays/dev -l app.kubernetes.io/name=api-research
         (adds the five FEEDBACK_PG_* env to Deployment api-research and nothing else; the pod restarts on the
         current :dev image, which ignores them; release.sh dev then brings 0.7.5)
verify:  the dry-run again (feedback_writer: login t, scram t; ops_feedback tables S/I/U/D t for it, schema CREATE f)
         and, after release.sh dev: curl -s http://192.168.10.73:30882/api/research/research/feedback/summary

## stg
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-dryrun.sql
commit:  (only if the dry-run shows no feedback_writer) kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-role.sql
password: (only if has_password is f) scripts/feedback-writer-secret.sh ensure && scripts/feedback-writer-secret.sh password
secret:  scripts/feedback-writer-secret.sh secret stg && scripts/feedback-writer-secret.sh check stg
manifest: comes with the deliver's Argo sync (infra main must carry the FEEDBACK_PG_* env before release.sh stg)
verify:  after the deliver: curl -s http://192.168.10.73:30880/api/research/research/feedback/summary

## prod
(order and the other envs: the 'Owner checklist' above in this file)
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on;" -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-dryrun.sql
commit:  (only if the dry-run shows no feedback_writer) kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-role.sql
password: (only if has_password is f) scripts/feedback-writer-secret.sh ensure && scripts/feedback-writer-secret.sh password
secret:  scripts/feedback-writer-secret.sh secret prod && scripts/feedback-writer-secret.sh check prod
manifest: comes with the PROD deliver's Argo sync
verify:  after the deliver: curl -s http://192.168.10.73:30881/api/research/research/feedback/summary
rollback (api first, then DB): back to the api 0.7.3 image (it still reads ANALYTICS_PG_*, which stay until the
         revoke step), then kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-04-td49-feedback-writer-rollback.sql
         and kubectl -n bifrost-prod delete secret bifrost-feedback-secrets (same for stg / dev)
