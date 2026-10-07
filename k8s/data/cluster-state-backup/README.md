# Cluster-state backup (etcd snapshot + age-encrypted Secrets)

Second copy of level-1 cluster state (ADR §9). The only k3s server is
`ubt-k3s-01`. Its etcd snapshots stay on that node's disk
(`/var/lib/rancher/k3s/server/db/snapshots/`, about 170MiB, every 12h)
until this job copies the newest one to the NAS.

| What | Where |
|------|--------|
| Newest etcd snapshot, exact bytes (sha256 matches the source) | `daily/<UTC date>/` on claim `kube-system/cluster-state-backup` (`nfs-cold`) |
| All Secrets, as YAML, age-encrypted before they touch the volume | `secrets.yaml.age` in that directory |
| ConfigMaps named `platform-state-*`, same treatment | `platform-state.yaml.age` |
| k3s server token (`/var/lib/rancher/k3s/server/token`), same treatment | `server-token.age` (needed to restore the snapshot onto a new disk) |
| Daily copies, newest 30 kept | `daily/` |
| One copy per calendar month, newest 12 kept | `monthly/<YYYY-MM>/` (replaced by that month's latest success) |

Schedule: 05:15 UTC, after the 03:00 physical backup and the 04:30 logical
backup. The age recipient is the Owner's public key in ConfigMap
`cluster-state-backup-recipient`. The private key is not in the cluster
and not in git.

The snapshot file on the NAS is not age-wrapped (the copy has to match the
source byte for byte). Treat that file like the etcd database. The YAML
exports are ciphertext.

Not under Argo, same as `k8s/data/logical-backup`.

## Apply

```bash
kubectl apply -k k8s/data/cluster-state-backup
kubectl apply -f k8s/monitoring/bifrost-cluster-state-rules.yaml
```

The first command writes the age public key into ConfigMap
`kube-system/cluster-state-backup-recipient`. No private key is created.

## Run once

```bash
kubectl -n kube-system create job --from=cronjob/cluster-state-backup cluster-state-backup-manual-$(date +%s)
```

A manual Job does not update `kube_cronjob_status_last_successful_time`.
`BifrostClusterStateBackupStale` arms on the next scheduled success.
