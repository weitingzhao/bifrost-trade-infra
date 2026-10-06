# MinIO for the Postgres backups, on the NAS

`compose.yaml` runs the backup MinIO directly on the NAS (192.168.10.20, Debian 12,
Docker). It takes over the directory that `data/minio` in the cluster used over NFS,
so the 272 GiB of backups are not copied. Why: on NFS, MinIO lost multipart parts
underneath itself (InvalidPart on 10-03 and 10-04) and kept its drive offline for
6h40m after an 8-minute NAS stall on 10-05.

On the NAS the files live in `/volume1/docker/minio-backup/`:

| File | Source |
|---|---|
| `compose.yaml` | this directory |
| `minio-RELEASE.2024-12-18T13-15-44Z.docker.tar` + `SHA256SUMS` | the image; docker.io no longer serves `minio/minio`, so it is loaded from this tarball (exported from the in-cluster registry, config digest `sha256:6aed1b69…`, the image the cluster MinIO runs) |
| `.env` | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`, written from the cluster Secret `data/minio-backup`; never in git |

`k8s_admin` can write the directory but cannot use Docker; the `sudo` steps are the
Owner's.

## 1. Prepare (any time; nothing starts)

```bash
# Owner, on the Mac: credentials from the cluster Secret straight into .env (mode 600)
kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml -n data get secret minio-backup \
  -o go-template='MINIO_ROOT_USER={{.data.ACCESS_KEY_ID|base64decode}}{{"\n"}}MINIO_ROOT_PASSWORD={{.data.SECRET_ACCESS_KEY|base64decode}}{{"\n"}}' \
  | ssh nas-k8s 'umask 077; cat > /volume1/docker/minio-backup/.env'

# Owner, on the NAS: load the image and check it
cd /volume1/docker/minio-backup && sha256sum -c SHA256SUMS
sudo docker load -i minio-RELEASE.2024-12-18T13-15-44Z.docker.tar
sudo docker image ls minio/minio      # IMAGE ID 6aed1b694901
sudo docker compose config --quiet && echo compose ok
```

Do not run `docker compose up` yet.

## 2. Cutover (outside 03:00–04:30 UTC, no Backup running)

1. Cluster: `kubectl -n data scale deploy/minio --replicas=0` and wait until the pod
   is gone. WAL archiving fails and PostgreSQL retries; the segments wait in pg_wal.
2. NAS (Owner): `cd /volume1/docker/minio-backup && sudo docker compose up -d`, then
   `curl -fsS http://192.168.10.20:9000/minio/health/cluster` answers 200.
3. Cluster: point the Service `data/minio` at 192.168.10.20:9000 (selector removed,
   EndpointSlice added). The Cluster spec keeps `endpointURL:
   http://minio.data.svc.cluster.local:9000`.
4. Verify: ContinuousArchiving True, the queued WAL drains, the bucket lists, an
   on-demand Backup completes, the next 03:00 backup completes.

## Rollback

`sudo docker compose down` on the NAS, put the Service selector back,
`kubectl -n data scale deploy/minio --replicas=1`. Same directory, nothing to copy.
At no point may both MinIO servers run on this directory.

## Operating it

- `k8s_admin` may run exactly these without a password (`/etc/sudoers.d/k8s_admin-minio`,
  set up by the Owner 2026-10-06); everything else needs the Owner. The directory,
  `compose.yaml` and `.env` are root-owned, so changing the configuration is the Owner's.

  ```bash
  sudo -n docker compose -f /volume1/docker/minio-backup/compose.yaml ps
  sudo -n docker compose -f /volume1/docker/minio-backup/compose.yaml logs --tail 200 minio
  sudo -n docker compose -f /volume1/docker/minio-backup/compose.yaml restart minio
  sudo -n docker compose -f /volume1/docker/minio-backup/compose.yaml up -d
  ```

  A UGOS update may reset `/etc/sudoers.d`; re-add the rule if `sudo -n` asks for a password.
- Monitoring: `k8s/monitoring/bifrost-minio-nas.yaml` (ScrapeConfig, static target
  192.168.10.20:9000, `/minio/v2/metrics/cluster`, public on the LAN) and the alerts
  `BifrostMinIONasDown`, `BifrostMinIONasDriveOffline`, `BifrostMinIONasSpaceLow`.

## After a week of good backups

Move the directory to its own shared folder (a rename inside `/volume1` is instant
on btrfs) and update the volume path; retire `data/minio`, its PVC and
`k8s/data/backup-retry.yaml`.
