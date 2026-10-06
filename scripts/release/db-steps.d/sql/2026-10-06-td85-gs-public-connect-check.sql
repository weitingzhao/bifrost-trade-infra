-- TD-85 GS follow-up, read-only: who can connect to bifrost_golden_source and how. Before the revoke the
-- database ACL starts with "=Tc/bifrost" and connect_only_via_public lists market_reader and streaming_replica
-- (read 2026-10-06); after it the ACL starts with "=T/bifrost" and both rows show can_connect f.
SELECT datacl FROM pg_database WHERE datname = 'bifrost_golden_source';

-- Every login role: can it connect now, and would it still connect without PUBLIC? (superuser, owner, an explicit
-- CONNECT to itself or to a role it inherits from)
WITH db AS (SELECT oid, datdba, datacl FROM pg_database WHERE datname = 'bifrost_golden_source'),
grantees AS (SELECT a.grantee FROM db, aclexplode(db.datacl) a WHERE a.privilege_type = 'CONNECT')
SELECT r.rolname,
       has_database_privilege(r.oid, 'bifrost_golden_source', 'CONNECT') AS can_connect,
       r.rolsuper
         OR r.oid = (SELECT datdba FROM db)
         OR EXISTS (SELECT 1 FROM grantees g WHERE g.grantee <> 0 AND pg_has_role(r.oid, g.grantee, 'USAGE'))
         AS connect_without_public,
       (SELECT count(*) FROM pg_stat_activity s WHERE s.usename = r.rolname
          AND s.datname = 'bifrost_golden_source') AS sessions
  FROM pg_roles r
 WHERE r.rolcanlogin
 ORDER BY connect_without_public, r.rolname;
