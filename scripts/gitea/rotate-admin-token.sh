#!/usr/bin/env bash
# rotate-admin-token.sh check|rotate|revoked — TD-365: the Gitea admin token
# in Secret cicd/gitea-bootstrap (gitea_admin_token) has been in the public
# infra history since 2026-06-17 (d30ef90), and the clone credentials in
# Secret cicd/gitea-git-credentials (password, used by every Tekton clone)
# held the same token there. The Owner makes a new token in Gitea; this puts
# it in every place that holds the old one; only then is the old one revoked
# (OWNER-STEPS-gitea-primary.md section 0).
#
#   check    read only: which Gitea user each Secret's token logs in as, and
#            whether the clone password is the same token as the admin token
#   rotate   reads the new token hidden and tries it for what the two Secrets
#            are used for before writing anything (review 256 A2): it must be
#            40 hex characters, not the current one, log in as the same Gitea
#            administrator, read a repository (read:repository: lineage,
#            clones) and ask a mirror to fetch (write:repository: mirror-sync).
#            Then the clone password first, gitea_admin_token second, each only
#            if the Secret is still as it was read (resourceVersion; review 256
#            B5). Writing the clone first means a failure half-way never
#            leaves the clone on the old token while the admin token is new;
#            running rotate again, with the same or another new token,
#            finishes it (review 256 A1). Done means: gitea_admin_token is the
#            new token and neither Secret holds the token the admin Secret had
#            when rotation began.
#   revoked  after the Owner revoked the old token in Gitea: the token in the
#            leaked file (read by its pinned blob id, no replacement objects;
#            review 256 B6) must be refused (HTTP 401) and both Secrets'
#            values, as stored, must log in
#
# Values are compared as stored, byte for byte; a stored value that is not 40
# hex characters is reported, never sent (review 256 B3, B4). No token is
# printed or put on a command line: Secrets are read as JSON into python,
# tokens travel in environment variables to python only, writes go to kubectl
# through a pipe; no proxy, no redirect, xtrace off. Gitea is always reached
# through the port-forward of the Owner's admin kubeconfig (lib.sh): GITEA_API
# and the like are honoured only in the tests' mode (ROTATE_TEST_MODE=1;
# review 256 B7). Stops at the first error.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ "${ROTATE_TEST_MODE:-}" != 1 ]]; then
  unset GITEA_API GITEA_GIT_BASE GITEA_TOKEN
fi
# shellcheck source=lib.sh
source "$HERE/lib.sh"
INFRA="$(cd "${HERE}/../.." && pwd -P)"
LEAKED_COMMIT=d30ef90cd8c7fee37e8beb4fd3f3712e77544344
LEAKED_BLOB=380df47bb115a3019a6b1a223731f9bf85b3b628 # k8s/cicd/gitea/secret.yaml in that commit
if [[ "${ROTATE_TEST_MODE:-}" == 1 ]]; then
  # the tests bring their own repository with a leaked file of fixture tokens
  INFRA="${ROTATE_TEST_INFRA:-${INFRA}}" LEAKED_COMMIT="${ROTATE_TEST_LEAKED_COMMIT:-${LEAKED_COMMIT}}" LEAKED_BLOB="${ROTATE_TEST_LEAKED_BLOB:-${LEAKED_BLOB}}"
fi
LOCAL_COPY="${INFRA}/k8s/cicd/gitea/secret.yaml"
export GIT_NO_REPLACE_OBJECTS=1
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES \
  GIT_NAMESPACE GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT GIT_EXEC_PATH

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

# read_leaked — the leaked file, by its pinned blob id, checked against that id
read_leaked() {
  git -C "${INFRA}" cat-file -e "${LEAKED_COMMIT}^{commit}" 2> /dev/null || gitea_die "commit ${LEAKED_COMMIT} is not in ${INFRA}; git fetch there first"
  [[ "$(git -C "${INFRA}" rev-parse "${LEAKED_COMMIT}:k8s/cicd/gitea/secret.yaml")" == "${LEAKED_BLOB}" ]] ||
    gitea_die "the leaked file in ${LEAKED_COMMIT} is not blob ${LEAKED_BLOB}"
  (umask 077 && git -C "${INFRA}" cat-file blob "${LEAKED_BLOB}" > "${work}/leaked.yaml")
  [[ "$(git -C "${INFRA}" hash-object --no-filters -- "${work}/leaked.yaml")" == "${LEAKED_BLOB}" ]] ||
    gitea_die "the leaked file as read is not blob ${LEAKED_BLOB}"
}

