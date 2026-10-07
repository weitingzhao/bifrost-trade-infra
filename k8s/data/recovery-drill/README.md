# TD-217 Barman recovery drill (prepared, not applied)

Scratch Cluster, one instance, `bootstrap.recovery` from the `bifrost-postgres`
object store, `targetTime` about one hour ago, source `serverName` `bifrost-postgres`,
this Cluster named `pg-recovery-drill` so it cannot archive over the source.
Credentials are a read-only Secret the Owner creates out of band. No backup
section on the scratch Cluster.

`firstRecoverabilityPoint` on 2026-10-07 was `2026-09-07T03:08:25Z`. A target
before that will not recover. Golden Source was 34 GB; the volume request is 80Gi
on a `general` pool node. Check free disk on that node before applying.

## Owner steps

1. On the node that will get the volume (`ubt-k3s-05` or `ubt-k3s-06`): `df -h` shows at least 80 GiB free.
2. Create Secret `minio-backup-readonly` in namespace `pg-recovery-drill` with keys `ACCESS_KEY_ID` and `SECRET_ACCESS_KEY`. The MinIO policy is `s3:GetObject` and `s3:ListBucket` on `bifrost-postgres-backup` only. Do not copy `data/minio-backup`.
3. `kubectl apply -f k8s/data/recovery-drill/namespace.yaml`
4. `bash k8s/data/recovery-drill/render-cluster.sh | kubectl apply -f -`
   Expected: Cluster `pg-recovery-drill` reaches `Healthy` and one pod `Running`. Recovery of ~34 GB plus WAL replay takes a while; watch `kubectl -n pg-recovery-drill describe cluster pg-recovery-drill`.
5. `bash k8s/data/recovery-drill/compare.sh <the same targetTime>`
   Expected: `PASS` and the three lines (`stock_daily`, `atm_iv`, `transactions`) identical on primary and scratch.
6. Record the pass time. The prepared alert `BifrostPostgresRecoveryDrillStale` looks for CronJob `pg-recovery-drill` last success within 35 days. This drill is manual; the CronJob is not in this directory because a CronJob that creates an 80Gi Cluster needs its own RBAC review. Apply `k8s/monitoring/td-d2-postgres-rules.yaml` only after a successful drill, or the absent() clause pages immediately.

## Cleanup

```bash
kubectl -n pg-recovery-drill delete cluster pg-recovery-drill
kubectl delete ns pg-recovery-drill
```

Expected: the Cluster, its pod, the PVC and the read-only Secret are gone. `local-path` reclaim is Delete, so the volume goes with the claim. This does not touch `data/bifrost-postgres` or the backup bucket.

Rollback of a failed recovery is the same cleanup. Nothing in the source Cluster or the bucket is written by these steps when the Secret is read-only and the scratch Cluster has no backup section.
