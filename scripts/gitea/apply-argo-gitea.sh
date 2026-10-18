#!/usr/bin/env bash
# apply-argo-gitea.sh check|apply|back — batch C step 2 (CUT-gitea-primary-2026-10-17
# §4 「第 C 批」): Argo CD reads bifrost-trade-infra and bifrost-research from Gitea,
# the primary, instead of GitHub. The Owner runs it with the admin kubeconfig.
#
#   check  read only: the preconditions and what apply would change
#   apply  check, then the AppProject (k8s/platform-rbac/42-appproject-bifrost.yaml)
#          and the five Applications (k8s/cicd/applications/), read back, and wait
#          until Argo has compared each one against Gitea main
#   back   the five Applications with their GitHub addresses again (the move back;
#          the AppProject keeps both addresses for a week, so it stays)
#
# Preconditions: Secret cicd/repo-creds-gitea-bifrost (put-argocd-reader-token.sh)
# with label repo-creds; for both repositories Gitea main and GitHub main are the
# same commit, so the change of source changes nothing Argo would deploy.
#
# What is applied comes from the infra checkout's commit FROM (default
# origin/main, printed), as raw blobs. Before anything is applied, each object is
# dry-run on the server and compared with the live one as a whole object, leaving
# out only status and what the server keeps (managedFields, resourceVersion,
# generation, uid, creationTimestamp) and the last-applied annotation (review 261
# A2: a client-side apply may also drop annotations or finalizers the file lacks):
# the AppProject may only gain the two Gitea addresses in sourceRepos, each
# Application may only change spec.source.repoURL from its GitHub address to its
# Gitea address (back: the reverse). Anything else stops it before the first
# write. After apply, every Application must read back with the new address and,
# within WAIT_S, show no ComparisonError and a sync revision equal to that
# side's main. back needs only GitHub: it is the way out when Gitea is down
# (review 261 B6), and it says which commit GitHub main is.
set -euo pipefail
set +x

mode="${1:-}"
[[ "${mode}" == check || "${mode}" == apply || "${mode}" == back ]] || { echo "usage: apply-argo-gitea.sh check|apply|back" >&2; exit 2; }
INFRA="${ARGO_INFRA:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
export KUBECONFIG="${ARGO_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
NS=cicd
GITEA_IN="${GITEA_IN_CLUSTER:-http://gitea.cicd.svc.cluster.local:3000/bifrost}"
GITEA_PUB="${GITEA_PUBLIC_BASE:-http://192.168.10.73:30300/bifrost}"
GITHUB="${GITHUB_PUBLIC_BASE:-https://github.com/weitingzhao}"
FROM="${FROM:-origin/main}"
WAIT_S="${WAIT_S:-360}"
SECRET=repo-creds-gitea-bifrost
APPS="bifrost-platform-prod:bifrost-trade-infra bifrost-platform-stg:bifrost-trade-infra bifrost-prod:bifrost-trade-infra bifrost-stg:bifrost-trade-infra bifrost-research:bifrost-research"
REPOS="bifrost-trade-infra bifrost-research"

die() { echo "ERROR: $*" >&2; exit 1; }
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

[[ -r "${KUBECONFIG}" ]] || die "no admin kubeconfig at ${KUBECONFIG}"
kubectl -n "${NS}" get serviceaccount default -o name > /dev/null || die "cannot reach the cluster with ${KUBECONFIG}"

# The files, from one commit, as raw blobs (no checkout filters).
sha="$(git -C "${INFRA}" rev-parse --verify --quiet "${FROM}^{commit}")" || die "no commit ${FROM} in ${INFRA}"
echo "files from ${FROM} = ${sha}"
blob() { git -C "${INFRA}" cat-file blob "${sha}:$1" > "$2" || die "no $1 in ${sha}"; }
blob k8s/platform-rbac/42-appproject-bifrost.yaml "${work}/project.yaml"
for pair in ${APPS}; do
  app="${pair%%:*}"
  blob "k8s/cicd/applications/${app}.yaml" "${work}/${app}.yaml"
done
if [[ "${mode}" == back ]]; then
  for pair in ${APPS}; do
    app="${pair%%:*}"; repo="${pair#*:}"
    python3 - "${work}/${app}.yaml" "${GITEA_IN}/${repo}.git" "${GITHUB}/${repo}.git" << 'PY'