# py PROGRAM ARGS… — python with this file's helpers:
#   secret(file, key)  one key of a Secret file, decoded, exactly as stored
#   rv(file)           its resourceVersion
#   clean(value)       a token as Gitea makes them: 40 hex characters
#   call(token, method, path)  the HTTP status of a Gitea API call with that
#                      token, and the parsed answer; a token that is not clean
#                      is not sent; no proxy, no redirect; no exception text
#                      (it could hold the header) is ever shown
#   login(token)       "user <login>" (or "admin <login>"), or why not
#   leaked_tokens(file) the tokens the leaked file holds
py() {
  local program="$1"
  shift
  gitea_alive
  python3 -c '
import base64, json, os, re, sys, urllib.error, urllib.request
def secret(path, key):
    data = json.load(open(path)).get("data") or {}
    return base64.b64decode(data[key]).decode("utf-8", "replace") if key in data else None
def rv(path):
    return json.load(open(path))["metadata"]["resourceVersion"]
def clean(value):
    return bool(value) and re.fullmatch("[0-9a-f]{40}", value) is not None
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)
def call(token, method, path):
    if not clean(token):
        return "not a clean token", None
    req = urllib.request.Request(os.environ["GITEA_API"].rstrip("/") + path, method=method,
                                 data=b"{}" if method == "POST" else None,
                                 headers={"Authorization": "token " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return "no answer (%s)" % type(e).__name__, None
def login(token):
    code, answer = call(token, "GET", "/user")
    if code != 200 or not isinstance(answer, dict):
        return code if isinstance(code, str) else "HTTP %s" % code
    return ("admin " if answer.get("is_admin") else "user ") + str(answer.get("login", "?"))
def leaked_tokens(path):
    return set(re.findall(r"(?:gitea_admin_token|password):\s*\"?([0-9a-f]{40})\"?", open(path).read()))
'"${program}" "$@"
}

describe() {
  py '
admin = secret(sys.argv[1], "gitea_admin_token")
clone_user, clone = secret(sys.argv[2], "username"), secret(sys.argv[2], "password")
print("gitea-bootstrap gitea_admin_token:", login(admin) if admin is not None else "missing")
print("gitea-git-credentials password:   ", login(clone) if clone is not None else "missing", "(username %s)" % clone_user)
print("the clone password is", "THE SAME token as the admin token" if admin is not None and admin == clone else "a different token")
' "${work}/bootstrap.json" "${work}/clone.json"
}

# patch NAME KEY RESOURCEVERSION — writes NEW_TOKEN into that key, only if the
# Secret is still at that resourceVersion
patch() {
  py 'print(json.dumps({"metadata": {"resourceVersion": sys.argv[2]}, "stringData": {sys.argv[1]: os.environ["NEW_TOKEN"]}}))' "$2" "$3" |
    kubectl -n cicd patch secret "$1" --type merge --patch-file /dev/stdin > /dev/null
}

case "${step}" in
  check)
    read_secrets
    describe
    ;;

  rotate)
    read_secrets
    read_leaked
    describe
    read -rs -p "New Gitea admin token (made in Gitea → Settings → Applications): " NEW_TOKEN
    echo
    NEW_TOKEN="${NEW_TOKEN//[[:space:]]/}"
    export NEW_TOKEN
    # what to write, decided before anything is written; the new token tried for its uses.
    # "old" is a token in the leaked file (or, for the clone, the same value as the admin token now)
    plan="$(py '
new = os.environ["NEW_TOKEN"]
admin = secret(sys.argv[1], "gitea_admin_token")
clone = secret(sys.argv[2], "password")
leaked = leaked_tokens(sys.argv[3])
org = sys.argv[4]
if not clean(new):
    sys.exit("not a Gitea token (40 hex characters); nothing changed")
if new in leaked:
    sys.exit("that is the leaked token; make a new one; nothing changed")
if not clean(admin):
    sys.exit("gitea_admin_token as stored is not a clean token; look at the Secret first; nothing changed")
clone_old = clone is not None and (clone == admin or clone in leaked or clone.strip() in leaked)
admin_old = admin != new
want = login(admin)
if not want.startswith("admin "):
    sys.exit("the current admin token does not log in as a Gitea administrator (%s); nothing changed" % want)
