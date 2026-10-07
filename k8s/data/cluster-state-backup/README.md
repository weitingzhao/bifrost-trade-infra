# Cluster-state backup (age-encrypted etcd snapshot + Secrets)

Second copy of level-1 cluster state (ADR §9). The only k3s server is
`ubt-k3s-01`. Its etcd snapshots stay on that node's disk
(`/var/lib/rancher/k3s/server/db/snapshots/`, about 170MiB, every 12h).
This k3s has no secrets-at-rest encryption, so a snapshot contains every
Secret in plaintext. The job age-encrypts the newest snapshot before any
byte of it reaches the NAS.

| What | Where |
|------|--------|
| Newest etcd snapshot, age ciphertext (`etcd-snapshot-….age`) | `daily/<UTC date>/` on claim `kube-system/cluster-state-backup` (`nfs-cold`) |
| All Secrets, as YAML, age-encrypted before they touch the volume | `secrets.yaml.age` in that directory |
| ConfigMaps named `platform-state-*`, same treatment | `platform-state.yaml.age` |
| k3s server token (`/var/lib/rancher/k3s/server/token`), same treatment | `server-token.age` (needed to restore the snapshot onto a new disk) |
| Plaintext filenames, sizes, sha256, and a timestamp. The snapshot row's `plaintext_sha256` is the source file, hashed before encryption | `MANIFEST` in that directory |
| Daily copies, newest 30 kept | `daily/` (also a one-line `STATUS`) |
| One copy per calendar month, newest 12 kept | `monthly/<YYYY-MM>/` — ciphertext and `MANIFEST` only |

Schedule: 05:15 UTC, after the 03:00 physical backup and the 04:30 logical
backup. The age recipient is the Owner's public key in ConfigMap
`cluster-state-backup-recipient`. The private key is not in the cluster
and not in git.

age reads the snapshot from the read-only hostPath and writes ciphertext
to a temp name on the volume. The temp name is renamed to
`etcd-snapshot-….age` only after the age header checks. No unencrypted
snapshot is stored on the NAS. Restore decrypts, checks
`plaintext_sha256` in `MANIFEST`, then follows the k3s reset steps.
See `docs/runbooks/cluster-state-restore.md`.

The init container downloads age and kubectl at runtime (pinned checksums
in `fetch-tools.sh`, checked before either binary is kept). If GitHub or
dl.k8s.io is unreachable the backup does not run. Anyone who can change
those two checksums in git can change the binaries that execute. They
are not baked into a pinned image.

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
