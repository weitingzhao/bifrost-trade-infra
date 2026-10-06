---
id: 2026-10-06-td114-commission-sign-restate
envs: prod
when: after
done:
---
# TD-114: restate the commission rows stored cost-positive before core 0.50.0 (Golden Source only)

**Owner approval required: it rewrites existing `raw_broker.commissions` rows.** Prepared 2026-10-06, not run.

Core 0.50.0 gives `raw_broker.commissions.commission` one stored sign: IB's statement sign (a charge negative, a rebate
positive — what Flex sends). The IB API commissionReport path and the `POST`/`PUT /executions` writers now store the
negation of the cost they receive, and the ledger reader returns `-commission` for every source. Before 0.50.0 those
writers stored the cost positive and the reader flipped the sign by the execution row's source. Rows written that way
read back as rebates on core >= 0.50.0 until restated.

Read-only 2026-10-06 (`…-dryrun.sql` on the replica): Flex-backed 435 negative (charges), 15 positive (rebates, each equal
to the Flex row's `net_cash - proceeds - taxes` to 4 dp), 32 NULL; TWS-only 4 positive (1.04–1.06 each, created
2026-03-17), 33 NULL; journal 2 positive (2 and 1, created 2026-03), 1 zero; orphans 2 zero, 7 NULL. Flex rows whose sign
disagrees with their own cash: 0. **6 rows to restate, 7.20 USD in total.**

**Run only after every env runs core >= 0.50.0** — STG / PROD through the release, DEV through `release.sh dev` (check
`core_version` on all three `/health`). An env still on an older core reads a restated row with the wrong sign and keeps
writing cost-positive rows. The script only touches rows created before its cutover (default: now). A rebate typed into the
Ledger form after the rollout is stored positive and correct; if one exists, the count differs from 6 and the commit refuses —
then pass `-v "cutover='…'"` with the PROD rollout time to both scripts.

| # | statement | rows | reversible? | rollback |
|---|-----------|------|-------------|----------|
| 1 | `UPDATE raw_broker.commissions SET commission = -commission` where no Flex execution has the exec id, `commission > 0`, `created_at < cutover` | 6 (dry run) | yes | the same negation on the exec ids the commit prints |

The commit refuses (division by zero under `ON_ERROR_STOP`, rolled back) unless it changed exactly `expected` rows and none
is left. Rehearsed 2026-10-06 on a throwaway postgres:16: wrong `expected` → error, nothing changed; right `expected` →
2 TWS rows negated, the Flex row and a positive row created after the cutover untouched.

Verify: the dry-run again with the same cutover: `expected` 0; Ledger commission column positive (costs) for the four
2026-03-17 TWS fills.

## prod
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-06-td114-commission-sign-dryrun.sql
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -v ON_ERROR_STOP=1 -v expected=6 -f - < scripts/release/db-steps.d/sql/2026-10-06-td114-commission-sign-restate.sql
verify:  the dry-run again: expected 0
rollback: the same negation on the exec ids the commit printed (UPDATE raw_broker.commissions SET commission = -commission WHERE exec_id IN those ids)
