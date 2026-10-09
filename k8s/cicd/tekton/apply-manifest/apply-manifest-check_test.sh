#!/bin/sh
# Fixtures for apply-manifest-check.sh. Uses client-side kubectl and jq.
# Does not apply anything and does not read a kubeconfig for the checks:
# KUBECTL is a stub that reports NotFound, except one tracked name.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
POLICY="${ROOT}/actuation-policy.yaml"
CHECK="${ROOT}/apply-manifest-check.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "${TMP}/kubectl" <<'EOF'
#!/bin/sh
if [ "$1" = "get" ] && [ "$2" = "namespace" ]; then
  # TD-275: one Namespace exists with labels team=data and part-of=plugin.
  if [ "$3" = "existing-ns" ]; then
    printf '%s' '{"kubernetes.io/metadata.name":"existing-ns","team":"data","part-of":"plugin"}'
    exit 0
  fi
  echo "Error from server (NotFound)" >&2
  exit 1
fi
if [ "$1" = "get" ]; then
  for arg in "$@"; do
    if [ "$arg" = "tracked-cm" ]; then
      printf '%s' 'applications.argoproj.io/bifrost-research:research'
      exit 0
    fi
  done
  echo "Error from server (NotFound)" >&2
  exit 1
fi
echo "stub kubectl refuses $1" >&2
exit 1
EOF
chmod +x "${TMP}/kubectl" "$CHECK"
export KUBECTL="${TMP}/kubectl"

normalize() {
  kubectl create --dry-run=client -o json -f "$1" | jq -s '{apiVersion:"v1",kind:"List",items:.}' > "$2"
}

expect_fail() {
  name="$1"
  src="$2"
  normalize "$src" "${TMP}/norm.json"
  if sh "$CHECK" "$POLICY" "${TMP}/norm.json" "${TMP}/objects.json" >"${TMP}/out" 2>"${TMP}/err"; then
    echo "FAIL ${name} was accepted" >&2
    cat "${TMP}/err" >&2
    exit 1
  fi
}

cat > "${TMP}/ok.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: w33br-ok
  namespace: bifrost-dev
data:
  k: v
EOF
normalize "${TMP}/ok.yaml" "${TMP}/norm.json"
tier=$(sh "$CHECK" "$POLICY" "${TMP}/norm.json" "${TMP}/objects.json")
if [ "$tier" != "B" ]; then
  echo "FAIL normal configmap tier=${tier}" >&2
  exit 1
fi

cat > "${TMP}/flow.yaml" <<'EOF'
{apiVersion: v1, kind: ConfigMap, metadata: {name: flow-cm}}
EOF
expect_fail "flow style without namespace" "${TMP}/flow.yaml"

cat > "${TMP}/json.yaml" <<'EOF'
{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"json-cm"}}
EOF
expect_fail "json without namespace" "${TMP}/json.yaml"

cat > "${TMP}/nonamespace.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-cm
EOF
expect_fail "missing namespace" "${TMP}/nonamespace.yaml"

cat > "${TMP}/hidden.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: cover
  namespace: bifrost-dev
data:
  k: v
---
{apiVersion: apps/v1, kind: Deployment, metadata: {name: daemon, namespace: bifrost-stg}, spec: {replicas: 0, selector: {matchLabels: {app: daemon}}, template: {metadata: {labels: {app: daemon}}, spec: {containers: [{name: c, image: alpine}]}}}}
EOF
expect_fail "flow-style daemon hidden beside a configmap" "${TMP}/hidden.yaml"

cat > "${TMP}/list.yaml" <<'EOF'
apiVersion: v1
kind: List
items:
  - apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: daemon
      namespace: bifrost-stg
    spec:
      replicas: 0
      selector:
        matchLabels:
          app: daemon
      template:
        metadata:
          labels:
            app: daemon
        spec:
          containers:
            - name: c
              image: alpine
EOF
expect_fail "list hiding a daemon deployment" "${TMP}/list.yaml"

cat > "${TMP}/tracked.yaml" <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: tracked-cm
  namespace: research
data:
  k: v
EOF
expect_fail "live object tracked by Argo" "${TMP}/tracked.yaml"

# TD-275: an existing Namespace with the same labels is dropped, the rest applies.
cat > "${TMP}/ns-ok.yaml" <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: existing-ns
  labels:
    team: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: md-pdb
  namespace: plugin-market-data
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: md
YAML
normalize "${TMP}/ns-ok.yaml" "${TMP}/norm.json"
tier=$(sh "$CHECK" "$POLICY" "${TMP}/norm.json" "${TMP}/objects.json" 2>"${TMP}/err") || {
  echo "FAIL existing namespace + PDB was refused" >&2
  cat "${TMP}/err" >&2
  exit 1
}
if [ "$tier" != "C" ]; then
  echo "FAIL existing namespace + PDB tier=${tier}" >&2
  cat "${TMP}/err" >&2
  exit 1
fi
if jq -e '[.. | objects | select(.kind == "Namespace")] | length > 0' "${TMP}/norm.json" >/dev/null; then
  echo "FAIL the existing Namespace was left in the file the pipeline applies" >&2
  exit 1
fi
if ! jq -e 'length == 1 and .[0].kind == "PodDisruptionBudget"' "${TMP}/objects.json" >/dev/null; then
  echo "FAIL objects.json should list only the PDB" >&2
  exit 1
fi

cat > "${TMP}/ns-missing.yaml" <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: missing-ns
YAML
expect_fail "namespace that does not exist" "${TMP}/ns-missing.yaml"

cat > "${TMP}/ns-differs.yaml" <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: existing-ns
  labels:
    team: research
YAML
expect_fail "existing namespace with different labels" "${TMP}/ns-differs.yaml"

cat > "${TMP}/clusterrole.yaml" <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: sneaky
rules: []
YAML
expect_fail "cluster-scoped ClusterRole" "${TMP}/clusterrole.yaml"
if ! grep -q "cluster-scoped objects are refused" "${TMP}/err"; then
  echo "FAIL a cluster-scoped object must be reported as such, not as a missing kind or name" >&2
  cat "${TMP}/err" >&2
  exit 1
fi

script=$(awk '
  /^            script: \|/ {p=1; next}
  p && /^        volumes:/ {exit}
  p {print}
' "${ROOT}/pipeline.yaml")
if printf '%s\n' "$script" | grep -q '$(params\.'; then
  echo "FAIL pipeline script still interpolates params" >&2
  exit 1
fi

echo "ok: normalized manifests reject flow, json, missing namespace, hidden daemon, List, Argo tracking, missing or changed Namespace, and ClusterRole; drop an existing Namespace"
