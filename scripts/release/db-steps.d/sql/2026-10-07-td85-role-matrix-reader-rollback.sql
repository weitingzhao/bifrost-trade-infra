-- Take CONNECT away and stop the role signing in. The role row is left in place
-- so this file does not remove a role that might own a session.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';

REVOKE CONNECT ON DATABASE bifrost_dev FROM role_matrix_reader;
REVOKE CONNECT ON DATABASE bifrost_stg FROM role_matrix_reader;
REVOKE CONNECT ON DATABASE bifrost_prod FROM role_matrix_reader;
REVOKE CONNECT ON DATABASE bifrost_golden_source FROM role_matrix_reader;
ALTER ROLE role_matrix_reader NOLOGIN;

COMMIT;
