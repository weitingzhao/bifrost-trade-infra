#!/usr/bin/env bash
# ensure-push-webhooks.sh [<repo>...] — every repository Gitea holds as its
# primary needs its push webhook to the CI EventListener: CI routes the ones it
# builds, and every push to main or a tag starts the GitHub copy
# (k8s/cicd/tekton/trigger-trade-ci.yaml, trigger github-sync). Infra and the
# three plugins never had one while they were pull mirrors without CI, so after
# batch C a push to them reached GitHub only with the 15-minute reconcile
# (2026-10-17 23:5x). Default: the repositories in agent-config/gitea-primary.txt.
#
# For each repository it reads the hooks; one already pointing at EL_URL is left
# as it is when it is a gitea hook, json, POST, with the push event and active,
# and is reported otherwise (not changed). A repository without one gets it,
# then the hooks are read back. The admin token comes from Secret
# cicd/gitea-bootstrap through lib.sh (never on a command line). Exits 1 on any
# repository that does not end with a right hook.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
EL_URL="${EL_URL:-http://el-bifrost-ci.cicd.svc.cluster.local:8080}"
LIST="${PRIMARY_LIST:-$HERE/../../agent-config/gitea-primary.txt}"
if [[ $# -eq 0 ]]; then
  set -- $(sed -e 's/#.*//' -e 's/[[:space:]]//g' "${LIST}" | grep -v '^$')
fi
[[ $# -ge 1 ]] || gitea_die "no repositories (the list ${LIST} is empty)"
for repo in "$@"; do
  [[ "${repo}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || gitea_die "not a repository name: ${repo}"
done
JUDGE='
import json, sys
url = sys.argv[1]
hooks = [h for h in json.load(sys.stdin) if (h.get("config") or {}).get("url", "").rstrip("/") == url.rstrip("/")]
if not hooks:
    print("none"); sys.exit()
h, c = hooks[0], hooks[0].get("config") or {}
bad = []
if h.get("type") != "gitea": bad.append("type %s" % h.get("type"))
if not h.get("active"): bad.append("not active")
if c.get("content_type") != "json": bad.append("content type %s" % c.get("content_type"))
if (c.get("http_method") or "post").lower() != "post": bad.append("method %s" % c.get("http_method"))
if "push" not in (h.get("events") or []): bad.append("no push event")
print("ok" if not bad else "wrong: " + "; ".join(bad))
'
gitea_connect
payload="$(python3 -c 'import json,sys; print(json.dumps({"type": "gitea", "active": True, "events": ["push"], "config": {"url": sys.argv[1], "content_type": "json", "http_method": "post"}}))' "${EL_URL}")"
fail=0
for repo in "$@"; do
  hooks="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/hooks")" || gitea_die "cannot read the hooks of ${repo}"
  state="$(python3 -c "${JUDGE}" "${EL_URL}" <<< "${hooks}")"
  case "${state}" in
    ok) echo "${repo}: push webhook already there" ;;
    none)
      gitea_api POST "/repos/${GITEA_ORG}/${repo}/hooks" "${payload}" > /dev/null || gitea_die "${repo}: creating the hook refused"
      hooks="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/hooks")" || gitea_die "cannot read the hooks of ${repo}"
      state="$(python3 -c "${JUDGE}" "${EL_URL}" <<< "${hooks}")"
      if [[ "${state}" == ok ]]; then echo "${repo}: push webhook created and read back"; else echo "${repo}: READ BACK ${state}"; fail=1; fi ;;
    *) echo "${repo}: a hook to ${EL_URL} is there but ${state#wrong: }; left as it is"; fail=1 ;;
  esac
done
exit "${fail}"
