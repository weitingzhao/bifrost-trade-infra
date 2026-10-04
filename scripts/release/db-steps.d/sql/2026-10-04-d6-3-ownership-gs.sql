-- D6 step 3 of 4 (as postgres, bifrost_golden_source, one transaction): ownership moves to the role that
-- runs the DDL (Owner 2026-10-04, P1; "谁跑 DDL 谁拥有", as in D2).
--
--   M1  every bifrost-owned relation in raw_market (tables, partitioned parents, partitions, views; owned
--       sequences and indexes follow their table) and the schema raw_market -> data_writer.
--   M2  the seven market tables of ops_jobs (job_ingest, ingest_freshness, queue_sample, coverage_sample,
--       data_source_void, symbol_source_void, watchlist_cache; their sequences follow) -> data_writer.
--   F2  the four flex tables of ops_jobs (job_flex_ingest, flex_ingest_freshness, flex_worker_heartbeat,
--       flex_settings; job_flex_ingest_id_seq follows) -> flex_writer.
--   F5  (Owner: ops_jobs owners split per plugin) the schema ops_jobs -> postgres, so neither plugin (nor
--       bifrost) owns the schema that holds the other's tables and can drop them; both get USAGE, CREATE.
--       The five partition helpers ops_jobs.{ensure_day,ensure_month,ensure_year}_partitions /
--       drop_{day,month}_partitions_older_than -> postgres as well (DEVIATION from the plan's M2, which
--       said data_writer; named for the Owner): they are SECURITY INVOKER, so EXECUTE (PUBLIC has it) is
--       all a caller needs, no plugin path replaces them at run time, and Research's Dagster runs
--       ensure_month_partitions as analytics_writer — an owner could rewrite code that Research executes.
--       To follow M2 literally instead, change the target of the function loop below to data_writer.
--   M3  default privileges for what the new owners create later (new monthly partitions, a new ops table):
--       FOR ROLE data_writer IN raw_market: SELECT to analytics_writer, analytics_reader, market_reader,
--       brokerage_reader (today's readers); IN ops_jobs: SELECT to analytics_reader, market_reader.
--       FOR ROLE flex_writer IN ops_jobs: SELECT to analytics_reader.
--   Bridge  bifrost keeps USAGE + SELECT/INSERT/UPDATE/DELETE/TRUNCATE on raw_market and the eleven ops_jobs
--       tables (and their sequences) so the plugins, still signed in as bifrost until the Secret switch,
--       keep reading and writing. What bifrost loses at once is ownership-only work: the migrate Job,
--       partition create / drop in the nightly trim, the flex ALTER … ADD COLUMN on a fresh process. Switch
--       within the same window; step 4 removes the bridge.
--
-- ALTER … OWNER rewrites each ACL: the old owner's entry becomes the new owner's (bifrost's own rights
-- go), other grantees keep theirs with the new owner as grantor (analytics_writer, market_reader, …).
-- Each relation takes an ACCESS EXCLUSIVE lock until COMMIT (catalog only, no rewrite); lock_timeout 5s:
-- if a long plugin statement holds a table the whole step rolls back and is simply run again. Idempotent.
-- Rollback: sql/2026-10-04-d6-rollback-gs.sql.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '300s';

DO $d6$
DECLARE
  r       record;
  moved   int;
  market  text[] := ARRAY['job_ingest', 'ingest_freshness', 'queue_sample', 'coverage_sample',
                          'data_source_void', 'symbol_source_void', 'watchlist_cache'];
  flex    text[] := ARRAY['job_flex_ingest', 'flex_ingest_freshness', 'flex_worker_heartbeat', 'flex_settings'];
BEGIN
  IF current_database() <> 'bifrost_golden_source' THEN
    RAISE EXCEPTION 'd6: run this in bifrost_golden_source, not %', current_database();
  END IF;
  IF to_regrole('flex_writer') IS NULL OR NOT has_schema_privilege('data_writer', 'features', 'USAGE') THEN
    RAISE EXCEPTION 'd6: step 2 (sql/2026-10-04-d6-2-grants-gs.sql) has not run';
  END IF;
  -- An ops_jobs table that is neither market nor flex would be left with bifrost in a schema it no longer
  -- owns: stop and look.
  PERFORM 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'ops_jobs' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
     AND NOT (c.relname = ANY (market) OR c.relname = ANY (flex));
  IF FOUND THEN
    RAISE EXCEPTION 'd6: ops_jobs holds a relation that is neither market nor flex; re-run the dry-run';
  END IF;
  PERFORM 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'raw_market' AND c.relowner NOT IN ('bifrost'::regrole, 'data_writer'::regrole);
  IF FOUND THEN
    RAISE EXCEPTION 'd6: raw_market holds an object owned by neither bifrost nor data_writer; re-run the dry-run';
  END IF;

  -- M1: parents and plain tables first, partitions after (ALTER TABLE … OWNER does not recurse).
  moved := 0;
  FOR r IN
    SELECT c.oid, c.relkind, format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'raw_market' AND c.relowner = 'bifrost'::regrole AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY c.relispartition, c.relname
  LOOP
    IF (SELECT relowner FROM pg_class WHERE oid = r.oid) = 'bifrost'::regrole THEN
      EXECUTE format('ALTER %s %s OWNER TO data_writer',
                     CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END, r.fq);
      moved := moved + 1;
    END IF;
  END LOOP;
  -- A sequence not linked to a column does not follow a table.
  FOR r IN
    SELECT format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'raw_market' AND c.relkind = 'S' AND c.relowner = 'bifrost'::regrole
  LOOP
    EXECUTE format('ALTER SEQUENCE %s OWNER TO data_writer', r.fq);
    moved := moved + 1;
  END LOOP;
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'raw_market') <> 'data_writer'::regrole THEN
    ALTER SCHEMA raw_market OWNER TO data_writer;
  END IF;
  RAISE NOTICE 'd6 M1: % raw_market object(s) now owned by data_writer (schema too)', moved;

  -- M2 / F2
  moved := 0;
  FOR r IN
    SELECT format('ops_jobs.%I', c.relname) AS fq,
           CASE WHEN c.relname = ANY (market) THEN 'data_writer' ELSE 'flex_writer' END AS new_owner
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ops_jobs' AND c.relkind IN ('r', 'p')
      AND c.relowner <> CASE WHEN c.relname = ANY (market) THEN 'data_writer'::regrole ELSE 'flex_writer'::regrole END
  LOOP
    EXECUTE format('ALTER TABLE %s OWNER TO %I', r.fq, r.new_owner);
    moved := moved + 1;
  END LOOP;
  RAISE NOTICE 'd6 M2/F2: % ops_jobs table(s) moved to data_writer / flex_writer', moved;

  -- F5: the shared schema and the shared helpers belong to postgres.
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'ops_jobs') <> 'postgres'::regrole THEN
    ALTER SCHEMA ops_jobs OWNER TO postgres;
  END IF;
  moved := 0;
  FOR r IN
    SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'ops_jobs' AND p.proowner <> 'postgres'::regrole
  LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO postgres', r.sig);
    moved := moved + 1;
  END LOOP;
  RAISE NOTICE 'd6 F5: schema ops_jobs and % helper function(s) now owned by postgres', moved;
