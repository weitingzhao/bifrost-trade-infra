#!/usr/bin/env bash
# rotate-admin-token.sh check|rotate|revoked — TD-365: the Gitea admin token
# in Secret cicd/gitea-bootstrap (gitea_admin_token) has been in the public
# infra history since 2026-06-17 (d30ef90), and the clone credentials in
# Secret cicd/gitea-git-credentials (username, password: basic auth for every
# Tekton clone) held the same token there. The Owner makes a new token in
# Gitea; this puts it in every place that needs it; only then is the old one
# revoked (OWNER-STEPS-gitea-primary.md section 0).
#
#   check    read only: what each Secret's credential is good for now, and
#            whether it is still the leaked token
#   rotate   reads the new token hidden and tries it, before writing anything,
#            for what the Secrets are used for (review 256 A2, 257 A1, B4, B6):
#            40 hex characters, not the leaked token; logs in as the Gitea
#            administrator ADMIN_LOGIN (whatever the current token can still
#            do: a broken or revoked one can be replaced); reads a repository
#            (read:repository: lineage, clones); and asks a regular repository
#            of the org to mirror-sync, which Gitea answers 400 "not a mirror"
#            only once the token's write:repository scope has passed (403
#            without it), so no mirror is touched; no regular repository means
#            nothing is written (section 1 makes bifrost/primary-probe).
#            Then the clone password first (when it is the leaked token, the
#            admin token at the start, or the administrator's and no longer
#            works), gitea_admin_token second, each only if the Secret is as it
#            was read (resourceVersion). A failure half-way leaves the clone on
#            a working token; rotate run again finishes it (review 256 A1).
#            Done means: gitea_admin_token is the new token; neither Secret
#            holds the leaked token or, unless it is the new one, the admin
#            token of the start (review 257 B3); and both work as their users
#            use them, the clone by basic auth like Tekton, over the API and
#            over Git HTTP for every repository of the org (review 257 B2,
#            258 B2, B8).
#   revoked  after the Owner revoked the old token in Gitea: the token in the
#            leaked file (read by its pinned blob id, no replacement objects)
#            must be refused (HTTP 401) and both Secrets must still work
#
# Values are compared as stored, byte for byte; a stored value that is not 40
# hex characters is reported, never sent. No token is printed or put on a
# command line: Secrets are read as JSON into python, tokens travel in
# environment variables to python only, writes go to kubectl through a pipe;
# no proxy, no redirect, xtrace off. Gitea is reached through the port-forward
# of the Owner's admin kubeconfig (lib.sh). The tests' mode (ROTATE_TEST_MODE=1)
# takes GITEA_API from the environment and sends every kubectl call, lib.sh's
# included, to ROTATE_TEST_KUBECTL, which must be the tests' fake (it carries
# their marker line), so the tests' mode cannot reach a cluster (review 257 B5).
# Stops at the first error.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ADMIN_LOGIN=weitingzhao
if [[ "${ROTATE_TEST_MODE:-}" == 1 ]]; then
  grep -qx '# rotate-admin-token fake kubectl' "${ROTATE_TEST_KUBECTL:-/nonexistent}" 2> /dev/null ||
    { echo "rotate-admin-token.sh: the tests' mode needs ROTATE_TEST_KUBECTL to be the tests' fake kubectl" >&2; exit 1; }
  kubectl() { "${ROTATE_TEST_KUBECTL}" "$@"; }
else
  unset GITEA_API GITEA_GIT_BASE GITEA_TOKEN