got = login(new)
if got != want:
    sys.exit("the new token logs in as %s, the current one as %s; nothing changed" % (got, want))
code, repos = call(new, "GET", "/orgs/%s/repos?limit=50" % org)
if code != 200 or not isinstance(repos, list) or not repos:
    sys.exit("the new token cannot list the repositories of %s (%s): give it repository and organization Read and Write; nothing changed" % (org, code))
code, _ = call(new, "GET", "/repos/%s/%s/branches?limit=1" % (org, repos[0]["name"]))
if code != 200:
    sys.exit("the new token cannot read %s/%s (%s): give it repository Read and Write; nothing changed" % (org, repos[0]["name"], code))
mirrors = [r["name"] for r in repos if r.get("mirror") is True]
if mirrors:
    code, _ = call(new, "POST", "/repos/%s/%s/mirror-sync" % (org, mirrors[0]))
    if code != 200:
        sys.exit("the new token cannot ask %s/%s to fetch (%s): give it repository Read and Write; nothing changed" % (org, mirrors[0], code))
else:
    print("note: no mirror left to try mirror-sync on; write:repository not tried", file=sys.stderr)
print(("clone " if clone_old else "") + ("admin" if admin_old else "") or "nothing")
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" "${GITEA_ORG}")" || gitea_die "${plan:-the new token did not pass the checks}"
    # the clone first: a failure after it leaves the clone on a token that keeps working
    if [[ "${plan}" == clone* ]]; then
      patch gitea-git-credentials password "$(py 'print(rv(sys.argv[1]))' "${work}/clone.json")" ||
        gitea_die "could not write gitea-git-credentials (changed since it was read, or refused); nothing changed; run rotate again"
    fi
    if [[ "${plan}" == *admin ]]; then
      patch gitea-bootstrap gitea_admin_token "$(py 'print(rv(sys.argv[1]))' "${work}/bootstrap.json")" ||
        gitea_die "gitea-bootstrap could not be written (changed since it was read, or refused): run rotate again, with the same or another new token; do not revoke the old one yet"
    fi
    [[ "${plan}" != nothing ]] || echo "both Secrets already free of the leaked token and gitea_admin_token is this token; nothing to write"
    read_secrets
    py '
new = os.environ["NEW_TOKEN"]
leaked = leaked_tokens(sys.argv[3])
admin, clone = secret(sys.argv[1], "gitea_admin_token"), secret(sys.argv[2], "password")
clone_old = clone is not None and (clone in leaked or clone.strip() in leaked)
print("gitea-bootstrap gitea_admin_token:", "the new token" if admin == new else "NOT the new token")
print("gitea-git-credentials password:   ", "the new token" if clone == new else "STILL THE LEAKED TOKEN" if clone_old else "another token (not the leaked one)")
local = sys.argv[4]
if os.path.exists(local):
    text = open(local).read()
    print("local copy", local, "holds the new token" if new in text else "still holds an old token: delete it (the cluster Secret is the one that counts)")
sys.exit(0 if admin == new and not clone_old else 1)
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" "${LOCAL_COPY}" ||
      gitea_die "not done: a Secret still holds the leaked token or gitea_admin_token is not the new one; do not revoke the old one"
    unset NEW_TOKEN
    echo "==> rotated. Do not revoke the old token yet: say 「Gitea 令牌换好了」 in the thread first."
    ;;

  revoked)
    read_secrets
    read_leaked
    py '
old = sorted(leaked_tokens(sys.argv[3]))
bad = 0
for i, token in enumerate(old, 1):
    answer = login(token)
    print("token %d from the public history:" % i, answer, "(refused, as it should be)" if answer == "HTTP 401" else "STILL ACCEPTED or not refused: revoke it")
    bad += answer != "HTTP 401"
for path, key, name in ((sys.argv[1], "gitea_admin_token", "gitea-bootstrap"), (sys.argv[2], "password", "gitea-git-credentials")):
    value = secret(path, key)
    answer = login(value) if value is not None else "missing"
    print(name + ":", answer)
    bad += not (answer.startswith("user ") or answer.startswith("admin "))
sys.exit(1 if bad or not old else 0)
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" || gitea_die "not done yet: see the lines above"
    echo "==> the leaked tokens are refused; both Secrets log in."
    ;;
esac
