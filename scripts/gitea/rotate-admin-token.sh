#!/usr/bin/env bash
# rotate-admin-token.sh check|rotate|revoked — TD-365: the Gitea admin token
# in Secret cicd/gitea-bootstrap (gitea_admin_token) has been in the public
# infra history since 2026-06-17 (d30ef90), and the clone credentials in
# Secret cicd/gitea-git-credentials (password, used by every Tekton clone)
# held a token there too. The Owner makes a new token in Gitea; this puts it
# in every place that holds the old one; only then is the old one revoked
# (OWNER-STEPS-gitea-primary.md section 0).
#
#   check    read only: which Gitea user each Secret's token logs in as, and
#            whether the clone password is the same token as the admin token
#   rotate   reads the new token hidden, checks it (40 hex characters, not the
#            current one, Gitea answers /api/v1/user with it for the same user
#            as the current admin token), then writes it into gitea_admin_token
#            and, where it held the same old token, the clone password; reads
#            both back. Says whether the ignored local copy
#            k8s/cicd/gitea/secret.yaml still holds the old token.
#   revoked  after the Owner revoked the old token in Gitea: the token from
#            the public history (d30ef90) must now be refused (HTTP 401), and
#            both Secrets' tokens still accepted
#
# No token is printed or put on a command line: Secrets are read as JSON into
# python, tokens travel in environment variables to python only, writes go to
# kubectl through a pipe. Uses the Owner's admin kubeconfig (lib.sh). Stops at
# the first error.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
INFRA="$(cd "${HERE}/../.." && pwd -P)"
LEAKED=d30ef90
LOCAL_COPY="${INFRA}/k8s/cicd/gitea/secret.yaml"

[[ "${1:-}" == check || "${1:-}" == rotate || "${1:-}" == revoked ]] || gitea_die "usage: rotate-admin-token.sh check|rotate|revoked"
step="$1"
gitea_connect
work="$(mktemp -d)"
trap 'gitea_cleanup; rm -rf "${work}"' EXIT
chmod 700 "${work}"

# read_secrets — both Secrets as JSON into the work directory (mode 600)
read_secrets() {
  (umask 077 && kubectl -n cicd get secret gitea-bootstrap -o json > "${work}/bootstrap.json") || gitea_die "cannot read Secret cicd/gitea-bootstrap"
  (umask 077 && kubectl -n cicd get secret gitea-git-credentials -o json > "${work}/clone.json") || gitea_die "cannot read Secret cicd/gitea-git-credentials"
}

# py PROGRAM ARGS… — python with this file's helpers: secret(file, key) decodes
# one key of a Secret file, login(token) asks Gitea which user the token is
# (HTTP status on failure); no proxy, no redirect
py() {
  local program="$1"
  shift
  gitea_alive
  python3 -c '
import base64, json, os, sys, urllib.error, urllib.request
def secret(path, key):
    data = json.load(open(path)).get("data") or {}
    return base64.b64decode(data[key]).decode().strip() if key in data else None
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)
def login(token):
    req = urllib.request.Request(os.environ["GITEA_API"].rstrip("/") + "/user", headers={"Authorization": "token " + token})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
            return "user " + json.load(r).get("login", "?")
    except urllib.error.HTTPError as e:
        return "HTTP %d" % e.code
    except (urllib.error.URLError, OSError) as e:
        return "no answer (%s)" % e
'"${program}" "$@"
}

describe() {
  py '
admin = secret(sys.argv[1], "gitea_admin_token")
clone_user, clone = secret(sys.argv[2], "username"), secret(sys.argv[2], "password")
print("gitea-bootstrap gitea_admin_token:", login(admin) if admin else "missing")
print("gitea-git-credentials password:   ", login(clone) if clone else "missing", "(username %s)" % clone_user)
print("the clone password is", "THE SAME token as the admin token" if admin and admin == clone else "a different token")
' "${work}/bootstrap.json" "${work}/clone.json"
}

case "${step}" in
  check)
    read_secrets
    describe
    ;;

  rotate)
    read_secrets
    describe
    read -rs -p "New Gitea admin token (made in Gitea → Settings → Applications): " NEW_TOKEN
    echo
    export NEW_TOKEN
    # what to change, decided before anything is written
    plan="$(py '