fi
# lib.sh would load the admin token from the Secret and stop when it is empty;
# this script reads both Secrets itself, so a broken one can be replaced
# (review 258 B4). The value below is never sent anywhere.
export GITEA_TOKEN=not-used-by-rotate-admin-token
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
export GIT_NO_REPLACE_OBJECTS=1 ADMIN_LOGIN
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
#   secret(file, key)    one key of a Secret file, decoded, exactly as stored
#   rv(file)             its resourceVersion
#   clean(value)         a token as Gitea makes them: 40 hex characters
#   call(auth, method, path)  HTTP status and parsed answer of a Gitea API call;
#                        auth is a token, or (user, password) for basic auth as
#                        Tekton's clones use it; a credential that is not clean
#                        is not sent; no proxy, no redirect, no exception text
#   login(token)         "admin <login>", "user <login>", or why not
#   repos(token)         every repository of the org (all pages), or a reason
#   can_read(auth, repo) a branch of the repository can be read
#   can_write(token, regular_repo)  write:repository passed (400 "not a mirror")
#   leaked_tokens(file)  the tokens the leaked file holds
py() {
  local program="$1"
  shift
  gitea_alive
  python3 -c '
import base64, json, os, re, sys, urllib.error, urllib.request
ORG, ADMIN = os.environ["GITEA_ORG_NAME"], os.environ["ADMIN_LOGIN"]
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
def call(auth, method, path):
    if isinstance(auth, tuple):
        user, password = auth
        if not clean(password) or not user or ":" in user:
            return "not a clean credential", None
        header = "Basic " + base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
    else:
        if not clean(auth):
            return "not a clean token", None
        header = "token " + auth
    req = urllib.request.Request(os.environ["GITEA_API"].rstrip("/") + path, method=method,
                                 data=b"{}" if method == "POST" else None,
                                 headers={"Authorization": header, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"null")
        except ValueError:
            body = None
        return e.code, body
    except Exception as e:
        return "no answer (%s)" % type(e).__name__, None
def login(token):
    code, answer = call(token, "GET", "/user")
    if code != 200 or not isinstance(answer, dict):
        return code if isinstance(code, str) else "HTTP %s" % code
    return ("admin " if answer.get("is_admin") else "user ") + str(answer.get("login", "?"))
def repos(token):
    found, page = [], 1
    while page <= 100:
        code, answer = call(token, "GET", "/orgs/%s/repos?limit=50&page=%d" % (ORG, page))
        if code != 200 or not isinstance(answer, list):
            return "cannot list the repositories of %s (%s)" % (ORG, code)
        if not answer:
            return found
        found += answer
        page += 1
    return "more than 100 pages of repositories in %s" % ORG
def can_read(auth, repo):
    code, _ = call(auth, "GET", "/repos/%s/%s/branches?limit=1" % (ORG, repo))
    return code == 200
def can_write(token, regular):
    code, answer = call(token, "POST", "/repos/%s/%s/mirror-sync" % (ORG, regular))
    return code == 400 and isinstance(answer, dict) and "not a mirror" in str(answer.get("message", "")).lower()
def git_reads(user, password, names):
    """the repositories (of names) that the credentials cannot list over Git HTTP by basic auth, as Tekton clones"""
    import subprocess
    if not clean(password) or not user or ":" in user:
        return list(names)
    base = os.environ["GITEA_GIT_BASE"].rstrip("/")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="2",
               GIT_CONFIG_KEY_0="http.%s/.extraHeader" % base,
               GIT_CONFIG_VALUE_0="Authorization: Basic " + base64.b64encode(("%s:%s" % (user, password)).encode()).decode(),
               GIT_CONFIG_KEY_1="http.followRedirects", GIT_CONFIG_VALUE_1="false")
    failed = []
    for name in names:
        try:
            r = subprocess.run(["git", "ls-remote", "--heads", "%s/%s/%s.git" % (base, ORG, name)], env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
            if r.returncode != 0:
                failed.append(name)
        except Exception:
            failed.append(name)
    return failed
def leaked_tokens(path):
    return set(re.findall(r"(?:gitea_admin_token|password):\s*\"?([0-9a-f]{40})\"?", open(path).read()))
'"${program}" "$@"
}
export GITEA_ORG_NAME="${GITEA_ORG}"

# patch NAME KEY RESOURCEVERSION — writes NEW_TOKEN into that key, only if the
# Secret is still at that resourceVersion
patch() {
  py 'print(json.dumps({"metadata": {"resourceVersion": sys.argv[2]}, "stringData": {sys.argv[1]: os.environ["NEW_TOKEN"]}}))' "$2" "$3" |
    kubectl -n cicd patch secret "$1" --type merge --patch-file /dev/stdin > /dev/null
}

# the shared part of check and the end of rotate: what each Secret is good for
DESCRIBE='
def describe(bootstrap, clone_file):
    admin = secret(bootstrap, "gitea_admin_token")
    user, clone = secret(clone_file, "username"), secret(clone_file, "password")
    listed = repos(admin) if clean(admin) else []
    first = listed[0]["name"] if isinstance(listed, list) and listed else None
    print("gitea-bootstrap gitea_admin_token:", login(admin) if admin is not None else "missing")
    print("gitea-git-credentials %s:" % ("(username %s)" % user), "can read %s/%s" % (ORG, first) if first and clone is not None and can_read((user, clone), first) else "CANNOT read a repository as Tekton does" if clone is not None else "no password")
    print("the clone password is", "THE SAME token as the admin token" if admin is not None and admin == clone else "a different token")
'

case "${step}" in
  check)
    read_secrets
    read_leaked
    py "${DESCRIBE}"'
