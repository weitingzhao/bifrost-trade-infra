#!/bin/bash
# Who still uses repository $1 (read-only): the reading behind law
# "structure elasticity" s5 (approval #719; R0D, Foundation 2026-11-23).
# Code: origin/main of every workspace repo except itself. Running surface:
# object names and ConfigMap data in the cluster. Secrets: the agent identity
# cannot list them, so that line stays empty (unmeasured, not zero).
# A repository may retire (tier: retired in k8s/cicd/repositories.yaml) when
# nothing depends on the repository itself: no clone, build, import, or
# governance special case naming it. Live resources that only reuse the old
# name belong to their domain and do not block it.
# Usage: scripts/repos/repo_users.sh <repo> [<short name used at runtime>]
set -u
name="$1"; short="${2:-$1}"   # short: the bare word the runtime uses (e.g. analytics)
ws=$(cd "$(dirname "$0")/../../.." && pwd -P)   # the workspace: infra and its sibling checkouts
echo "== code (origin/main, files naming '$name') =="
for r in "$ws"/bifrost-*/; do
  r=${r%/}; b=$(basename "$r"); [ "$b" = "$name" ] && continue
  git -C "$r" fetch -q origin main 2>/dev/null
  n=$(git -C "$r" grep -l -I -e "$name" origin/main -- 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" != 0 ] && { echo "$b: $n files"; git -C "$r" grep -l -I -e "$name" origin/main -- 2>/dev/null | sed 's/^origin\/main:/   /' | head -15; }
done
echo "== running surface (object names containing '$short') =="
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
for k in configmaps persistentvolumeclaims secrets deployments cronjobs services pipelines.tekton.dev; do
  kubectl get "$k" -A --no-headers -o custom-columns=NS:.metadata.namespace,N:.metadata.name 2>/dev/null | grep -i -- "$short" | sed "s/^/$k  /"
done
echo "== ConfigMap data naming '$name' =="
kubectl get configmaps -A -o json 2>/dev/null | python3 -c '
import json,sys
n=sys.argv[1]
for i in json.load(sys.stdin)["items"]:
  d=json.dumps(i.get("data") or {})
  if n in d: print(i["metadata"]["namespace"], i["metadata"]["name"], d.count(n))' "$name"
