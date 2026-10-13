# Gitea nightly verified, encrypted backup (W-41)

One CronJob, `cicd/gitea-backup`, runs at 03:10 UTC. It uses the Deployment's
`gitea/gitea:1.21.11`, uid/gid 1000, required same-node pod affinity and the
same tolerations. Both the live PVC and its mount are read-only. There is no
ServiceAccount token, Secret volume, Secret environment or API client.
Self-registration off is the separate commit `1c931da`; this change does not
modify or apply the Gitea Deployment.

Plaintext exists only in the pod's `/work` emptyDir. SQLite's online backup
uses `file:<path>?mode=ro`; `gitea dump` is never used. After copying the data
tree, both sets are normalized with `LC_ALL=C sort -u` (duplicates are
checked by counts, independently of ordering). The repository set from
SQLite must equal the copied directory set.
In Gitea 1.21.11 `RepoPath` uses `user.lower_name` (including organizations)
and `repository.lower_name`: `git/repositories/<owner>/<name>.git`. The
script fails closed on other ROOT layouts, missing owners, unsafe paths or
zero repositories. A set mismatch discards the stage and repeats both DB
and tree copies, up to three times; failures name database-only/disk-only
repositories in the Job log, explicitly including non-wiki orphan directories.
Wiki repositories (`*.wiki.git`) are archived and fsck checked, but excluded
from set comparisons and HTTP cloning. SQLite integrity and every repository's
`git fsck --connectivity-only` must pass; fsck has three copy attempts.

The archive includes the SQLite copy in its original location, app.ini and
the complete conf/custom tree, repositories, avatars, attachments, uploads,
actions logs and LFS. SQLite sidecars and rebuildable sessions, queues,
indexers, logs and temp are excluded. The image's root-owned `/data/ssh`
host keys cannot be read by uid 1000; restore creates new SSH host keys.

The archive is made **before** Gitea changes the stage. `verify-stage.sh`
must run ONLY on a throwaway copy: it mutates app.ini and the database. It
rebases copied paths, binds HTTP to 127.0.0.1:3000 and disables SSH. It
disables webhooks outside loopback, mirror sync, cron, actions and mail, and
creates
a throwaway access token in the copied database, clones every repository
in the manifest over HTTP and compares every ref. All Gitea logs, token
output and clones stay in `/work` and are removed. The archive retains the
original configuration and database, not the verification token. Any
verification failure prevents publishing any backup data onto the NAS.

The NAS directory `<UTC stamp>/` contains exactly:

| File | Content |
|---|---|
| `data.tar.age` | One age-encrypted full archive |
| `MANIFEST.tsv.age` | Encrypted repository paths and every ref=sha |
| `SIZES.tsv` | Plaintext DB/repository/archive byte sizes and repository count; no names |
| `SHA256SUMS` | Both ciphertext hashes; comment `# plaintext_sha256 data.tar <hash>` |
| `VERIFIED` | Number of repositories and refs matched over HTTP |
| `STATUS` | Exactly `OK`, written last |

Age reads `/work` and writes ciphertext directly to `<stamp>.partial/`.
A rejected age header is removed. The directory is created exclusively,
never reused, and renamed only after verification, ciphertext checksums and
STATUS checks. Directories are 0700 and files 0600; Bash's `set -euo pipefail`
checks redirections, pipelines, copy, rename and chmod errors. LATEST is
prepared and read back before STATUS. TERM/INT are ignored from just before
the final directory rename until LATEST is renamed. Cleanup never changes a
final directory. A rename error leaves any finalized OK copy intact, keeps
the previous LATEST and prevents retention.

A NAS `mkdir` lock records its start epoch in `.lock/started`. A held lock
at most three hours old fails immediately, reporting its age. An older lock
(longer than the one-hour Job deadline) is reported, removed and retaken.
Two runs starting in the same instant beside a stale lock could both proceed.
This rare race is accepted: different start stamps keep directories distinct,
and each run publishes its directory and LATEST atomically. An identical
second stamp is refused by exclusive directory creation; no shared run is
reused. The normal CronJob also forbids overlap. There is no stale-lock
breaker state.
A stamp must exceed the newest existing run, including non-OK and partial
runs; clock rollback fails before retention (recovery is in the runbook).
Only after success: keep the newest **14 OK runs**, always protect LATEST,
and remove `.partial` leftovers older than two days. Other non-OK final
runs are left for inspection. A failed run performs no retention.