import sys
p, gitea, github = sys.argv[1:4]
s = open(p).read()
line = "repoURL: " + gitea
if s.count(line) != 1:
    sys.exit("%s: expected one %r" % (p, line))
open(p, "w").write(s.replace(line, "repoURL: " + github))
PY
  done
fi

# Preconditions.
if [[ "${mode}" != back ]]; then
  label="$(kubectl -n "${NS}" get secret "${SECRET}" -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/secret-type}' 2> /dev/null || true)"
  [[ "${label}" == repo-creds ]] || die "Secret ${NS}/${SECRET} with label repo-creds is not there (put-argocd-reader-token.sh first)"
  echo "ok    Secret ${NS}/${SECRET} (repo-creds)"
fi
declare_main() { # REPO — prints Gitea main; dies unless GitHub main is the same commit
  local repo="$1" g h
  g="$(GIT_TERMINAL_PROMPT=0 git ls-remote "${GITEA_PUB}/${repo}.git" refs/heads/main | awk '{print $1}')"
  h="$(GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 git ls-remote "${GITHUB}/${repo}.git" refs/heads/main | awk '{print $1}')"
  [[ "${g}" =~ ^[0-9a-f]{40}$ ]] || die "cannot read Gitea main of ${repo}"
  [[ "${g}" == "${h}" ]] || die "${repo}: Gitea main ${g}, GitHub main ${h:-unreadable}; wait for bifrost-github-sync, then run this again"
  printf '%s\n' "${g}"
}
for repo in ${REPOS}; do
  if [[ "${mode}" == back ]]; then
    main="$(GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 git ls-remote "${GITHUB}/${repo}.git" refs/heads/main | awk '{print $1}')"
    [[ "${main}" =~ ^[0-9a-f]{40}$ ]] || die "cannot read GitHub main of ${repo}"
    echo "ok    ${repo}: going back to GitHub main ${main}"
  else
    main="$(declare_main "${repo}")"
    echo "ok    ${repo}: Gitea main = GitHub main = ${main:0:12}"
  fi
  printf '%s\n' "${main}" > "${work}/main-${repo}"
done

# Dry-run on the server and compare with what is live.
compare() { # KIND NAME FILE WANT_FROM WANT_TO
  kubectl -n "${NS}" get "$1" "$2" -o json > "${work}/live.json" || die "cannot read $1 $2"
  kubectl -n "${NS}" apply --dry-run=server -o json -f "$3" > "${work}/new.json" || die "server dry-run of $3 failed"
  python3 - "$1" "${work}/live.json" "${work}/new.json" "$4" "$5" << 'PY'
import json, sys
kind, live_p, new_p, want_from, want_to = sys.argv[1:6]
live, new = json.load(open(live_p)), json.load(open(new_p))
problems = []
def bare(obj):
    obj = json.loads(json.dumps(obj))
    obj.pop("status", None)
    meta = obj.get("metadata") or {}
    for k in ("managedFields", "resourceVersion", "generation", "uid", "creationTimestamp"):
        meta.pop(k, None)
    ann = meta.get("annotations") or {}
    ann.pop("kubectl.kubernetes.io/last-applied-configuration", None)
    meta["annotations"] = ann
    return obj
lo, no = bare(live), bare(new)
if lo["metadata"] != no["metadata"]:
    keys = sorted(k for k in set(lo["metadata"]) | set(no["metadata"]) if lo["metadata"].get(k) != no["metadata"].get(k))
    problems.append("metadata changes: %s" % ", ".join(keys))
rest = sorted(k for k in set(lo) | set(no) if k not in ("metadata", "spec") and lo.get(k) != no.get(k))
if rest:
    problems.append("changes outside spec: %s" % ", ".join(rest))
ls, ns = lo.get("spec") or {}, no.get("spec") or {}
if kind == "appproject":
    gained = sorted(set(ns.get("sourceRepos") or []) - set(ls.get("sourceRepos") or []))
    lost = sorted(set(ls.get("sourceRepos") or []) - set(ns.get("sourceRepos") or []))
    allowed = set(want_to.split())
    if lost:
        problems.append("sourceRepos would lose %s" % ", ".join(lost))
    if set(gained) - allowed:
        problems.append("sourceRepos would gain %s" % ", ".join(sorted(set(gained) - allowed)))
    ns["sourceRepos"] = ls.get("sourceRepos")
    change = "sourceRepos + %s" % (", ".join(gained) or "nothing")
else:
    was, now = (ls.get("source") or {}).get("repoURL"), (ns.get("source") or {}).get("repoURL")
    if now == was:
        change = "repoURL stays %s" % now
    elif was == want_from and now == want_to:
        change = "repoURL %s → %s" % (was, now)
    else:
        problems.append("repoURL %s → %s, expected %s → %s" % (was, now, want_from, want_to))
        change = ""
    if "source" in ns:
        ns["source"]["repoURL"] = was
if ns != ls:
    keys = sorted(k for k in set(ns) | set(ls) if ns.get(k) != ls.get(k))
    problems.append("spec changes beyond that: %s" % ", ".join(keys))
if problems:
    print("FAIL  %s %s: %s" % (kind, live["metadata"]["name"], "; ".join(problems)))
    sys.exit(1)
print("ok    %s %s: %s" % (kind, live["metadata"]["name"], change))
PY
}
bad=0
if [[ "${mode}" != back ]]; then
  compare appproject bifrost "${work}/project.yaml" "" "${GITEA_IN}/bifrost-trade-infra.git ${GITEA_IN}/bifrost-research.git" || bad=1
