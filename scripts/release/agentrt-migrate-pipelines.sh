#!/usr/bin/env bash
# TD-411 (Owner 2026-10-21: 「STG 的迁移由发布流水线先跑、PROD 照旧由我建 Job」): the
# Owner applies the deliver pipelines' agentrt migration steps to the cluster.
#
#   bash scripts/release/agentrt-migrate-pipelines.sh check   read only: the commit, who you
#                                                              are, a server dry-run, a diff
#   bash scripts/release/agentrt-migrate-pipelines.sh apply   the same checks, then apply
#
# What is applied is this checkout's commit, which must be on origin/main (pushed, and
# origin/main fetched or updated by the push; any commit of main's history passes): each file is
# taken from that commit into a snapshot, and the dry-run, the diff and the apply all read
# the snapshot. STG's files (the Role and RoleBinding in bifrost-platform-stg, the
# migration Task, the image promotion Task, the STG pipeline) go first. PROD's pipeline
# (the schema check and the promotion before its rollout) goes only once every PROD
# platform-api pod reports agentrt_schema_applied on its own /health, the Deployment
# converged on one image: before that its check would refuse every PROD release, the one
# that brings the field included. Until then apply says so and leaves PROD's pipeline as it is; run apply
# again after that release. A PROD platform rolled back to one without the field is
# refused by the check on every release: roll back only to a platform that has it.
# The pods asked are read again (by uid, image and container) before the first write and
# right before PROD's pipeline is applied; a rollout that starts after that last read is
# not seen, so no PROD release runs while you apply (the release window).
# Run it in your own terminal (your kubeconfig, not the agent's). It stops at its first
# error; nothing is written before every check passed; apply is safe to run again.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
STG_FILES=(
  k8s/cicd/tekton/rbac-deliver-migrate-stg.yaml
  k8s/cicd/tekton/task-agentrt-migrate-stg.yaml
  k8s/cicd/tekton/task-promote-platform-images.yaml
  k8s/cicd/tekton/pipeline-deliver-platform.yaml
)
PROD_FILE=k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml

# Every read of the cluster is bounded (review 503 B2): your kubeconfig,
# so the flag is safe here (unlike kubectl inside a pod).
RT=--request-timeout=20s
PNS=bifrost-platform-prod

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"
case "${step}" in
  check|apply) ;;
  *) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
cd "${root}"

# The commit, pinned once: on origin/main, holding every file.
sha="$(git rev-parse HEAD)"
git merge-base --is-ancestor "${sha}" refs/remotes/origin/main ||
  die "this checkout's commit ${sha:0:12} is not on origin/main: check out main as pushed"
snap="$(mktemp -d)"
trap 'rm -rf "${snap}"' EXIT
for f in "${STG_FILES[@]}" "${PROD_FILE}"; do
  git cat-file -e "${sha}:${f}" 2>/dev/null || die "${f} is not in commit ${sha:0:12} (is TD-411's pipeline change on main?)"
  mkdir -p "${snap}/$(dirname "${f}")"
  git show "${sha}:${f}" > "${snap}/${f}"
done
say "applying from commit ${sha:0:12} ($(git log -1 --format=%s "${sha}"))"

# Who you are, a first screen: the server dry-run below is the real check.
for want in "create tasks.tekton.dev -n cicd" "patch tasks.tekton.dev -n cicd" \
  "get pipelines.tekton.dev -n cicd" "patch pipelines.tekton.dev -n cicd" \
  "create roles.rbac.authorization.k8s.io -n bifrost-platform-stg" "patch roles.rbac.authorization.k8s.io -n bifrost-platform-stg" \
  "create rolebindings.rbac.authorization.k8s.io -n bifrost-platform-stg" "patch rolebindings.rbac.authorization.k8s.io -n bifrost-platform-stg" \
  "get deployments.apps -n ${PNS}" "list replicasets.apps -n ${PNS}" "list pods -n ${PNS}" \
  "get pods --subresource=proxy -n ${PNS}"; do
  # shellcheck disable=SC2086 # the words are kubectl's arguments
  [[ "$(kubectl auth can-i ${want} "${RT}" 2>/dev/null || true)" == "yes" ]] ||
    die "this kubeconfig cannot ${want}: run this in your own terminal, with your admin kubeconfig"
done
say "this identity passes the first screen (get, create, patch; PROD's platform-api readable)"

