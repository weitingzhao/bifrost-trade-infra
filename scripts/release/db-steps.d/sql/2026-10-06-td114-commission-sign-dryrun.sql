-- TD-114 dry run: raw_broker.commissions rows not in IB's statement sign (read-only).
--
-- Since core 0.50.0 every writer stores IB's statement sign (a charge is negative, a rebate
-- positive -- what Flex sends) and the ledger reader returns -commission for every source.
-- Before 0.50.0 the TWS / gateway path and the POST/PUT /executions writers stored a cost as a
-- positive number. Those rows read back with the wrong sign once an env runs core >= 0.50.0.
--
-- Run on Golden Source, any time (nothing is written):
--   psql -d bifrost_golden_source -v ON_ERROR_STOP=1 [-v cutover="'<UTC timestamp>'"] \
--        -f 2026-10-06-td114-commission-sign-dryrun.sql
-- cutover defaults to now (as in the restate); pass one to see the count for an earlier time.
--
-- 1. Per owner of the exec id (the execution row the brokerage.executions view keeps: Flex wins
--    over TWS for a shared exec id) and sign.
-- 2. The candidates the restate negates: no Flex row, commission > 0, created before the cutover. The restate takes the count
--    printed here as :expected and refuses to commit on any other count.
-- 3. Flex-backed rows whose sign disagrees with the Flex row's own cash (net_cash - proceeds -
--    taxes). Expected 0; the restate does not touch these -- report any to the Owner.

\if :{?cutover}
\else
\set cutover '''now'''
\endif

BEGIN READ ONLY;

\echo '== 1. rows per owner and sign'
WITH owner AS (
  SELECT c.exec_id, c.commission,
         CASE
           WHEN EXISTS (SELECT 1 FROM raw_broker.executions_raw_flex f WHERE f.exec_id = c.exec_id) THEN 'flex'
           WHEN EXISTS (SELECT 1 FROM raw_broker.executions_raw_tws t WHERE t.exec_id = c.exec_id) THEN 'tws'
           WHEN EXISTS (SELECT 1 FROM raw_broker.executions_raw_journal j WHERE j.exec_id = c.exec_id) THEN 'journal'
           ELSE 'orphan'
         END AS owner
  FROM raw_broker.commissions c
)
SELECT owner, sign(commission) AS sign, count(*) AS n, round(sum(commission)::numeric, 2) AS total
FROM owner GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== 2. restate candidates (no Flex row, commission > 0)'
SELECT c.exec_id, c.commission, c.currency, c.created_at,
       coalesce(t.source, j.source, '(orphan)') AS source
FROM raw_broker.commissions c
LEFT JOIN raw_broker.executions_raw_tws t ON t.exec_id = c.exec_id
LEFT JOIN raw_broker.executions_raw_journal j ON j.exec_id = c.exec_id
WHERE c.commission > 0
  AND c.created_at < :cutover::timestamptz
  AND NOT EXISTS (SELECT 1 FROM raw_broker.executions_raw_flex f WHERE f.exec_id = c.exec_id)
ORDER BY c.created_at;

SELECT count(*) AS expected
FROM raw_broker.commissions c
WHERE c.commission > 0
  AND c.created_at < :cutover::timestamptz
  AND NOT EXISTS (SELECT 1 FROM raw_broker.executions_raw_flex f WHERE f.exec_id = c.exec_id);

\echo '== 3. Flex-backed rows whose sign disagrees with the Flex cash (expected 0)'
SELECT count(*) AS flex_sign_mismatch
FROM raw_broker.commissions c
JOIN raw_broker.executions_raw_flex f ON f.exec_id = c.exec_id
WHERE c.commission IS NOT NULL AND c.commission <> 0
  AND f.net_cash IS NOT NULL AND f.proceeds IS NOT NULL
  AND sign(c.commission) <> sign(round((f.net_cash - f.proceeds - coalesce(f.taxes, 0))::numeric, 4));

ROLLBACK;
