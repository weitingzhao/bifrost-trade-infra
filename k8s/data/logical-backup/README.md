# Logical backup of hand-entered data (phase 0 W5)

What the CNPG Barman backup does not give: a table-level copy of the data that
people typed in, stored outside PostgreSQL and MinIO, that restores with
`pg_restore` alone.

| What | Where |
|------|-------|
| `bifrost_{prod,stg,dev}` schema `public` (strategy, trade, review, settings, watchlist …) | one dump per database |
| Golden Source `journal`, `research`, `ops_feedback`, `raw_broker` | one dump per schema |
| Daily runs, newest 14 kept | claim `data/logical-backup-hot` (nfs-hot) → NAS `/volume1/k3s-hot/data-logical-backup-hot-<pv>/daily/<UTC stamp>/` |
| Weekly copies, kept | claim `data/logical-backup-cold` (nfs-cold) → NAS `/volume1/k3s-cold/data-logical-backup-cold-<pv>/weekly/<UTC stamp>/` |
| Restore drill reports | `drills/` in the hot folder |

Each run folder holds `<db>.<schema>.dump` (pg_dump custom format),
`manifest.tsv` (row count of every table, taken inside the same snapshot as
the dump), `extensions.tsv`, `SHA256SUMS` and `STATUS` (`OK`, or `PARTIAL:` and
the targets that failed). `LATEST` names the newest OK run.

Schedules (UTC): backup 04:30 daily, drill 06:00 on the 1st. Alerts:
`BifrostLogicalBackupMissing` (no success for 26 h) and
`BifrostLogicalBackupDrillStale` (no passing drill for 35 days).

RPO is one day for this copy. Point-in-time recovery to the minute is still
the Barman WAL archive, which lives on the same NAS; an offsite copy is open.

## Apply

Not under Argo, like the rest of `k8s/data`:

```bash
kubectl apply -k k8s/data/logical-backup
kubectl apply -f k8s/monitoring/bifrost-alerting-rules.yaml
```

Prerequisite in Golden Source (run once as `postgres`): the app role `bifrost`
cannot read two `journal` sequences owned by `analytics_writer`, and pg_dump
needs to:

```sql
GRANT SELECT ON SEQUENCE journal.memory_mem_no_seq, journal.visit_visit_id_seq TO bifrost;
ALTER DEFAULT PRIVILEGES FOR ROLE analytics_writer IN SCHEMA journal GRANT SELECT ON SEQUENCES TO bifrost;
-- research (2026-10-07, TD-210: the suggestion ledger's sequences broke the research dump)
GRANT SELECT ON SEQUENCE research.suggestion_adoption_suggestion_adoption_id_seq, research.suggestion_settlement_suggestion_settlement_id_seq TO bifrost;
ALTER DEFAULT PRIVILEGES FOR ROLE analytics_writer IN SCHEMA research GRANT SELECT ON SEQUENCES TO bifrost;
```

Without it the `journal` dump fails and the run ends `PARTIAL`.

## Run now, drill now

```bash
kubectl -n data create job --from=cronjob/logical-backup logical-backup-manual-$(date +%s)
kubectl -n data create job --from=cronjob/logical-backup-drill logical-backup-drill-manual-$(date +%s)
```

## Restore one table for real

The dumps restore into any PostgreSQL 17. To pull one table back into a live
database, restore the dump into a scratch database first, compare, then copy
the rows you need; never `pg_restore --clean` straight into PROD.

```bash
pg_restore -l bifrost_prod.public.dump | grep 'TABLE DATA public strategy_plan'
pg_restore -d scratch --no-owner --no-acl -t strategy_plan bifrost_prod.public.dump
```

## Agent runtime (W-31)

`TARGETS` includes `bifrost_platform:agentrt` (PROD only). `backup.sh` loops over
TARGETS; `drill.sh` discovers every dump and creates its source database by name,
so neither script needs another database or schema list. The restore uses
`--no-owner --no-acl`; isolated drill databases do not need the six login roles.
There are no tests in this directory; the role-matrix tests cover the backup
login's access.

Before running migrations, apply db-step `2026-10-14-w31-agentrt-2-connect` in
all three databases. In PROD only (the one backed up) it installs read-only
default schema/table/sequence grants for the backup login `bifrost` on objects
created by `agentrt_owner_prod`; DEV and STG give `bifrost` nothing.
For a database already migrated, rerun that step to grant access on existing
objects too. It grants no CREATE or DML. After migration, request
`create_job_from_cronjob` for `logical-backup` in `data`, then
`logical-backup-drill` in `data` after the backup succeeds. Require the new
`bifrost_platform.agentrt` dump and equal row counts in the drill report.
A physical backup restore to a temporary cluster remains separate (O11).
