#!/usr/bin/env bash
# W-31 3.4 ①② (Owner 2026-10-21 「D3 A」): the Owner applies the release speed-up to cicd.
#
#   bash scripts/release/release-speedup-apply.sh check   read only: the commit, who you are,
#                                                          the release window, a server
#                                                          dry-run and a diff of every file
#   bash scripts/release/release-speedup-apply.sh apply   the same checks, then apply
#
# What is applied is this checkout's commit, which must be on origin/main: each file is
# taken from that commit into a snapshot, and the dry-run, the diff and the apply all
# read the snapshot. In this order: the admission policies (a delivery may pin its own
# platform application by digest), the pin-and-sync Task and the rollout check Task, the
# STG and PROD platform deliver pipelines (PROD builds nothing and deploys the digests
# STG verified; both pin their Argo application to digests), then the CI triggers (CI on
# every branch push). No Argo application is written here: a delivery pins its own; the
# pin is only tried as tekton-deliver with --dry-run=server, which stores nothing.
# Nothing is applied while a release window is open (a delivery may be running).
# Run it in your own terminal (your kubeconfig, not the agent's). It stops at its first
# error; nothing is written before every check passed; apply is safe to run again.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
FILES=(
  k8s/platform-rbac/40-admission.yaml
  k8s/cicd/tekton/task-argocd-pin-sync-platform.yaml
  k8s/cicd/tekton/task-rollout-verify-platform.yaml
  k8s/cicd/tekton/pipeline-deliver-platform.yaml
  k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
  k8s/cicd/tekton/trigger-trade-ci.yaml
)
WINDOW="${SPEEDUP_WINDOW:-${here}/release.sh}"
RT=--request-timeout=20s

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"
case "${step}" in
  check|apply) ;;
  *) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
cd "${root}"

# The commit, pinned once: on origin/main, holding every file.
sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor "${sha}" refs/remotes/origin/main ||
  die "this checkout's commit ${sha:0:12} is not on origin/main: check out main as pushed"
snap="$(mktemp -d)"
trap 'rm -rf "${snap}"' EXIT
for f in "${FILES[@]}"; do
  git cat-file -e "${sha}:${f}" 2>/dev/null || die "${f} is not in commit ${sha:0:12} (is the release speed-up on main?)"
  mkdir -p "${snap}/$(dirname "${f}")"
  git show "${sha}:${f}" > "${snap}/${f}"
done
say "applying from commit ${sha:0:12} ($(git log -1 --format=%s "${sha}"))"

# Who you are, a first screen: the server dry-run below is the real check.
for want in "patch validatingadmissionpolicies.admissionregistration.k8s.io" \
  "patch validatingadmissionpolicybindings.admissionregistration.k8s.io" \
  "impersonate serviceaccounts/tekton-deliver -n cicd" \
  "create tasks.tekton.dev -n cicd" "patch tasks.tekton.dev -n cicd" \
  "get pipelines.tekton.dev -n cicd" "patch pipelines.tekton.dev -n cicd" \
  "patch eventlisteners.triggers.tekton.dev -n cicd" "patch triggertemplates.triggers.tekton.dev -n cicd" \
  "patch triggerbindings.triggers.tekton.dev -n cicd"; do
  # shellcheck disable=SC2086 # the words are kubectl's arguments
  [[ "$(kubectl auth can-i ${want} "${RT}" 2>/dev/null || true)" == "yes" ]] ||
    die "this kubeconfig cannot ${want}: run this in your own terminal, with your admin kubeconfig"
done
say "this identity passes the first screen (admission policies, tasks, pipelines, triggers in cicd)"

