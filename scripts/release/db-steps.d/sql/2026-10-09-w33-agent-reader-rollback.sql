-- Take CONNECT away and stop the role signing in. The role row stays.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

REVOKE CONNECT ON DATABASE bifrost_dev FROM agent_reader;
REVOKE CONNECT ON DATABASE bifrost_stg FROM agent_reader;
REVOKE CONNECT ON DATABASE bifrost_prod FROM agent_reader;
REVOKE CONNECT ON DATABASE bifrost_golden_source FROM agent_reader;
ALTER ROLE agent_reader NOLOGIN;

COMMIT;
