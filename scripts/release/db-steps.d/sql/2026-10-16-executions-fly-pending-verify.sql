-- Verify (read-only): the new rule is live and what it holds.
SELECT (pg_get_viewdef('brokerage.executions_fly'::regclass) LIKE '%flex_through%') AS new_rule,
       (pg_get_viewdef('brokerage.executions_fly'::regclass) LIKE '%executions_final%') AS old_rule,
       count(*) AS pending_rows
FROM brokerage.executions_fly;
