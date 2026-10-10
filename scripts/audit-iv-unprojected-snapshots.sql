-- Run via audit-iv-snapshot-source.py: two bounded observation windows.
-- Counts input candidates, not successful ATM or cone readings.
SELECT os.underlying,
       DATE(timezone('America/New_York', os.snapshot_ts)),
       oc.expiry, count(DISTINCT os.option_ticker)
FROM raw_market.option_snapshot os
JOIN raw_market.option_contract oc USING (option_ticker)
WHERE os.snapshot_ts >= (%s::timestamp AT TIME ZONE 'America/New_York')
  AND os.snapshot_ts < (%s::timestamp AT TIME ZONE 'America/New_York')
  AND DATE(timezone('America/New_York', os.fetched_at))
      - DATE(timezone('America/New_York', os.snapshot_ts)) <= 3
  AND oc.expiry - DATE(timezone('America/New_York', os.snapshot_ts)) BETWEEN 50 AND 220
  AND os.iv > 0
  AND (CASE WHEN os.iv > 3 THEN os.iv / 100 ELSE os.iv END) BETWEEN .01 AND 5
  AND substr(os.option_ticker, 3, length(os.option_ticker) - 17) !~ '[0-9]$'
  AND NOT EXISTS (
    SELECT 1 FROM features.option_iv_reconstructed_daily r
    WHERE r.option_ticker = os.option_ticker
      AND r.trade_date = DATE(timezone('America/New_York', os.snapshot_ts))
      AND r.iv > 0 AND r.spot > 0
  )
GROUP BY 1, 2, 3;
