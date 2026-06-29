#!/usr/bin/env bash
# Reassign public schema table/view owners to bifrost after pg_restore / prod clone.
# Required for daemon sink and db_refresh_schema (postgres-owned tables block bifrost DDL/DML).
#
# Usage:
#   ./scripts/k3s/fix-cnpg-db-ownership.sh bifrost_prod
#   ./scripts/k3s/fix-cnpg-db-ownership.sh bifrost_dev bifrost_stg
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
DATABASES=("$@")

if [[ ${#DATABASES[@]} -eq 0 ]]; then
  DATABASES=(bifrost_prod bifrost_dev bifrost_stg)
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}')"
if [[ -z "${primary}" ]]; then
  echo "CNPG cluster ${CLUSTER_NAME} not ready" >&2
  exit 1
fi

FIX_SQL="
DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT n.nspname AS schemaname, c.relname AS relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r','p','v','m','f')
      AND pg_get_userbyid(c.relowner) = 'postgres'
  LOOP
    IF r.relkind IN ('r','p') THEN
      EXECUTE format('ALTER TABLE %I.%I OWNER TO bifrost', r.schemaname, r.relname);
    ELSIF r.relkind = 'v' THEN
      EXECUTE format('ALTER VIEW %I.%I OWNER TO bifrost', r.schemaname, r.relname);
    ELSIF r.relkind = 'm' THEN
      EXECUTE format('ALTER MATERIALIZED VIEW %I.%I OWNER TO bifrost', r.schemaname, r.relname);
    ELSIF r.relkind = 'f' THEN
      EXECUTE format('ALTER FOREIGN TABLE %I.%I OWNER TO bifrost', r.schemaname, r.relname);
    END IF;
  END LOOP;
END
\$\$;
"

for db in "${DATABASES[@]}"; do
  echo "==> ALTER OWNER public.* → bifrost on ${db}"
  kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${db}" -v ON_ERROR_STOP=1 -c "${FIX_SQL}"
  cnt="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${db}" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner='bifrost'")"
  echo "   ${db}: ${cnt} tables owned by bifrost"
done

echo "Done."
