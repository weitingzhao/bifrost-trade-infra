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
         expect 200, and a row feedback_writer|trade-api-feedback (the pod runs 0.7.5) with no analytics_writer row
commit:  kubectl -n bifrost-dev delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30882/api/research/research/feedback/summary   (200)

## stg
dry-run: curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30880/api/research/research/feedback/summary
         ip=$(kubectl -n bifrost-stg get pod -l app.kubernetes.io/name=api-research -o jsonpath='{.items[0].status.podIP}')
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -XtA -c "SET default_transaction_read_only=on;" -c "SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE client_addr = '$ip' GROUP BY 1, 2"
         expect 200, and a row feedback_writer|trade-api-feedback (the pod runs 0.7.5) with no analytics_writer row
commit:  kubectl -n bifrost-stg delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30880/api/research/research/feedback/summary   (200)

## prod
dry-run: curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30881/api/research/research/feedback/summary
         ip=$(kubectl -n bifrost-prod get pod -l app.kubernetes.io/name=api-research -o jsonpath='{.items[0].status.podIP}')
         kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -XtA -c "SET default_transaction_read_only=on;" -c "SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE client_addr = '$ip' GROUP BY 1, 2"
         expect 200, and a row feedback_writer|trade-api-feedback (the pod runs 0.7.5) with no analytics_writer row
commit:  kubectl -n bifrost-prod delete secret bifrost-analytics-secrets
verify:  curl -s -o /dev/null -w '%{http_code}\n' http://192.168.10.73:30881/api/research/research/feedback/summary   (200)
then, once dev, stg and prod are all done: an infra commit removes the ANALYTICS_PG_HOST / PORT / USER / DATABASE /
         PASSWORD entries (and their comment) from Deployment api-research in k8s/base/apis/manifest.yaml, and
         docs/SECRETS.md drops bifrost-analytics-secrets from the Trade namespaces.
