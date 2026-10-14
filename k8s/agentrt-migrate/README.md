# Agent runtime migrations (W-31)

These plain Jobs are outside every infra Argo Application source path. They are
not overlay resources; creating one does not affect Argo Application health.
The image is the explicit platform-api image rendered by that environment's overlay.

After roles → passwords → databases ready → connect → Postgres ingress policy,
the Owner checks the embedded migration SQL and compares the manifest image digest
with the running platform-api container's imageID (a matching tag alone is insufficient).
If the tag changed, update the Job image to the verified running digest before creating it.
The image must include the reviewed `platform-api agentrt-migrate` subcommand.
The Owner creates a fresh Job with:

```bash
kubectl create -f k8s/agentrt-migrate/stg/job.yaml
kubectl create -f k8s/agentrt-migrate/prod/job.yaml
```

PROD creation requires prior approval of its DDL. `generateName` creates a fresh
name on each invocation; do not apply these manifests. Watch the generated Job
through completion before enabling runtime use. Jobs have no retry, a 900-second
deadline and a seven-day TTL; their wait-pg init container handles policy propagation.
DEV migration runs locally using the DEV owner identity; there is no DEV cluster Job.
