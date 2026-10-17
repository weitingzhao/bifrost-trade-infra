#!/usr/bin/env bash
# apply-step0.sh check|apply — the Owner puts the cluster half of step 0 of the
# Gitea-primary cut in place (CUT-gitea-primary-2026-10-17 §5 「第 1 步」 8;
# OWNER-STEPS-gitea-primary.md §2): 0a, the mirror-sync Task that knows a
# repository Gitea holds as its primary; 0e, the GitHub sync (Task, trigger
# template, a 15-minute reconcile CronJob, the github-sync trigger on the CI
# EventListener), its two alerts and its maintainer entry. While every
# repository is still a pull mirror none of it changes anything.
#
# check: the files must be the reviewed ones (REVIEWED below), then every
# object is dry-run on the server. apply: the same checks, then the applies,
# in the same order. Stops at the first error. Needs the Owner's admin
# kubeconfig; nothing here reads or prints a Secret.
set -euo pipefail
export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"
REVIEWED=1de78f6 # 0a and 0e as reviews 243 and 244 left them
INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
paths=(
  k8s/cicd/tekton/task-gitea-mirror-sync.yaml
  k8s/cicd/tekton/trigger-trade-ci.yaml
  k8s/cicd/github-sync
  k8s/monitoring/bifrost-alerting-rules.yaml
  k8s/monitoring/maintainer-reconcile
)

die() {
  echo "apply-step0.sh: $*" >&2
  exit 1
}

[[ "${1:-}" == check || "${1:-}" == apply ]] || die "usage: apply-step0.sh check|apply"
[[ -f "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"
cd "${INFRA}"
git rev-parse --verify --quiet "${REVIEWED}^{commit}" > /dev/null || die "commit ${REVIEWED} is not in ${INFRA}; git fetch there first"
if ! git diff --quiet "${REVIEWED}" -- "${paths[@]}" || [[ -n "$(git status --porcelain -- "${paths[@]}")" ]]; then
  git diff --stat "${REVIEWED}" -- "${paths[@]}" >&2
  git status --short -- "${paths[@]}" >&2
  die "these files are not the reviewed ones (${REVIEWED}); nothing done"
fi

# each: kubectl apply <flags> on one file (-f) or kustomization (-k)
each() {
  kubectl apply "$@" -f k8s/cicd/tekton/task-gitea-mirror-sync.yaml
  kubectl apply "$@" -f k8s/cicd/tekton/trigger-trade-ci.yaml
  kubectl apply "$@" -k k8s/cicd/github-sync
  kubectl apply "$@" -f k8s/monitoring/bifrost-alerting-rules.yaml
  kubectl apply "$@" -k k8s/monitoring/maintainer-reconcile
}

echo "==> dry run on the server"
each --dry-run=server
if [[ "$1" == check ]]; then
  echo "==> check passed; nothing applied. Run it again with apply."
  exit 0
fi
echo "==> apply"
each
echo "==> applied. Say 「第 0 步装好了」 in the thread; the coordinating thread checks the objects."