describe(sys.argv[1], sys.argv[2])
leaked = leaked_tokens(sys.argv[3])
for path, key, name in ((sys.argv[1], "gitea_admin_token", "gitea-bootstrap"), (sys.argv[2], "password", "gitea-git-credentials")):
    value = secret(path, key)
    print(name + ":", "STILL THE LEAKED TOKEN (not rotated yet)" if value is not None and (value in leaked or value.strip() in leaked) else "not the leaked token")
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml"
    ;;

  rotate)
    read_secrets
    read_leaked
    py "${DESCRIBE}"'
describe(sys.argv[1], sys.argv[2])
' "${work}/bootstrap.json" "${work}/clone.json"
    read -rs -p "New Gitea admin token (made in Gitea → Settings → Applications): " NEW_TOKEN
    echo
    NEW_TOKEN="${NEW_TOKEN//[[:space:]]/}"
    export NEW_TOKEN
    cp "${work}/bootstrap.json" "${work}/bootstrap.start.json"
    # what to write, decided before anything is written; the new token tried for its uses
    plan="$(py '
new = os.environ["NEW_TOKEN"]
admin = secret(sys.argv[1], "gitea_admin_token")
user, clone = secret(sys.argv[2], "username"), secret(sys.argv[2], "password")
leaked = leaked_tokens(sys.argv[3])
if not clean(new):
    sys.exit("not a Gitea token (40 hex characters); nothing changed")
if new in leaked:
    sys.exit("that is the leaked token; make a new one; nothing changed")
got = login(new)
if got != "admin " + ADMIN:
    sys.exit("the new token logs in as %s, not as the administrator %s; nothing changed" % (got, ADMIN))
now = login(admin) if admin is not None else "missing"
if now.startswith(("admin ", "user ")) and now != "admin " + ADMIN:
    sys.exit("gitea_admin_token now logs in as %s, not as %s; look before replacing it; nothing changed" % (now, ADMIN))
listed = repos(new)
if not isinstance(listed, list) or not listed:
    sys.exit("the new token %s: give it repository and organization Read and Write; nothing changed" % (listed or "sees no repository"))
if not can_read(new, listed[0]["name"]):
    sys.exit("the new token cannot read %s/%s: give it repository Read and Write; nothing changed" % (ORG, listed[0]["name"]))
regular = [r["name"] for r in listed if r.get("mirror") is False]
if not regular:
    sys.exit("no regular repository in %s to test write:repository on (section 1 makes %s/primary-probe); nothing changed" % (ORG, ORG))
if not can_write(new, regular[0]):
    sys.exit("the new token cannot write %s/%s (mirror-sync not let through): give it repository Read and Write; nothing changed" % (ORG, regular[0]))
clone_works = clone is not None and can_read((user, clone), listed[0]["name"])
clone_old = clone is not None and (clone == admin or clone in leaked or clone.strip() in leaked)
clone_admins = user == ADMIN
if (clone_old or not clone_works) and not clone_admins:
    sys.exit("the clone credentials (user %s) %s and are not the administrator%ss; fix them by hand; nothing changed" % (user, "hold the old token" if clone_old else "do not work", chr(39)))