# PROD's pipeline waits until every running PROD platform-api says which migrations its
# database has (review 500 B2): the Deployment converged, every Pod of it (owned through its
# ReplicaSet) Ready on one image, and each Pod's own /health (through the API server's pod
# proxy) reporting the field.
prod_replicas() { # prints the pods' names, then what identifies them (review 503 B1); else "NO: why"
  local d r p
  d="$(kubectl get deployment platform-api -n "${PNS}" -o json "${RT}")" || { echo "NO: the Deployment cannot be read"; return; }
  r="$(kubectl get replicasets -n "${PNS}" -o json "${RT}")" || { echo "NO: its ReplicaSets cannot be read"; return; }
  p="$(kubectl get pods -n "${PNS}" -l app.kubernetes.io/name=platform-api -o json "${RT}")" || { echo "NO: its pods cannot be read"; return; }
  python3 - "$d" "$r" "$p" <<'PY'
import json, sys
d, r, p = (json.loads(x) for x in sys.argv[1:4])
want, st = d["spec"].get("replicas", 1), d.get("status", {})
if st.get("observedGeneration") != d["metadata"]["generation"] or any(
        st.get(k, 0) != want for k in ("updatedReplicas", "readyReplicas", "availableReplicas")) or st.get("replicas", 0) != want:
    print("NO: the Deployment has not converged on %d replicas: %s" % (want, {k: st.get(k) for k in sorted(st) if "eplicas" in k}))
    sys.exit()
def owned_by(x, uids):
    return any(o.get("controller") and o.get("uid") in uids for o in x["metadata"].get("ownerReferences", []))
sets = {x["metadata"]["uid"] for x in r["items"] if owned_by(x, {d["metadata"]["uid"]})}
pods = [x for x in p["items"] if not x["metadata"].get("deletionTimestamp")]
foreign = sorted(x["metadata"]["name"] for x in pods if not owned_by(x, sets))
if foreign:
    print("NO: pods with its label that the Deployment does not own: %s" % " ".join(foreign))
    sys.exit()
ready = [x for x in pods if x.get("status", {}).get("phase") == "Running" and any(
    c.get("type") == "Ready" and c.get("status") == "True" for c in x["status"].get("conditions", []))]
images = {cs.get("imageID") for x in ready for cs in x["status"].get("containerStatuses", [])}
if len(pods) != want or len(ready) != want or len(images) != 1:
    print("NO: %d pods, %d Ready, %d images (want %d, %d, 1)" % (len(pods), len(ready), len(images), want, want))
    sys.exit()
print(" ".join(sorted(x["metadata"]["name"] for x in ready)))
print(json.dumps({"deployment": [d["metadata"]["uid"], d["metadata"]["generation"]], "pods": sorted(
    [x["metadata"]["name"], x["metadata"].get("uid"), sorted(
        [c.get("name"), c.get("imageID"), c.get("containerID"), c.get("restartCount")]
        for c in x["status"].get("containerStatuses", []))] for x in ready)}, sort_keys=True))
PY
}
prod=yes
before="$(prod_replicas)"
if [[ "${before}" == NO:* ]]; then
  prod=no
  say "PROD's platform-api is not ready for the PROD pipeline (${before#NO: }): the PROD pipeline waits"
else
  pods_before="$(head -1 <<<"${before}")"
  for pod in ${pods_before}; do
    if ! body="$(kubectl get --raw "/api/v1/namespaces/${PNS}/pods/${pod}:8780/proxy/health" "${RT}")"; then
      prod=no
      say "PROD's platform-api pod ${pod} could not be asked for its /health (see above): the PROD pipeline waits"
      break
    fi
    if ! printf '%s' "${body}" | python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(sys.stdin).get("agentrt_schema_applied"), list) else 1)'; then
      prod=no
      say "PROD's platform-api pod ${pod} does not report agentrt_schema_applied: the PROD pipeline waits"
      break
    fi
  done
fi
files=("${STG_FILES[@]}")
[[ "${prod}" == yes ]] && files+=("${PROD_FILE}") && say "every PROD platform-api pod (${pods_before}) reports agentrt_schema_applied: the PROD pipeline goes too"

for f in "${files[@]}"; do
  kubectl apply --dry-run=server -f "${snap}/${f}" >/dev/null || die "the server refuses ${f}"
  say "server dry-run ok: ${f}"
done
for f in "${files[@]}"; do
  say "diff ${f}:"
  kubectl diff -f "${snap}/${f}" || [[ $? -eq 1 ]] || die "kubectl diff failed on ${f}"
done

if [[ "${step}" == check ]]; then
  say "check done; nothing written"
  exit 0
fi

# The PROD containers asked are still the ones running, the same pods, images and
# containers (reviews 500 B2, 503 B1): before the first write, and again right before
# PROD's pipeline.
if [[ "${prod}" == yes && "$(prod_replicas)" != "${before}" ]]; then
  die "PROD's platform-api pods changed during the checks; nothing is written; run apply again"
fi
done_files=()
for f in "${files[@]}"; do
  if [[ "${f}" == "${PROD_FILE}" && "$(prod_replicas)" != "${before}" ]]; then
    die "PROD's platform-api changed since its pods were asked, so PROD's pipeline is not applied; applied: ${done_files[*]:-none}. Run apply again at commit ${sha:0:12}"
  fi
  if ! kubectl apply -f "${snap}/${f}"; then
    die "applying ${f} failed (it may be partly applied); applied before it: ${done_files[*]:-none}. Run apply again at commit ${sha:0:12}: it is safe"
  fi
  done_files+=("${f}")
done
kubectl get role,rolebinding tekton-deliver-migrate -n bifrost-platform-stg "${RT}"
kubectl get task bifrost-agentrt-migrate-stg bifrost-promote-platform-images -n cicd "${RT}"
kubectl get pipeline bifrost-deliver-platform bifrost-deliver-platform-prod -n cicd "${RT}"
if [[ "${prod}" == yes ]]; then
  say "done (${sha:0:12}): STG runs its migrations before it rolls out; PROD checks its database before it rolls out"
else
  say "done for STG (${sha:0:12}). Run apply again once PROD's platform-api reports agentrt_schema_applied (a PROD release of platform with TD-411's health field)"
fi
