#!/usr/bin/env bash
# Which Kubernetes API versions in use are deprecated or removed in a target
# release. Read-only: pluto reads the manifests in this repository and asks the
# API server which versions its objects are stored at. It does not read Helm
# releases here (those live in Secrets).
#
#   PLUTO=~/agent-work/compute-s1/tools/pluto/pluto scripts/k3s/pluto-report.sh v1.36.0
#
# Run it before a k3s upgrade and when Renovate proposes one, with the target
# version. Exit 0: nothing found. Exit 1: something is deprecated or removed
# (the lines are printed), or pluto could not run.
set -euo pipefail

target="${1:?usage: pluto-report.sh <target k8s version, e.g. v1.36.0>}"
pluto="${PLUTO:-pluto}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"

command -v "$pluto" >/dev/null || { echo "pluto-report: no pluto at ${pluto} (set PLUTO)" >&2; exit 1; }

# A scan that cannot find a removed API proves nothing; show that it can.
control="$(printf 'apiVersion: policy/v1beta1\nkind: PodSecurityPolicy\nmetadata:\n  name: control\n' \
  | "$pluto" detect - -t "k8s=${target}" -o wide 2>&1 || true)"
grep -q PodSecurityPolicy <<<"$control" || { echo "pluto-report: the control (a removed PodSecurityPolicy) was not detected" >&2; exit 1; }

rc=0
echo "== manifests under k8s/ against ${target}"
"$pluto" detect-files -d "${root}/k8s" -t "k8s=${target}" -o wide || rc=1
echo "== API versions the cluster stores objects at, against ${target}"
"$pluto" detect-api-resources -t "k8s=${target}" -o wide || rc=1
exit "$rc"
