-- TD-85 D8 complement (DEV only): schema brokerage itself to bifrost, as its objects already are (D8, 2026-10-04).
-- R4 rebuilds the env views in brokerage as bifrost; with the schema owned by postgres bifrost has USAGE only.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
  IF current_database() <> 'bifrost_dev' THEN
    RAISE EXCEPTION 'td85-d8b: connected to %, this SQL is for bifrost_dev', current_database();
  END IF;
  IF (SELECT nspowner::regrole::text FROM pg_namespace WHERE nspname = 'brokerage') NOT IN ('postgres', 'bifrost') THEN
    RAISE EXCEPTION 'td85-d8b: schema brokerage has an unexpected owner; nothing changed';
  END IF;
END $$;
ALTER SCHEMA brokerage OWNER TO bifrost;
SELECT nspname, nspowner::regrole AS owner, has_schema_privilege('bifrost', oid, 'CREATE') AS bifrost_create,
       has_schema_privilege('trade_app_dev', oid, 'USAGE') AS runtime_usage
FROM pg_namespace WHERE nspname = 'brokerage';
COMMIT;
