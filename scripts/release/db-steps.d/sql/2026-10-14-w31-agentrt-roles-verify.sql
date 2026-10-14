\set ON_ERROR_STOP on
-- Fail closed before using env in an identifier. Run with -v env=dev|stg|prod.
SELECT :'env' IN ('dev', 'stg', 'prod') AS valid_env \gset
\if :valid_env
\else
  \echo 'w31: env must be dev, stg or prod'
  \quit 2
\endif
SELECT set_config('w31.env', :'env', false);
DO $w31$
DECLARE
  env text := current_setting('w31.env');
  role text;
  lim int;
BEGIN
  FOREACH role IN ARRAY ARRAY['agentrt_owner_' || env, 'platform_agentrt_' || env] LOOP
    lim := CASE WHEN role = 'agentrt_owner_' || env THEN 4 WHEN env = 'prod' THEN 10 ELSE 5 END;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role AND rolcanlogin
                   AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
                   AND NOT rolreplication AND NOT rolbypassrls AND rolconnlimit = lim) THEN
      RAISE EXCEPTION 'w31: missing role or unsafe flags/connection limit: %', role;
    END IF;
  END LOOP;
END
$w31$;
