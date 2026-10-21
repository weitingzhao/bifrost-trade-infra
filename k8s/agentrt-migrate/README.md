# Agent runtime migrations (W-31)

These plain Jobs are outside every infra Argo Application source path. They are
not overlay resources; creating one does not affect Argo Application health.
The image is the explicit platform-api image rendered by that environment's overlay.

After the order written at the top of db-step `2026-10-14-w31-agentrt-2-connect` (roles, the role-matrix
transition branch, passwords, databases, connect, Postgres ingress policy),
the Owner checks the embedded migration SQL and compares the manifest image digest
with the running platform-api container's imageID (a matching tag alone is insufficient).
If the tag changed, update the Job image to the verified running digest before creating it.
The image must include the reviewed `platform-api agentrt-migrate` subcommand.
The Owner creates a fresh Job with:

STG first:

```bash
kubectl create -f k8s/agentrt-migrate/stg/job.yaml
```

Wait until that Job completes and the STG checks pass. PROD only after its DDL is
approved:

```bash
kubectl create -f k8s/agentrt-migrate/prod/job.yaml
```

PROD creation requires prior approval of its DDL. `generateName` creates a fresh
name on each invocation; do not apply these manifests. Watch the generated Job
through completion before enabling runtime use. Jobs have no retry, a 900-second
deadline and a seven-day TTL; their wait-pg init container handles policy propagation.
DEV migration runs locally using the DEV owner identity; there is no DEV cluster Job.

## Since TD-411 (Owner 2026-10-21: 「STG 的迁移由发布流水线先跑、PROD 照旧由我建 Job」)

- **STG**: `bifrost-deliver-platform` runs these migrations itself before it rolls out
  (`k8s/cicd/tekton/task-agentrt-migrate-stg.yaml`): the Job above, with the api image the
  run has just built pinned by digest and an annotation naming the run. A Job that fails
  stops the run before gitops-sync and rollout; the run's log says which migrations it applied.
  The STG Job above stays for a database the pipeline has not reached.
- **PROD**: still this Owner-created Job. Before it rolls out, `bifrost-deliver-platform-prod`
  checks that PROD's database has applied every migration the build carries, with the same
  bytes, as PROD's platform-api reports on `/health` (`agentrt_schema_applied`). If one is
  missing, the run stops and prints, with the build's digest filled in, the one command that
  creates this Job with the build's image instead of `:prod` (a `sed` of the image line piped
  to `kubectl create -f -`). Run that printed line, watch the Job finish, then start the release
  again. The check refuses as well when PROD's health does not report the applied list.