The NAS squashes clients to uid 1000: file permissions do not isolate NFS
clients. The archive and manifest are encrypted to the same Owner public
key as cluster-state-backup. The private key never enters the cluster.
Legacy plaintext runs from round 1 are **not** encrypted retroactively;
the Owner must handle those separately if any exist.

The alpine:3.22 init container downloads only the exact pinned amd64 age
release/checksum used by cluster-state-backup into `/tools`, with up to
three download attempts three seconds apart. Stage token generation retries
up to ten times while SQLite is busy during web startup. GitHub download
availability is a backup dependency. This policy is looser than round 1's
no-egress policy: DNS to kube-dns and public TCP 443 are needed for age.
There is no ingress; HTTPS to 10/8, 172.16/12 and 192.168/16 is excluded.
It permits neither API server/Gitea/pod endpoints in these private ranges
nor arbitrary DNS destinations. There are no IPv6 egress rules. Public
HTTPS is available to the whole pod, not just the init container; this is
the fixed download design's tradeoff. NAS PVC traffic is a node mount.

`BifrostGiteaBackupMissing` fires after 26h plus 30m without success, also
when the CronJob has existed for 26h but never succeeded. Manual Jobs do
not change CronJob last-success metrics: wait for a scheduled success too.
The checkout's cluster-state rule currently contains only the stale-success
expression, despite TASK-2 referring to a never-success branch; Gitea adds
an explicit `kube_cronjob_created` + `absent(last_successful_time)` branch.

This directory is not under Argo. Owner commissioning/application sequence
and human restore are in `docs/runbooks/gitea-restore.md`. There is no monthly
drill CronJob, alert, maintainer row, subPath or cluster identity key.
All Owner commands run from merged `main` of `bifrost-trade-infra`, after
the rehearsal passes: inspect diffs, then apply the whole alert object,
`kubectl apply -k k8s/monitoring/maintainer-reconcile`, and
`kubectl apply -k k8s/cicd/gitea-backup`. The maintainer kustomization applies
the inventory/script ConfigMap, ServiceAccount, ClusterRole/Binding,
Role/Binding and CronJob, as its `cronjob.yaml` header documents. It does
not create the optional auth Secret. See the runbook for commissioning.

Offline checks (no Docker, no network):

```bash
python3 -m pytest k8s/cicd/gitea-backup/test_gitea_backup.py k8s/cicd/gitea-backup/test_backup_logic.py -q
bash -n k8s/cicd/gitea-backup/backup.sh
bash -n k8s/cicd/gitea-backup/verify-stage.sh
bash -n k8s/cicd/gitea-backup/restore.sh
bash -n k8s/cicd/gitea-backup/rehearse.sh
```

Coordinator rehearsal: `bash k8s/cicd/gitea-backup/rehearse.sh`. It fetches the
pinned age archive and creates a disposable age keypair in a separate Docker
volume. Every backup/Gitea/restore container uses `--network none`; only the
fetch container has network. The backup never mounts that identity volume.
PASS lines cover the handshake push during the copy pipeline, real decrypt
and HTTP restore, repository creation/deletion on each of three retries,
missing object, full tmpfs at manifest encryption, concurrent lock, clock
rollback, one clone with refs different from the manifest, and authenticated
rejection of a ciphertext cut in its payload. Seeds are private repositories
`bifrost/x`, `bifrost/x-y`, a wiki on x, and `admin/gamma`. It does not prove
pull mirrors, NetworkPolicy enforcement, real data sizes, or the Owner key.

The sole opt-in test variable is `GITEA_BACKUP_TEST_HOOK_DIR`; without it all
hooks are inert. `wait-<phase>` files enable bounded ready/release handshakes;
`fail-<phase>` triggers deliberate test write failures. The production
CronJob does not set it. Offline tests also obstruct actual redirections and
make tool writes fail; fake age is not evidence of real cryptography.