# A delivery's pin, as its gitops-sync sends it, tried as tekton-deliver and not stored
# (--dry-run=server): both platform applications must accept it, and a pin by tag must be
# refused by the admission policy (it allows a digest pin and nothing else). The first STG
# run's pin was denied by the policy before it had this exception (2026-10-22).
DELIVER=system:serviceaccount:cicd:tekton-deliver
ZERO="sha256:0000000000000000000000000000000000000000000000000000000000000000"
pin_patch() {  # $1, $2: the api and console images the pin names
  printf '{"spec":{"source":{"kustomize":{"images":["%s","%s"]}}},"operation":{"initiatedBy":{"username":"tekton-deliver-platform:speedup-apply-check"},"sync":{"revision":"HEAD"}}}' \
    "registry.cicd.svc.cluster.local:5000/bifrost-platform-api=$1" \
    "registry.cicd.svc.cluster.local:5000/bifrost-platform-console=$2"
}
pin_dry_run() {  # $1: the application; $2: the patch. Prints the server's answer when refused.
  kubectl -n cicd patch "applications.argoproj.io/$1" --type merge -p "$2" --dry-run=server \
    --as "${DELIVER}" "${RT}" 2>&1 >/dev/null
}
pins_pass() {
  local app out bad=0
  for app in bifrost-platform-stg bifrost-platform-prod; do
    if out="$(pin_dry_run "${app}" "$(pin_patch "192.168.10.73:30500/bifrost-platform-api@${ZERO}" \
      "192.168.10.73:30500/bifrost-platform-console@${ZERO}")")"; then
      say "a delivery's digest pin of ${app} passes admission (server dry-run, not stored)"
    else
      bad=1
      say "a delivery's digest pin of ${app} is refused: ${out%%$'\n'*}"
    fi
  done
  if out="$(pin_dry_run bifrost-platform-stg "$(pin_patch "192.168.10.73:30500/bifrost-platform-api:stg" \
    "192.168.10.73:30500/bifrost-platform-console@${ZERO}")")"; then
    bad=1
    say "a pin by tag passes admission: the policy is wider than a digest pin"
  elif [[ "${out}" != *"ValidatingAdmissionPolicy 'bifrost-platform-application'"* ]]; then
    bad=1
    say "a pin by tag is refused, but not by the admission policy: ${out%%$'\n'*}"
  else
    say "a pin by tag is refused by the admission policy"
  fi
  return "${bad}"
}

window_closed() {
  local rc=0
  "${WINDOW}" window >/dev/null 2>&1 || rc=$?
  case "${rc}" in
    0) return 0 ;;
    1) die "a release window is open (release.sh window): a delivery may be running; apply once it is closed" ;;
    *) die "cannot read the release window (exit ${rc})" ;;
  esac
}
window_closed

for f in "${FILES[@]}"; do
  kubectl apply --dry-run=server -f "${snap}/${f}" "${RT}" >/dev/null || die "the server refuses ${f}"
  say "server dry-run ok: ${f}"
done
for f in "${FILES[@]}"; do
  say "diff ${f}:"
  kubectl diff -f "${snap}/${f}" "${RT}" || [[ $? -eq 1 ]] || die "kubectl diff failed on ${f}"
done

if [[ "${step}" == check ]]; then
  pins_pass || say "(until 40-admission.yaml is applied the live policy refuses a delivery's pin: apply fixes that)"
  say "check done; nothing written"
  exit 0
fi

window_closed
done_files=()
for f in "${FILES[@]}"; do
  if ! kubectl apply -f "${snap}/${f}"; then
    die "applying ${f} failed (it may be partly applied); applied before it: ${done_files[*]:-none}. Run apply again at commit ${sha:0:12}: it is safe"
  fi
  done_files+=("${f}")
done
kubectl get task bifrost-argocd-pin-sync-platform bifrost-rollout-verify-platform -n cicd "${RT}"
kubectl get pipeline bifrost-deliver-platform bifrost-deliver-platform-prod -n cicd "${RT}"
kubectl get eventlistener bifrost-ci -n cicd "${RT}"
pins_pass || die "applied, but the API server does not answer a delivery's pin as it should: start no platform delivery; tell the agent"
say "done (${sha:0:12}): the next STG platform delivery pins STG to its digests; the next PROD one builds nothing; CI runs on branch pushes"
