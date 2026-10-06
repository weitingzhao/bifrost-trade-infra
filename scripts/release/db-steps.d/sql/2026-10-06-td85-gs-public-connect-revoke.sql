-- TD-85 GS follow-up (as postgres, in bifrost_golden_source, one transaction): PUBLIC loses CONNECT on the Golden
-- Source database, as D4 did for the three Trade databases. Every role that signs in to it holds an explicit
-- CONNECT (D4, D6, TD-49 and the roles step) or owns it; the two that do not are market_reader (no workload
-- or Secret uses it, 2026-10-06) and streaming_replica (replication connections do not check database CONNECT).
-- PUBLIC keeps TEMPORARY, as on the Trade databases. Aborts, changing nothing, if a role that would lose CONNECT
-- has a session here. Idempotent.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$
DECLARE
  losing text;
BEGIN
  SELECT string_agg(DISTINCT s.usename, ', ') INTO losing
    FROM pg_stat_activity s JOIN pg_roles r ON r.rolname = s.usename
   WHERE s.datname = 'bifrost_golden_source'
     AND NOT r.rolsuper
     AND r.oid <> (SELECT datdba FROM pg_database WHERE datname = 'bifrost_golden_source')
     AND NOT EXISTS (
       SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
        WHERE d.datname = 'bifrost_golden_source' AND a.privilege_type = 'CONNECT'
          AND a.grantee <> 0 AND pg_has_role(r.oid, a.grantee, 'USAGE'));
  IF losing IS NOT NULL THEN
    RAISE EXCEPTION 'sessions on bifrost_golden_source rely on PUBLIC CONNECT: %', losing;
  END IF;
END
$$;
REVOKE CONNECT ON DATABASE bifrost_golden_source FROM PUBLIC;
COMMIT;
