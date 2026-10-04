---
id: 2026-10-04-td49-revoke-analytics-from-trade-api
envs: dev stg prod
when: after
done:
---
# TD-49 D4 / TD-77 E5, last part: take analytics_writer away from trade-api

Only after `2026-10-04-td49-feedback-writer-role` is done for the env **and** that env runs api >= 0.7.5 **and**
its feedback GETs answered 200 on the new pods (the role step's verify). api 0.7.5 never reads `ANALYTICS_PG_*`.

**What "revoke" is here.** trade-api has no Golden Source role of its own to REVOKE from: it borrowed Research's
`analytics_writer`, whose grants Research (research-api, Dagster) still needs. So nothing is revoked in the database.
trade-api loses the role by losing its credential: the Secret `bifrost-analytics-secrets` leaves the three Trade
namespaces (api-research is its only reader there, read-only 2026-10-04: no other Deployment, Job or CronJob in
bifrost-dev / stg / prod references it), and a later infra commit drops the five `ANALYTICS_PG_*` env from
`k8s/base/apis/manifest.yaml` (their `secretKeyRef` is `optional: true`, so pods start without the Secret meanwhile;
the env stays until all three envs are done so a rollback to the 0.7.3 image keeps working).

**State read-only 2026-10-04 05:4x UTC (lane AF): ready in all three envs.** Every env runs api **0.8.1**
(`bifrost-api 0.8.1` installed in api-research; no module of the installed `bifrost_api` or `bifrost_core`
mentions `ANALYTICS_PG_`); `…/feedback/summary` answers 200 on :30882 / :30880 / :30881; Golden Source sessions
from the api-research pod IPs are `feedback_writer | trade-api-feedback` only. The pods still *receive*
`ANALYTICS_PG_PASSWORD` (optional `secretKeyRef`) but never read it. The one `analytics_writer` session left on
bifrost_golden_source at that time came from 10.42.8.176 = `research/dagster-webserver` (Running; a completed
cicd pod had held the same IP earlier) — Research's own login, not Trade's, and not touched by this step
(Research loses `bifrost`, not `analytics_writer`: db-step `2026-10-04-d2-analytics-writer-off-bifrost`).
`bifrost-analytics-secrets` also sits in `plugin-market-data`, where no workload references it (read-only
2026-10-04): delete it there in the same pass (no Trade release involved; restore the same way as below).

No DDL. The one irreversible-looking action, `kubectl delete secret`, is reversible: the same value still lives in
`research/bifrost-analytics-secrets` (`kubectl get secret -n research bifrost-analytics-secrets -o json`, strip
metadata, apply into the namespace again).

Not in this step (Owner's call, see the lane report): rotating `analytics_writer`'s password. Deleting the Secret
does not invalidate a credential that sat in three more namespaces; rotating it means updating
`research/` and `plugin-market-data/bifrost-analytics-secrets` and restarting research-api and Dagster together.

## dev
dry-run: curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30882/api/research/research/feedback/summary
         ip=$(kubectl -n bifrost-dev get pod -l app.kubernetes.io/name=api-research -o jsonpath='{.items[0].status.podIP}')
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -XtA -c "SET default_transaction_read_only=on;" -c "SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE client_addr = '$ip' GROUP BY 1, 2"
         expect 200, and a row feedback_writer|trade-api-feedback (api >= 0.7.5; 0.8.1 on 2026-10-04) with no analytics_writer row
         every analytics_writer session on the cluster comes from a Running pod in namespace research (none from bifrost-dev):
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -XtA -c "SET default_transaction_read_only=on;" -c "SELECT DISTINCT host(client_addr) FROM pg_stat_activity WHERE usename = 'analytics_writer'" | grep -v '^SET$' | while read -r a; do kubectl get pods -A --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.status.podIP} {.metadata.namespace}/{.metadata.name}{"\n"}{end}' | awk -v a="$a" '$1 == a'; done
commit:  kubectl -n bifrost-dev delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30882/api/research/research/feedback/summary   (200)

## stg
dry-run: curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30880/api/research/research/feedback/summary
         ip=$(kubectl -n bifrost-stg get pod -l app.kubernetes.io/name=api-research -o jsonpath='{.items[0].status.podIP}')
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -XtA -c "SET default_transaction_read_only=on;" -c "SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE client_addr = '$ip' GROUP BY 1, 2"
         expect 200, and a row feedback_writer|trade-api-feedback (api >= 0.7.5; 0.8.1 on 2026-10-04) with no analytics_writer row
         every analytics_writer session on the cluster comes from a Running pod in namespace research (none from bifrost-stg):
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -XtA -c "SET default_transaction_read_only=on;" -c "SELECT DISTINCT host(client_addr) FROM pg_stat_activity WHERE usename = 'analytics_writer'" | grep -v '^SET$' | while read -r a; do kubectl get pods -A --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.status.podIP} {.metadata.namespace}/{.metadata.name}{"\n"}{end}' | awk -v a="$a" '$1 == a'; done
commit:  kubectl -n bifrost-stg delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30880/api/research/research/feedback/summary   (200)

## prod
dry-run: curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30881/api/research/research/feedback/summary
         ip=$(kubectl -n bifrost-prod get pod -l app.kubernetes.io/name=api-research -o jsonpath='{.items[0].status.podIP}')
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -XtA -c "SET default_transaction_read_only=on;" -c "SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE client_addr = '$ip' GROUP BY 1, 2"
         expect 200, and a row feedback_writer|trade-api-feedback (api >= 0.7.5; 0.8.1 on 2026-10-04) with no analytics_writer row
         every analytics_writer session on the cluster comes from a Running pod in namespace research (none from bifrost-prod):
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -XtA -c "SET default_transaction_read_only=on;" -c "SELECT DISTINCT host(client_addr) FROM pg_stat_activity WHERE usename = 'analytics_writer'" | grep -v '^SET$' | while read -r a; do kubectl get pods -A --field-selector=status.phase=Running -o jsonpath='{range .items[*]}{.status.podIP} {.metadata.namespace}/{.metadata.name}{"\n"}{end}' | awk -v a="$a" '$1 == a'; done
commit:  kubectl -n bifrost-prod delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30881/api/research/research/feedback/summary   (200)
then: the infra commit "api-research: drop the ANALYTICS_PG_* env" (lane AF, branch td-batch/2026-10-04-lane-af)
         removes the five ANALYTICS_PG_* entries from Deployment api-research (k8s/base/apis/manifest.yaml) and the
         Secret's row from docs/SECRETS.md. It may merge before or after the deletes: api >= 0.7.5 reads neither, and
         the secretKeyRef is optional. Once all three envs run it, a rollback to an api <= 0.7.4 image is no longer
         possible without restoring both (not planned: every env is on 0.8.1).
         also: plugin-market-data has the same Secret and no reader: kubectl -n plugin-market-data delete secret bifrost-analytics-secrets
         live drift seen on the way (not in git, not part of this step): DEV and STG api-research carry an env
         SEPA_USE_ANALYTICS=true that nothing reads since 2026-08-24 (Wave 14E).