fi
for pair in ${APPS}; do
  app="${pair%%:*}"; repo="${pair#*:}"
  if [[ "${mode}" == back ]]; then
    compare application "${app}" "${work}/${app}.yaml" "${GITEA_IN}/${repo}.git" "${GITHUB}/${repo}.git" || bad=1
  else
    compare application "${app}" "${work}/${app}.yaml" "${GITHUB}/${repo}.git" "${GITEA_IN}/${repo}.git" || bad=1
  fi
done
[[ "${bad}" == 0 ]] || die "the dry-run shows more than the planned change; nothing applied"
if [[ "${mode}" == check ]]; then
  echo "== check: all as expected; nothing applied"
  exit 0
fi

# Apply: the project first (it must allow the new source before an Application uses it).
if [[ "${mode}" == apply ]]; then
  kubectl -n "${NS}" apply -f "${work}/project.yaml" > /dev/null
  echo "applied AppProject bifrost"
fi
for pair in ${APPS}; do
  app="${pair%%:*}"
  kubectl -n "${NS}" apply -f "${work}/${app}.yaml" > /dev/null
  kubectl -n "${NS}" annotate application "${app}" argocd.argoproj.io/refresh=normal --overwrite > /dev/null
  echo "applied Application ${app}"
done

# Read back and wait for Argo to compare against the new source.
deadline=$(( $(date +%s) + WAIT_S ))
for pair in ${APPS}; do
  app="${pair%%:*}"; repo="${pair#*:}"
  if [[ "${mode}" == back ]]; then want="${GITHUB}/${repo}.git"; else want="${GITEA_IN}/${repo}.git"; fi
  main="$(cat "${work}/main-${repo}")"
  while :; do
    kubectl -n "${NS}" get application "${app}" -o json > "${work}/app.json"
    verdict="$(python3 - "${work}/app.json" "${want}" "${main}" << 'PY'
import json, sys
a, want, main = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
if (a["spec"].get("source") or {}).get("repoURL") != want:
    print("FAIL spec.source.repoURL is %s" % (a["spec"].get("source") or {}).get("repoURL")); sys.exit()
st = a.get("status") or {}
errs = [c.get("message", "") for c in st.get("conditions") or [] if c.get("type") == "ComparisonError"]
sync = st.get("sync") or {}
compared = ((sync.get("comparedTo") or {}).get("source") or {}).get("repoURL")
if compared == want and sync.get("revision") == main and not errs:
    print("ok %s at %s" % (sync.get("status"), main[:12]))
elif errs:
    print("WAIT ComparisonError: %s" % errs[0][:200])
else:
    print("WAIT compared %s at %s" % (compared, (sync.get("revision") or "")[:12]))
PY
)"
    case "${verdict}" in
      ok*) echo "ok    ${app}: ${verdict#ok }"; break ;;
      FAIL*) die "${app}: ${verdict#FAIL }" ;;
    esac
    if (( $(date +%s) >= deadline )); then
      die "${app}: after ${WAIT_S}s still ${verdict#WAIT }; the move back is: bash ${BASH_SOURCE[0]} back"
    fi
    sleep 10
  done
done
echo "== ${mode} done: the five Applications read $([[ "${mode}" == back ]] && echo GitHub || echo Gitea)"
