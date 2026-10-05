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
