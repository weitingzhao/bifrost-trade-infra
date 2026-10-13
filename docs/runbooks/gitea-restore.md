# Gitea backup commissioning and restore (Owner, off cluster)

The Owner's age identity stays on an Owner machine. Never upload it as a
Secret, ConfigMap, environment variable or CronJob volume. The nightly pod
verifies HTTP restore before encryption and cannot decrypt NAS archives.
The one-time commissioning below proves encryption to the real Owner key.

## Apply and commission, in order

Run from merged `main` of `bifrost-trade-infra`, after the coordinator's
Docker rehearsal passes. These are **Owner** commands; an Agent's cluster
writes must instead use platform actions. No command below is run by the
implementation task. Apply can overwrite live drift; inspect diffs first.

1. Inspect rendered backup resources and the whole shared alert object:

   ```bash
   kubectl diff -k k8s/cicd/gitea-backup
   kubectl diff -f k8s/monitoring/bifrost-alerting-rules.yaml
   kubectl diff -k k8s/monitoring/maintainer-reconcile
   ```

   `diff` exit 1 means a difference. Check NAS permission/space, the Gitea
   pod's same-node read-only PVC sharing, and available node ephemeral space
   (stage, archive and HTTP mirror clones can require several live-tree
   sizes). emptyDir starts writable (0777), so uid 1000 needs no fsGroup.
   `/work` has a 60Gi limit since 2026-10-12 (the node had 432 GB free; the live size
   cannot be read from outside the pod). The first run's SIZES.tsv gives the real size;
   revisit the limit then.

2. If round 1 was installed, remove the obsolete drill and wait for any
   already running drill Job to finish before proceeding. `apply -k` does
   not prune it. Inspect Jobs first, do not kill an unrelated Job:

   ```bash
   kubectl -n cicd get jobs
   kubectl -n cicd delete cronjob gitea-backup-drill --ignore-not-found
   ```

   This removes only that CronJob; dependent Jobs are garbage collected by
   default. If a drill is active, wait for it to finish **before** deletion.

3. Install alert and maintainer inventory, then backup resources:

   ```bash
   kubectl apply -f k8s/monitoring/bifrost-alerting-rules.yaml
   kubectl apply -k k8s/monitoring/maintainer-reconcile
   kubectl apply -k k8s/cicd/gitea-backup
   kubectl -n cicd get pvc gitea-backup
   ```

   First command updates the **whole** existing PrometheusRule, adds the
   never-success condition and removes the monthly Gitea drill alert. Second
   applies the inventory/script ConfigMap, ServiceAccount, ClusterRole and
   ClusterRoleBinding, Role and RoleBinding, and the maintainer CronJob,
   following its `cronjob.yaml` header. It does not create the optional
   maintainer auth Secret. Third manages NAS PVC (dynamic PV/NAS directory
   on first application), script ConfigMap, public recipient ConfigMap, one
   CronJob and NetworkPolicy. It does not restart Gitea or apply registration
   changes. Wait for PVC Bound. Old hashed script ConfigMaps may remain;
   they are not live references and do not hold identities.

4. Run once and wait for completion (no drill Job):

   ```bash
   backup_job="gitea-backup-manual-$(date +%s)"
   kubectl -n cicd create job --from=cronjob/gitea-backup "$backup_job"
   # Two waits race: return as soon as either terminal condition is seen.
   kubectl -n cicd wait --for=condition=complete "job/$backup_job" --timeout=3700s &
   complete_wait=$!
   kubectl -n cicd wait --for=condition=failed "job/$backup_job" --timeout=3700s &
   failed_wait=$!
   while kill -0 "$complete_wait" 2>/dev/null && kill -0 "$failed_wait" 2>/dev/null; do sleep 1; done
   kill "$complete_wait" "$failed_wait" 2>/dev/null || true
   wait "$complete_wait" 2>/dev/null || true
   wait "$failed_wait" 2>/dev/null || true
   test "$(kubectl -n cicd get job "$backup_job" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}')" = True
   kubectl -n cicd logs "job/$backup_job" -c fetch-tools
   kubectl -n cicd logs "job/$backup_job" -c backup
   ```

   The create command does not wait. On wait failure, inspect Job/Pod events
   and logs; do not continue commissioning as though a backup succeeded.
   Check the NAS LATEST run has STATUS=OK and VERIFIED, and only the six
   listed files. Confirm policy enforcement: no ingress, only kube-dns and
   public 443; private API/Gitea/pod addresses must be blocked. Check the live
   Gitea still serves CI repositories normally.

5. On the Owner machine, mount/read the NAS and use the real key:

   ```bash
   nas_root=/path/to/cicd-gitea-backup-PV
   identity=/owner/private/age-identity.txt
   run="$nas_root/$(cat "$nas_root/LATEST")"
   test "$(cat "$run/STATUS")" = OK
   awk '!/^#/ {print}' "$run/SHA256SUMS" > /tmp/gitea-ciphertext-sums
   (cd "$run" && sha256sum -c /tmp/gitea-ciphertext-sums)
   commissioning_dir=$(mktemp -d)
   age -d -i "$identity" -o "$commissioning_dir/data.tar" "$run/data.tar.age"
   tar -tf "$commissioning_dir/data.tar"
   bash k8s/cicd/gitea-backup/restore.sh "$run" "$identity" "$commissioning_dir/data"
   expected=$(awk '$1=="repository_count" {print $2}' "$run/SIZES.tsv")
   manifest_count=$(awk 'NR>1 {n++} END {print n+0}' "$commissioning_dir/data.MANIFEST.tsv")
   disk_count=$(find "$commissioning_dir/data/git/repositories" -mindepth 2 -maxdepth 2 -type d -name '*.git' ! -name '*.wiki.git' | wc -l | tr -d ' ')
   test "$expected" = "$manifest_count"
   test "$expected" = "$disk_count"
   ```

   This decrypts locally, lists the archive, checks its plaintext sha256 via
   restore.sh and compares repository counts. Use the pinned/compatible age
   on the Owner machine. `restore.sh` requires sha256sum (macOS: GNU coreutils
   on PATH). Record successful commissioning without key/token output. Keep
   or securely remove the local plaintext according to the Owner's backup
   handling practice. No decrypted data goes back onto the NAS.

