#!/usr/bin/env bash
# apply-step0.sh check|apply — the Owner puts the cluster half of step 0 of the
# Gitea-primary cut in place (CUT-gitea-primary-2026-10-17 §5 「第 1 步」 8;
# OWNER-STEPS-gitea-primary.md §2): 0a, the mirror-sync Task that knows a
# repository Gitea holds as its primary; 0e, the GitHub sync (Task, trigger
# template, a 15-minute reconcile CronJob, the github-sync trigger on the CI
# EventListener), its two alerts and its maintainer entry. While every
# repository is still a pull mirror none of it changes anything.
#
# What is applied comes from the reviewed commit (REVIEWED), not from the
# working tree: the manifests are exported from it into a temporary directory
# and rendered once into a single file, and the server dry run and the apply
# both read that file (review 250 A3: a working tree can change between the
# dry run and the apply, or hide a change from git diff). check: the dry run
# only. apply: the dry run, then the apply. Stops at the first error. Needs
# the Owner's admin kubeconfig; nothing here reads or prints a Secret.
set -euo pipefail
export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"
# a local refs/replace entry could stand in for a reviewed object (review 251 A1);
# inherited environment could point git at other objects or another repository
# (review 252 A2), and the objects themselves are checked against their names
# before anything is exported (git fsck below)
export GIT_NO_REPLACE_OBJECTS=1
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES \
  GIT_NAMESPACE GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT GIT_CEILING_DIRECTORIES
REVIEWED=1de78f6811f209f766094dd621efa8c00711efe1 # 0a and 0e as reviews 243 and 244 left them
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
git -C "${INFRA}" cat-file -e "${REVIEWED}^{commit}" 2> /dev/null || die "commit ${REVIEWED} is not in ${INFRA}; git fetch there first"
git -C "${INFRA}" fsck --strict --no-reflogs --no-dangling --no-progress "${REVIEWED}" > /dev/null ||
  die "git fsck found objects in ${INFRA} that do not match their names; nothing done"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
mkdir "${work}/tree"
git -C "${INFRA}" archive "${REVIEWED}" -- "${paths[@]}" > "${work}/tree.tar"
tar -x -f "${work}/tree.tar" -C "${work}/tree"
rendered="${work}/step0.yaml"
{
  cat "${work}/tree/k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
  printf '\n---\n'
  cat "${work}/tree/k8s/cicd/tekton/trigger-trade-ci.yaml"
  printf '\n---\n'
  kubectl kustomize "${work}/tree/k8s/cicd/github-sync"
  printf '\n---\n'
  cat "${work}/tree/k8s/monitoring/bifrost-alerting-rules.yaml"
  printf '\n---\n'
  kubectl kustomize "${work}/tree/k8s/monitoring/maintainer-reconcile"
} > "${rendered}"
chmod a-w "${rendered}"
echo "==> rendered ${REVIEWED:0:7}: $(grep -c '^kind:' "${rendered}") objects"

echo "==> dry run on the server"
kubectl apply --dry-run=server -f "${rendered}"
if [[ "$1" == check ]]; then
  echo "==> check passed; nothing applied. Run it again with apply."
  exit 0
fi
echo "==> apply"
kubectl apply -f "${rendered}"
echo "==> applied. Say 「第 0 步装好了」 in the thread; the coordinating thread checks the objects."