write_clone = clone_old or not clone_works
print(("clone " if write_clone else "") + ("admin" if admin != new else "") or "nothing")
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml")" || gitea_die "${plan:-the new token did not pass the checks}"
    # the clone first: a failure after it leaves the clone on a token that works
    if [[ "${plan}" == clone* ]]; then
      patch gitea-git-credentials password "$(py 'print(rv(sys.argv[1]))' "${work}/clone.json")" ||
        gitea_die "could not write gitea-git-credentials (changed since it was read, or refused); nothing changed; run rotate again"
    fi
    if [[ "${plan}" == *admin ]]; then
      patch gitea-bootstrap gitea_admin_token "$(py 'print(rv(sys.argv[1]))' "${work}/bootstrap.json")" ||
        gitea_die "gitea-bootstrap could not be written (changed since it was read, or refused): run rotate again, with the same or another new token; do not revoke the old one yet"
    fi
    [[ "${plan}" != nothing ]] || echo "nothing to write: gitea_admin_token is this token and the clone credentials work and hold no old token"
    read_secrets
    report="$(py "${DESCRIBE}"'
new = os.environ["NEW_TOKEN"]
leaked = leaked_tokens(sys.argv[3])
start = secret(sys.argv[4], "gitea_admin_token")
admin = secret(sys.argv[1], "gitea_admin_token")
user, clone = secret(sys.argv[2], "username"), secret(sys.argv[2], "password")
describe(sys.argv[1], sys.argv[2])
old = set(leaked) | ({start} if start is not None and start != new else set())
listed = repos(new)
first = listed[0]["name"] if isinstance(listed, list) and listed else None
problems = []
if admin != new:
    problems.append("gitea_admin_token is not the new token")
if clone is None or clone in old or clone.strip() in old:
    problems.append("the clone password is still an old token")
if not first or clone is None or not can_read((user, clone), first):
    problems.append("the clone credentials do not read a repository")
elif isinstance(listed, list):
    unread = git_reads(user, clone, [r["name"] for r in listed])
    if unread:
        problems.append("the clone credentials cannot list over Git HTTP: " + ", ".join(unread))
    else:
        print("gitea-git-credentials lists all %d repositories of %s over Git HTTP, as Tekton clones" % (len(listed), ORG))
local = sys.argv[5]
if os.path.exists(local):
    text = open(local).read()
    print("local copy", local, "holds the new token" if new in text else "still holds an old token: delete it (the cluster Secret is the one that counts)")
for p in problems:
    print("NOT DONE:", p)
sys.exit(1 if problems else 0)
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" "${work}/bootstrap.start.json" "${LOCAL_COPY}")" || {
      printf '%s\n' "${report}"
      gitea_die "not done; do not revoke the old token: run rotate again"
    }
    printf '%s\n' "${report}"
    unset NEW_TOKEN
    echo "==> rotated. Do not revoke the old token yet: say 「Gitea 令牌换好了」 in the thread first."
    ;;

  revoked)
    read_secrets
    read_leaked
    py '
old = sorted(leaked_tokens(sys.argv[3]))
admin = secret(sys.argv[1], "gitea_admin_token")
user, clone = secret(sys.argv[2], "username"), secret(sys.argv[2], "password")
bad = 0
for i, token in enumerate(old, 1):
    answer = login(token)
    print("token %d from the public history:" % i, answer, "(refused, as it should be)" if answer == "HTTP 401" else "STILL ACCEPTED or not refused: revoke it")
    bad += answer != "HTTP 401"
now = login(admin) if admin is not None else "missing"
print("gitea-bootstrap:", now)
bad += now != "admin " + ADMIN
listed = repos(admin) if clean(admin) else []
first = listed[0]["name"] if isinstance(listed, list) and listed else None
works = bool(first) and clone is not None and can_read((user, clone), first)
unread = git_reads(user, clone, [r["name"] for r in listed]) if works else []
print("gitea-git-credentials (username %s):" % user, ("CANNOT list over Git HTTP: " + ", ".join(unread)) if unread else "lists all %d repositories over Git HTTP" % len(listed) if works else "CANNOT read a repository as Tekton does")
bad += (not works) or bool(unread)
sys.exit(1 if bad or not old else 0)
' "${work}/bootstrap.json" "${work}/clone.json" "${work}/leaked.yaml" || gitea_die "not done yet: see the lines above"
    echo "==> the leaked tokens are refused; both Secrets work."
    ;;
esac