6. Wait for the next **scheduled** nightly Job success and verify the
   Prometheus last-success metric and no Gitea missing alert. A manual Job
   alone cannot clear the CronJob metric condition. Confirm failures/Pending
   beyond 26h are visible, including when last-success is absent. Inspect
   the maintainer reconciliation after its next scheduled run.

Registration off (`1c931da`) remains separately reviewed/applied; this
runbook does not roll the live Deployment.

## Restore onto a new volume

1. Choose an OK run and complete the off-cluster decrypt/check above. A
   truncated ciphertext fails checksum or authenticated age decryption.
   Restore.sh refuses an existing target, so no existing live data is erased.
2. Perform HTTP verification ONLY on a separate throwaway copy. Never run
   `verify-stage.sh` on the tree or volume that will go live: it rebases paths,
   disables mirrors/cron/actions/mail, restricts webhooks and HTTP to loopback,
   and generates a token in the copied DB. In an isolated environment with the
   matching Gitea image and tools, restore a copy and run:

   ```bash
   bash k8s/cicd/gitea-backup/restore.sh "$run" "$identity" /path/to/throwaway
   bash k8s/cicd/gitea-backup/verify-stage.sh /path/to/throwaway /path/to/throwaway.MANIFEST.tsv /path/to/throwaway.VERIFIED
   ```

   Delete the throwaway copy after checking HTTP clones/refs. Check avatars,
   attachments and LFS separately for business completeness. For the tree
   that will go live, unpack **fresh** to a distinct nonexistent target:

   ```bash
   bash k8s/cicd/gitea-backup/restore.sh "$run" "$identity" /path/to/fresh-live-data
   ```

   Never run the verifier on fresh-live-data or copy files from throwaway.
3. Provision a **new** empty volume at least as large as the original Gitea
   claim, with the intended node affinity. Keep the old volume and backup
   intact. Stop CI writers and mirrors; scale live Gitea down through the
   Owner's platform action or Owner command and wait for the old pod to exit.
4. Transfer the untouched fresh-live-data tree to the new volume using an
   Owner-controlled path. Place its contents at mount root `/data`, not
   `/data/data`; chown Gitea files to 1000:1000. Do not transfer the age identity
   or adjacent manifest into the pod. SSH host keys were excluded; allow the
   image entrypoint to create new keys and communicate fingerprints to clients.
5. Inspect app.ini database PATH, repository ROOT, custom/conf, APP_DATA_PATH,
   LFS/attachment paths against `/data`; the archive contains original
   settings. Repoint the Deployment PVC reference to the **new** claim in a
   separately reviewed manifest, preserving Gitea 1.21.11 and Recreate strategy.
   For a different filesystem layout, rebase copied paths first. Do not enable
   registration or change service secrets accidentally.
6. Start the live Deployment against the new claim, wait for rollout/HTTP
   readiness and test CI clone/API operations. Resume writers/mirrors only
   after those pass. Keep the old claim until Owner acceptance. If validation
   fails, stop the replacement, repoint to the intact old claim and wait for
   readiness before resuming writers. Schedule/commission backup of the new
   volume again; no monthly restore job or private cluster key is needed.

## Recover a stale lock or a future timestamp

Owner only, on the mounted NAS, with no active backup Job. Inspect Jobs first
(`kubectl -n cicd get jobs,pods`); do not remove a live lock. The one-hour Job
deadline is shorter than the three-hour lock threshold. Inspect the lock:

```bash
ls -ld "$nas_root/.lock"
cat "$nas_root/.lock/started"  # UTC epoch seconds; compare with date -u +%s
```

The next run automatically reports/removes a lock older than three hours.
If its timestamp is invalid, or manual recovery is needed after proving no
Job is active, the Owner may `rm -rf "$nas_root/.lock"`. New locks store a
start time; an interrupted initial write falls back to directory mtime.

After a clock jumps forward and is corrected, the newest future-named run
(or `.partial`) causes `clock not monotonic` until addressed. Keep the data:
move all future-stamped entries outside the backup root to an Owner quarantine
on the same NAS, without renaming timestamps into fake historical successes.
If LATEST names one of these, first select an existing, correctly dated OK run
and verify its checksums. Write that stamp to `$nas_root/LATEST.recovery.tmp`
and rename it to LATEST, then quarantine the future entries. If no correctly
dated OK run exists, preserve the future backup in quarantine, remove LATEST
and let the next successful run create it. Confirm the machine's UTC clock,
start a manual backup and commission it before resuming the nightly schedule.
Never delete the only verified copy to fix the clock.
