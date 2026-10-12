# Gitea backup commissioning and restore (Owner, off cluster)

The Owner's age identity stays on an Owner machine. Never upload it as a
Secret, ConfigMap, environment variable or CronJob volume. The nightly pod
verifies HTTP restore before encryption and cannot decrypt NAS archives.
The one-time commissioning below proves encryption to the real Owner key.

## Apply and commission, in order

Run from a reviewed `bifrost-trade-infra` checkout, after the coordinator's
Docker rehearsal passes. These are **Owner** commands; an Agent's cluster
writes must instead use platform actions. No command below is run by the
implementation task. Apply can overwrite live drift; inspect diffs first.

1. Inspect rendered backup resources and the whole shared alert object:

   ```bash
   kubectl diff -k k8s/cicd/gitea-backup
   kubectl diff -f k8s/monitoring/bifrost-alerting-rules.yaml
   ```

   `diff` exit 1 means a difference. Check NAS permission/space, the Gitea
   pod's same-node read-only PVC sharing, and available node ephemeral space
   (stage, archive and HTTP mirror clones can require several live-tree
   sizes). fsGroup 1000 makes emptyDirs writable by the non-root pod.

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
   kubectl -n monitoring create configmap maintainer-reconcile --from-file=reconcile.py=k8s/monitoring/maintainer-reconcile/reconcile.py --from-file=MAINTAINERS.yaml=k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml --dry-run=client -o yaml | kubectl apply -f -
   kubectl apply -k k8s/cicd/gitea-backup
   kubectl -n cicd get pvc gitea-backup
   ```

   First command updates the **whole** existing PrometheusRule, adds the
   never-success condition and removes the monthly Gitea drill alert. Second
   updates only the existing inventory/script ConfigMap; it applies no
   maintainer RBAC/SA/CronJob. Third manages NAS PVC (dynamic PV/NAS directory
   on first application), script ConfigMap, public recipient ConfigMap, one
   CronJob and NetworkPolicy. It does not restart Gitea or apply registration
   changes. Wait for PVC Bound. Old hashed script ConfigMaps may remain;
   they are not live references and do not hold identities.

4. Run once and wait for completion (no drill Job):

   ```bash
   backup_job="gitea-backup-manual-$(date +%s)"
   kubectl -n cicd create job --from=cronjob/gitea-backup "$backup_job"
   kubectl -n cicd wait --for=condition=complete "job/$backup_job" --timeout=3700s
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
   (cd "$run" && sha256sum -c SHA256SUMS)
   commissioning_dir=$(mktemp -d)
   age -d -i "$identity" -o "$commissioning_dir/data.tar" "$run/data.tar.age"
   tar -tf "$commissioning_dir/data.tar"
   bash k8s/cicd/gitea-backup/restore.sh "$run" "$identity" "$commissioning_dir/data"
   expected=$(awk '$1=="repository_count" {print $2}' "$run/SIZES.tsv")
   manifest_count=$(awk 'NR>1 {n++} END {print n+0}' "$commissioning_dir/data.MANIFEST.tsv")
   disk_count=$(find "$commissioning_dir/data/git/repositories" -mindepth 2 -maxdepth 2 -type d -name '*.git' | wc -l | tr -d ' ')
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
2. Provision a **new** empty volume at least as large as the original Gitea
   claim, with the intended node affinity. Keep the old volume and backup
   intact. Stop CI writers and mirrors; scale the live Gitea down through the
   Owner's platform action or Owner command and wait for the old pod to exit.
3. Copy the locally decrypted `data/` tree to the new volume using an
   Owner-controlled transfer/provisioning path. Place its contents at the
   mount root `/data`, not `/data/data`; chown the Gitea files to 1000:1000.
   Do not transfer the age identity or the adjacent manifest into the pod.
   SSH host keys were excluded; allow the image entrypoint to create fresh
   keys and communicate the new fingerprints to clients.
4. Inspect app.ini database PATH, repository ROOT, custom/conf, APP_DATA_PATH,
   LFS/attachment paths against `/data`; the archive contains original
   settings. Repoint the Deployment PVC reference to the **new** claim in a
   separately reviewed manifest, preserving the Gitea version 1.21.11 and
   Recreate strategy. For a different filesystem layout, rebase copied paths
   first. Do not enable registration or change service secrets accidentally.
5. Start an isolated Gitea on this new data tree, with outbound webhooks,
   mirrors and mail disabled; verify SQLite integrity and the DB/disk set,
   then clone **every** repository over HTTP and compare all refs with the
   decrypted manifest (the coordinator uses verify-stage.sh in a disposable
   Docker stage). This validation may create a temporary token: remove it
   before making the restored instance live. Check avatars, attachments and
   LFS objects separately for business completeness.
6. Start the live Deployment against the new claim, wait for rollout/HTTP
   readiness and test CI clone/API operations. Resume writers/mirrors only
   after those pass. Keep the old claim until Owner acceptance. If validation
   fails, stop the replacement, repoint to the intact old claim and wait for
   readiness before resuming writers. Schedule/commission backup of the new
   volume again; no monthly restore job or private cluster key is needed.
