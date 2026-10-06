-- TD-114 restate: negate the commission rows stored cost-positive before core 0.50.0. OWNER-RUN.
--
-- When: after every env that writes commissions (dev, stg, prod trade-api and worker) runs
-- core >= 0.50.0. An env still on an older core reads a restated row with the wrong sign, and
-- would keep writing new cost-positive rows.
--
-- How:
--   1. Run 2026-10-06-td114-commission-sign-dryrun.sql; note the "expected" count and look at the list.
--   2. psql -d bifrost_golden_source -v ON_ERROR_STOP=1 -v expected=N \
--        [-v cutover="'2026-10-20 00:00+00'"] -f 2026-10-06-td114-commission-sign-restate.sql
--      N is the dry run's count. The script negates only rows with no Flex execution,
--      commission > 0 and created_at before the cutover (default: now; give the PROD rollout
--      time to leave alone a rebate typed into the Ledger form after it, stored positive and
--      correct), and commits only when it changed exactly N rows.
--
-- Reversible: the same UPDATE again (negation) on the exec ids it printed.

\if :{?cutover}
\else
\set cutover '''now'''
\endif

BEGIN;

CREATE TEMP TABLE td114_restate ON COMMIT DROP AS
SELECT c.exec_id, c.commission AS before
FROM raw_broker.commissions c
WHERE c.commission > 0
  AND c.created_at < :cutover::timestamptz
  AND NOT EXISTS (SELECT 1 FROM raw_broker.executions_raw_flex f WHERE f.exec_id = c.exec_id);

UPDATE raw_broker.commissions c
SET commission = -c.commission
FROM td114_restate r
WHERE c.exec_id = r.exec_id;

SELECT r.exec_id, r.before, c.commission AS after
FROM td114_restate r JOIN raw_broker.commissions c USING (exec_id)
ORDER BY r.exec_id;

-- Refuse to commit on a count other than the dry run's: the division fails and ON_ERROR_STOP
-- leaves the transaction to roll back.
SELECT 1 / (CASE WHEN count(*) = :expected THEN 1 ELSE 0 END) AS count_matches_expected
FROM td114_restate;

-- After: no row without a Flex execution may still be positive from before the cutover.
SELECT 1 / (CASE WHEN count(*) = 0 THEN 1 ELSE 0 END) AS none_left
FROM raw_broker.commissions c
WHERE c.commission > 0
  AND c.created_at < :cutover::timestamptz
  AND NOT EXISTS (SELECT 1 FROM raw_broker.executions_raw_flex f WHERE f.exec_id = c.exec_id);

COMMIT;
