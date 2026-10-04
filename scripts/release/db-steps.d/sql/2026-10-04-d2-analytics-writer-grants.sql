-- D2 step 1 of 3 (as postgres, bifrost_golden_source, one transaction): give analytics_writer DIRECTLY what
-- it uses today only through its bifrost membership. Revokes nothing; analytics_writer stays a member of
-- bifrost until step 3, so nothing it runs changes. Idempotent: a second run moves nothing and re-grants
-- the same rights.
--
--   1. SELECT on raw_broker.executions_final (journal_distill, journal_memory). The view keeps reading
--      its tables as its owner, bifrost; analytics_writer gets the view only, no raw_broker table.
--   2. Ownership of every bifrost-owned relation in features and research (tables, the four partitioned
--      parents and their partitions, the view v_atm_iv_unified) moves to analytics_writer: Research's DDL
--      (CREATE INDEX / ALTER TABLE … IF NOT EXISTS, COMMENT ON, CREATE OR REPLACE VIEW, CREATE TABLE …
--      PARTITION OF) needs ownership even when nothing changes. Indexes and owned sequences follow their
--      table. ALTER … OWNER rewrites each ACL: bifrost's own entry becomes analytics_writer's, other
--      grantees (market_reader) keep their rights with analytics_writer as grantor.
--   3. bifrost gets SELECT, INSERT, UPDATE, DELETE, TRUNCATE back on every table in features and research
--      (what Research's own _grant_*_schema_privileges gives it; the market-data plugin signs in as
--      bifrost and reads features.option_metric_*). Ownership-only rights (ALTER, DROP, partitions) stay
--      with analytics_writer.
--
-- Takes an ACCESS EXCLUSIVE lock on each relation for the length of the transaction (catalog only, no
-- rewrite). lock_timeout 5s: if a long Research query holds a table, the whole step rolls back; run it
-- again in a quiet window (see the db-step file).

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

GRANT SELECT ON raw_broker.executions_final TO analytics_writer;

DO $$
DECLARE
  r record;
  moved int := 0;
BEGIN
  IF to_regrole('analytics_writer') IS NULL OR to_regrole('bifrost') IS NULL THEN
    RAISE EXCEPTION 'role analytics_writer or bifrost is missing';
  END IF;
  -- Anything but tables, partitioned tables and views owned by bifrost here is unexpected: stop.
  PERFORM 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('features', 'research') AND c.relowner = 'bifrost'::regrole
     AND c.relkind NOT IN ('r', 'p', 'v', 'i', 'I', 'S');
  IF FOUND THEN
    RAISE EXCEPTION 'features / research hold a bifrost-owned object of an unexpected kind; re-run the dry-run';
  END IF;
  FOR r IN
    SELECT c.oid, c.relkind, format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('features', 'research') AND c.relowner = 'bifrost'::regrole
      AND c.relkind IN ('r', 'p', 'v')
    ORDER BY c.relispartition, n.nspname, c.relname   -- parents and plain tables first, then partitions
  LOOP
    -- A partition may already have moved with its parent on some versions; re-check per object.
    IF (SELECT relowner FROM pg_class WHERE oid = r.oid) = 'bifrost'::regrole THEN
      EXECUTE format('ALTER %s %s OWNER TO analytics_writer',
                     CASE r.relkind WHEN 'v' THEN 'VIEW' ELSE 'TABLE' END, r.fq);
      moved := moved + 1;
    END IF;
  END LOOP;
  RAISE NOTICE 'D2: % relation(s) in features / research now owned by analytics_writer', moved;
END
$$;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA features, research TO bifrost;

-- Nothing bifrost-owned may be left in the two schemas (indexes / sequences follow their table).
DO $$
DECLARE
  left_over int;
BEGIN
  SELECT count(*) INTO left_over FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('features', 'research') AND c.relowner = 'bifrost'::regrole;
  IF left_over > 0 THEN
    RAISE EXCEPTION 'D2: % object(s) in features / research are still owned by bifrost', left_over;
  END IF;
END
$$;

COMMIT;
