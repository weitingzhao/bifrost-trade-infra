-- D2 rollback, functional (as postgres, bifrost_golden_source): analytics_writer is a member of bifrost
-- again, exactly as before 2026-10-04 (inherit, set; granted by postgres). This alone restores every right
-- Research had. Steps 1 and 2 may stay: analytics_writer owning Research's tables and bifrost holding
-- S/I/U/D/TRUNCATE on them is what Research's own DDL code grants anyway. To also put the owners back,
-- run sql/2026-10-04-d2-analytics-writer-rollback-ownership.sql afterwards. Idempotent.

\set ON_ERROR_STOP on
GRANT bifrost TO analytics_writer WITH INHERIT TRUE, SET TRUE GRANTED BY postgres;