END
$d6$;

GRANT USAGE, CREATE ON SCHEMA ops_jobs TO data_writer, flex_writer;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ops_jobs TO data_writer;

-- M3
ALTER DEFAULT PRIVILEGES FOR ROLE data_writer IN SCHEMA raw_market
  GRANT SELECT ON TABLES TO analytics_writer, analytics_reader, market_reader, brokerage_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE data_writer IN SCHEMA ops_jobs
  GRANT SELECT ON TABLES TO analytics_reader, market_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE flex_writer IN SCHEMA ops_jobs
  GRANT SELECT ON TABLES TO analytics_reader;

-- Bridge (removed in step 4): the plugins keep working as bifrost until the switch.
GRANT USAGE ON SCHEMA raw_market, ops_jobs TO bifrost;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw_market, ops_jobs TO bifrost;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA raw_market, ops_jobs TO bifrost;

DO $d6$
DECLARE
  left_over int;
BEGIN
  SELECT count(*) INTO left_over FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('raw_market', 'ops_jobs') AND c.relowner = 'bifrost'::regrole;
  IF left_over > 0 THEN
    RAISE EXCEPTION 'd6: % object(s) in raw_market / ops_jobs are still owned by bifrost', left_over;
  END IF;
END
$d6$;

COMMIT;
