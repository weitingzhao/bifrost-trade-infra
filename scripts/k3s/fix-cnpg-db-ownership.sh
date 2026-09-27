#!/usr/bin/env bash
# Reassign public schema table/view/type owners to bifrost after pg_restore / prod clone.
# Required for daemon sink and db_refresh_schema (postgres-owned tables block bifrost DDL/DML).
# Indexes and OWNED BY sequences follow their table. Idempotent: only touches postgres-owned objects.
# clone-cnpg-prod-to-dev-stg.sh runs it after restore; platform-api data clone runs the equivalent
# (dataCloneOwnerSQL, re-owning to the database owner).
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
  -- dim_*_t enums (and any domains) — STG/PROD have them owned by bifrost.
  FOR r IN
    SELECT n.nspname AS schemaname, t.typname, t.typtype
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
      AND t.typtype IN ('e','d')
      AND pg_get_userbyid(t.typowner) = 'postgres'
  LOOP
    IF r.typtype = 'e' THEN
      EXECUTE format('ALTER TYPE %I.%I OWNER TO bifrost', r.schemaname, r.typname);
    ELSE
      EXECUTE format('ALTER DOMAIN %I.%I OWNER TO bifrost', r.schemaname, r.typname);
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
  left="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -c postgres -- \
    psql -U postgres -d "${db}" -tAc "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND pg_get_userbyid(c.relowner) = 'postgres') + (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public' AND t.typtype IN ('e','d') AND pg_get_userbyid(t.typowner) = 'postgres')")"
  echo "   ${db}: ${cnt} tables owned by bifrost; ${left} public objects still owned by postgres"
done

echo "Done."
