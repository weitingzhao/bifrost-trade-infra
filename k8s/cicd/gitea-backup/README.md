# Nightly backup of the in-cluster Gitea (W-41)

The Deployment (`k8s/cicd/gitea`, image `gitea/gitea:1.21.11`) keeps SQLite,
repositories, `app.ini`, and tokens on one `local-path` claim, `gitea-data`.
The repositories can be re-mirrored from GitHub. The database and `app.ini`
cannot.

| What | Where |
|------|--------|
| SQLite online backup (`gitea.db`) plus `data.tar` of the rest of the tree | `<UTC stamp>/` on claim `cicd/gitea-backup` (`nfs-cold`) |
| `MANIFEST.tsv`, `SIZES.tsv`, `SHA256SUMS`, `STATUS` | that same directory. `STATUS` is written last |
| Newest OK run | `LATEST` |
| Restore drill reports | `drills/` |

`data.tar` holds repositories, `app.ini` and the custom/conf tree, avatars,
attachments, and LFS when it is present. It leaves out the live database
files (`gitea.db` and its `-wal`/`-shm`/`-journal`), `sessions`, `queues`,
`indexers`, `log`, `actions_log`, `tmp`, and `uploads`. Every repository in
the copy must pass `git fsck --connectivity-only`. A repository that fails is
copied again, up to 3 times; if it still fails the run's `STATUS` is
`FAILED:` and it is not `LATEST`.

`MANIFEST.tsv` has a header and one row per repository: path, then every
`ref=sha` separated by spaces. `SIZES.tsv` is `database` (bytes of the sqlite
copy), `repositories` (uncompressed bytes of the git files inside the
archive), and `total` (sqlite copy plus `data.tar`).

The database copy is `sqlite3 "file:<path>?mode=ro" ".backup"`, then
`PRAGMA integrity_check` on the copy. `gitea dump` is not used. In 1.21.11
`DBConnStr` does `MkdirAll` on the database directory and opens
`file:<path>?mode=rwc`. A rehearsal can still see dump exit 0 when those
directories already exist and the SQL dump happens not to write a page; the
open is read-write-create either way, so the read-only rule rules it out.

Directories on the claim are `0700`, files `0600` (`umask 077`). The image
keeps `/data/ssh` (SSH host keys) owned by root mode `0700`. This job runs as
uid 1000, which is who the image runs Gitea as (`su-exec git`), so those host
keys are not in the archive. A restore mints new host keys. The drill turns
SSH off and binds HTTP to `127.0.0.1`.

## Who can read the NAS export

The claim lands at `192.168.10.20:/volume1/k3s-cold/cicd-gitea-backup-<pv>/`.
The NAS squashes every client uid to 1000, the same uid that owns the MinIO
and provisioner folders (`k8s/data/logical-backup/cronjob-backup.yaml`). Mode
`0700`/`0600` therefore does not separate NFS clients: any client the export
accepts is uid 1000 and can read `app.ini` (the secret key and internal
token) and the access-token hashes in the sqlite file. This repo does not
record an IP allow-list for that export. The known clients are the k3s nodes
that mount `nfs-cold`. The copy is not encrypted. `nfs-cold` is Retain.

## Retention

After an OK run only: the newest 7 OK runs, plus the newest OK run in each of
the four trailing 7-day windows anchored on the newest OK run's UTC date.
The newest OK run is never deleted. A run whose `STATUS` is not exactly `OK`
is not `LATEST` and does not count as one of the seven. Nothing is deleted
when today's run failed. Non-OK runs older than the oldest kept OK run are
removed on the next success.

## Schedules (UTC)

Backup 03:10 daily. Drill 04:10 on the 1st, after that day's backup and
before the 04:30 logical backup. Alerts: `BifrostGiteaBackupMissing` (no
success for 26 h) and `BifrostGiteaBackupDrillStale` (no passing drill for
35 days), next to the logical-backup rules.

Both pods are selected by `gitea-backup-deny-all`: no ingress and no egress.
The drill clones from `127.0.0.1` inside the pod.

Not under Argo, like `k8s/data/logical-backup`.

## Apply

```bash
kubectl apply -k k8s/cicd/gitea-backup
kubectl apply -f k8s/monitoring/bifrost-alerting-rules.yaml
```

The first command creates the claim, the two CronJobs, the script ConfigMap,
and the deny-all NetworkPolicy. It does not restart Gitea. The second updates
the existing PrometheusRule `monitoring/bifrost-alerting-rules` (the whole
object, with the two new alerts added).

The maintainer rows are in `MAINTAINERS.yaml`. The in-cluster copy is
ConfigMap `monitoring/maintainer-reconcile`, written by:

```bash
kubectl apply -k k8s/monitoring/maintainer-reconcile
```

Disabling registration is a separate change to `k8s/cicd/gitea/deployment.yaml`
(`GITEA__service__DISABLE_REGISTRATION=true`). Applying that file rolls the
Deployment. Strategy is Recreate, so the Gitea pod restarts. Apply it on its
own, not as part of the backup:

```bash
kubectl apply -f k8s/cicd/gitea/deployment.yaml
```

## Run now, drill now

Run a backup once before the first drill. The drill's report mount is
`subPath: drills`, and that directory is created by the backup job.

```bash
kubectl -n cicd create job --from=cronjob/gitea-backup gitea-backup-manual-$(date +%s)
kubectl -n cicd create job --from=cronjob/gitea-backup-drill gitea-backup-drill-manual-$(date +%s)
```

## Tests

Static checks live in this directory and are not part of a repo-wide pytest
run:

```bash
python3 -m pytest k8s/cicd/gitea-backup/test_gitea_backup.py -q
```

`rehearse.sh` is the Docker rehearsal (one container set at a time). It does
not talk to the cluster.
