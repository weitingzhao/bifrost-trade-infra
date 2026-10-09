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

script=$(awk '
  /^            script: \|/ {p=1; next}
  p && /^        volumes:/ {exit}
  p {print}
' "${ROOT}/pipeline.yaml")
if printf '%s\n' "$script" | grep -q '$(params\.'; then
  echo "FAIL pipeline script still interpolates params" >&2
  exit 1
fi

echo "ok: normalized manifests reject flow, json, missing namespace, hidden daemon, List, and Argo tracking"