new = os.environ["NEW_TOKEN"].strip()
admin = secret(sys.argv[1], "gitea_admin_token")
clone = secret(sys.argv[2], "password")
if not (len(new) == 40 and all(c in "0123456789abcdef" for c in new)):
    sys.exit("not a Gitea token (40 hex characters); nothing changed")
if new == admin:
    sys.exit("that is the current admin token; make a new one; nothing changed")
want, got = login(admin), login(new)
if not want.startswith("user "):
    sys.exit("the current admin token does not log in (%s); nothing changed" % want)
if got != want:
    sys.exit("the new token logs in as %s, the current one as %s; nothing changed" % (got, want))
print("clone" if clone == admin else "admin-only")
' "${work}/bootstrap.json" "${work}/clone.json")" || gitea_die "${plan:-the new token did not pass the checks}"
    py 'print(json.dumps({"stringData": {"gitea_admin_token": os.environ["NEW_TOKEN"].strip()}}))' |
      kubectl -n cicd patch secret gitea-bootstrap --type merge --patch-file /dev/stdin > /dev/null ||
      gitea_die "could not write gitea-bootstrap; nothing else changed"
    if [[ "${plan}" == clone ]]; then
      py 'print(json.dumps({"stringData": {"password": os.environ["NEW_TOKEN"].strip()}}))' |
        kubectl -n cicd patch secret gitea-git-credentials --type merge --patch-file /dev/stdin > /dev/null ||
        gitea_die "gitea-bootstrap has the new token but gitea-git-credentials could not be written: run rotate again with the same new token, and do not revoke the old one yet"
    fi
    read_secrets
    py '
new = os.environ["NEW_TOKEN"].strip()
ok = secret(sys.argv[1], "gitea_admin_token") == new
print("gitea-bootstrap gitea_admin_token:", "the new token" if ok else "NOT the new token")
clone_new = secret(sys.argv[2], "password") == new
print("gitea-git-credentials password:   ", "the new token" if clone_new else ("not changed (it was a different token)" if sys.argv[3] != "clone" else "NOT the new token"))
local = sys.argv[4]
if os.path.exists(local):
    text = open(local).read()
    print("local copy", local, "still holds the OLD token: delete it (the cluster Secret is the one that counts)" if new not in text else "holds the new token")
sys.exit(0 if ok and (clone_new or sys.argv[3] != "clone") else 1)
' "${work}/bootstrap.json" "${work}/clone.json" "${plan}" "${LOCAL_COPY}" || gitea_die "a Secret does not hold the new token after the write; do not revoke the old one"
    unset NEW_TOKEN
    echo "==> rotated. Do not revoke the old token yet: say 「Gitea 令牌换好了」 in the thread first."
    ;;

  revoked)
    read_secrets
    git -C "${INFRA}" cat-file -e "${LEAKED}:k8s/cicd/gitea/secret.yaml" 2> /dev/null || gitea_die "commit ${LEAKED} is not in ${INFRA}; git fetch there first"
    git -C "${INFRA}" show "${LEAKED}:k8s/cicd/gitea/secret.yaml" > "${work}/leaked.yaml"
    py '
import re
text = open(sys.argv[3]).read()
old = sorted(set(re.findall(r"(?:gitea_admin_token|password):\s*\"?([0-9a-f]{40})\"?", text)))
bad = 0
for i, token in enumerate(old, 1):
    answer = login(token)
    print("token %d from the public history:" % i, answer, "(refused, as it should be)" if answer == "HTTP 401" else "STILL ACCEPTED: revoke it")
    bad += answer != "HTTP 401"
for path, key, name in ((sys.argv[1], "gitea_admin_token", "gitea-bootstrap"), (sys.argv[2], "password", "gitea-git-credentials")):
    answer = login(secret(path, key) or "")
    print(name + ":", answer)
    bad += not answer.startswith("user ")
sys.exit(1 if bad or not old else 0)
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" || gitea_die "not done yet: see the lines above"
    echo "==> the leaked tokens are refused; both Secrets log in."
    ;;
esac
