#!/usr/bin/env bash
# chief-exam-set.sh — the Owner's steps for the chief of staff's exam set (W-31
# 2.4 chief exam S5; agent-config/work/multi-agent/CUT-chief-exam-2026-10-19.md
# §5, §6 甲). The set is five q*.json that hold the grading keys. It lives on
# this Mac only, never in a repository: an Agent host checks repositories out,
# and a seat reads whatever its user can. platform-api reads the set once, at
# start, from the Secret bifrost-chief-exam, which the overlay patch
# platform-<env>/platform-api-exam-set.patch.yaml mounts at AGENTRT_EXAM_DIR.
#
#   digest                  the set here: its files, their sizes and the sha256
#                           platform-api logs when it loads it (no cluster)
#   check stg|prod          read only: the set here; the Secret's keys, the
#                           sha256 of its data and the one it was put with;
#                           what platform-api said at its start. Exit 0 when
#                           platform-api loaded this set, 3 when not
#   put stg|prod <sha256>   put the set whose sha256 is given into the Secret:
#                           create it, or replace it when it holds another set;
#                           platform-api reads it at its next start. The sha256
#                           is the one the coordinator checked with the
#                           platform's loader on the commit the environment
#                           runs: what the loader alone judges (field types,
#                           each kind's required fields, patterns) is held by it
#
# The set's directory is CHIEF_EXAM_DIR (default below). Every step stops at
# its first error. Nothing prints the set's content or the Secret's data: file
# names, sizes and sha256 only. Written for the macOS system bash (3.2).
set -euo pipefail

export KUBECONFIG=${CHIEF_EXAM_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}
SET_DIR=${CHIEF_EXAM_DIR:-$HOME/agent-work/chief-exam-2026-10-19}
SECRET=bifrost-chief-exam

die() {
  echo "chief-exam-set: $*" >&2
  exit 1
}
say() { echo "==> $*"; }
TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

ns_of() {
  case "${1:-}" in
    stg) echo bifrost-platform-stg ;;
    prod) echo bifrost-platform-prod ;;
    *) die "say stg or prod" ;;
  esac
}

# set_py list | set_py manifest <namespace> <sha256>: reads the set in SET_DIR
# once and checks it as exam.Load and exam.Platform take it, as far as shape
# goes (one each of q1- to q5-<name>.json, regular files; each a question of
# the chief's exam with an id, a class the platform scores and items; each
# item an id of its own and rules; each rule an id and a kind of the closed
# vocabulary; under 512 KiB together). Its patterns are the loader's to judge:
# put takes only the sha256 the coordinator checked with it. list writes
# "<file> <bytes>" lines, then "sha256 <digest>"; manifest writes the Secret
# that holds the set, or nothing when the set read now is not the sha256
# given. The digest is exam.Load's: over the files in name order, each
# "<name>\0<bytes>\0" and its content. Errors name files and ids, never what
# a rule holds.
set_py() {
  python3 -I -c '
import base64, fnmatch, hashlib, json, os, re, sys

KINDS = {"max_lines", "mentions_all", "known_ids_only", "clause_forbid", "clause_require", "clause_each_require",
         "pace_near", "time_near", "require_any", "forbid_any", "alert", "protocol_lines", "plan_parses", "card",
         "section_order", "cjk_ratio"}
CLASSES = {"exam-brief", "exam-card", "exam-alert", "exam-refuse", "exam-handover"}
SAFE = re.compile(r"[A-Za-z0-9._-]{1,40}")

def die(m):
    print("chief-exam-set: " + m, file=sys.stderr)
    sys.exit(1)

def name_of(v):
    return v if isinstance(v, str) and SAFE.fullmatch(v) else "(an id)"

mode, d = sys.argv[1], sys.argv[2]
if not os.path.isdir(d):
    die(d + " is not a directory: there is no set here")
names = sorted(n for n in os.listdir(d) if fnmatch.fnmatchcase(n, "q*.json"))
if [n.split("-", 1)[0] for n in names] != ["q1", "q2", "q3", "q4", "q5"] or not all(
        re.fullmatch(r"q[1-5]-[a-z0-9-]+\.json", n) for n in names):
    die("%s holds %d q*.json (%s); a set is one each of q1- to q5-<name>.json" % (d, len(names), ", ".join(names) or "none"))
h = hashlib.sha256()
files = []
items = set()
for n in names:
    p = os.path.join(d, n)
    if os.path.islink(p) or not os.path.isfile(p):
        die(n + " is not a regular file")
    with open(p, "rb") as f:
        raw = f.read()
    try:
        q = json.loads(raw)
    except json.JSONDecodeError as e:
        die("%s is not JSON (line %d)" % (n, e.lineno))
    except UnicodeDecodeError:
        die(n + " is not UTF-8")
    if not isinstance(q, dict) or q.get("exam") != "chief_of_staff":
        die(n + " is not a question of the chief of staff exam")
    if not isinstance(q.get("question"), str) or not q["question"]:
        die(n + ": the question has no id")
    if q.get("class") not in CLASSES:
        die(n + ": its class is not one the platform scores the chief exam under")
    if not isinstance(q.get("items"), list) or not q["items"]:
        die(n + ": the question has no items")
    for it in q["items"]:
        if not isinstance(it, dict):
            die(n + ": an item is not an object")
        iid = it.get("id")
        if not isinstance(iid, str) or not iid or iid in items:
            die("%s: item %s has no id or comes twice" % (n, name_of(iid)))
        items.add(iid)
        rules = it.get("rules")
        if not isinstance(rules, list) or not rules:
            die("%s: item %s has no rule" % (n, name_of(iid)))
        for r in rules:
            if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"]:
                die("%s: item %s has a rule without an id" % (n, name_of(iid)))
            if r.get("kind") not in KINDS:
                die("%s: item %s rule %s is of a kind the platform does not grade" % (n, name_of(iid), name_of(r["id"])))
    h.update(("%s\0%d\0" % (n, len(raw))).encode())
    h.update(raw)
    files.append((n, raw))
total = sum(len(raw) for _, raw in files)
if total > 512 * 1024:
    die("the set is %d bytes; this Secret stays under 512 KiB" % total)
digest = h.hexdigest()
if mode == "list":
    for n, raw in files:
        print("%s %d" % (n, len(raw)))
    print("sha256 " + digest)
    sys.exit(0)
if digest != sys.argv[4]:
    die("the set read now is sha256 %s, not %s: nothing was sent" % (digest, sys.argv[4]))
json.dump({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
           "metadata": {"name": "bifrost-chief-exam", "namespace": sys.argv[3],
                        "labels": {"app.kubernetes.io/part-of": "bifrost-platform",
                                   "app.kubernetes.io/component": "chief-exam"},
                        "annotations": {"bifrost.io/exam-set-sha256": digest}},
           "data": {n: base64.b64encode(raw).decode() for n, raw in files}}, sys.stdout)
' "$@"
}

# secret_read <namespace>: S_PRESENT (yes / no), S_SHA (the sha256 the Secret
# was put with), S_DATA (the sha256 of its data, computed here as exam.Load
# computes it over the keys it reads) and S_KEYS (its keys, one a line). The
# data goes from kubectl into this process and nowhere else. Non-zero when
# the Secret cannot be read.
secret_read() {
  local out
  S_PRESENT=no S_SHA="" S_DATA="" S_KEYS=""
  out=$(kubectl -n "$1" get secret "$SECRET" --ignore-not-found -o json 2> /dev/null | python3 -I -c '
import base64, fnmatch, hashlib, json, sys
raw = sys.stdin.read()
if not raw.strip():
    print("no")
    sys.exit(0)
s = json.loads(raw)
data = s.get("data") or {}
h = hashlib.sha256()
for k in sorted(k for k in data if fnmatch.fnmatchcase(k, "q*.json")):
    b = base64.b64decode(data[k])
    h.update(("%s\0%d\0" % (k, len(b))).encode())
    h.update(b)
print("yes")
print(((s.get("metadata") or {}).get("annotations") or {}).get("bifrost.io/exam-set-sha256", ""))
print(h.hexdigest() if data else "")
for k in sorted(data):
    print(k)
') || return 1
  S_PRESENT=$(echo "$out" | sed -n 1p)
  [ "$S_PRESENT" = yes ] || return 0
  S_SHA=$(echo "$out" | sed -n 2p)
  S_DATA=$(echo "$out" | sed -n 3p)
  S_KEYS=$(echo "$out" | sed -n '4,$p')
}

keys_line() { echo $1; }

# kubectl_write <create|replace> <namespace> <sha256>: sends the Secret that
# holds the set (set_py manifest) to kubectl. kubectl's answer never reaches
# a shell variable, the terminal or a file: an API or admission error may
# quote the request it refused, the set's content among it (review 446). A
# local filter prints the first of a fixed list of words found in it, or
# says it is not shown. Non-zero when the write failed.
kubectl_write() {
  set_py manifest "$SET_DIR" "$2" "$3" | kubectl "$1" -f - 2>&1 | python3 -I -c '
import sys
t = sys.stdin.read()
for w in ("created", "replaced", "AlreadyExists", "NotFound", "Forbidden", "Unauthorized", "Conflict",
          "RequestEntityTooLarge", "Too long", "Invalid", "admission webhook", "no objects passed",
          "Unable to connect", "connection refused", "i/o timeout", "TLS handshake"):
    if w in t:
        print(w)
        break
else:
    print("kubectl said something not shown here: it may quote the request")
'
}

next_steps() {
  say "platform-api reads the set when it starts: a pod that started with the overlay patch platform-api-exam-set.patch.yaml before this Secret held this set needs one restart"
  say "then: bash $0 check $1"
}

step_digest() {
  set_py list "$SET_DIR"
}

step_put() {
  local env=${1:-} want=${2:-} ns list sha names verb ans out
  ns=$(ns_of "$env")
  echo "$want" | grep -Eq '^[0-9a-f]{64}$' ||
    die "say the set's sha256 after $env: the one the coordinator gives you, checked with the platform's loader on the commit $env runs (digest only shows the set here); nothing changed"
  list=$(set_py list "$SET_DIR")
  sha=$(echo "$list" | sed -n 's/^sha256 //p')
  names=$(echo "$list" | sed '$d' | cut -d' ' -f1)
  say "the set in $SET_DIR:"
  echo "$list"
  [ "$sha" = "$want" ] || die "the set here is sha256 $sha, not the $want you were given; nothing changed"
  kubectl get namespace "$ns" -o name > /dev/null || die "cannot read the namespace $ns with KUBECONFIG=$KUBECONFIG; nothing changed"
  for verb in create update; do
    ans=$(kubectl auth can-i "$verb" secrets -n "$ns" 2> /dev/null || true)
    [ "$ans" = yes ] || die "KUBECONFIG=$KUBECONFIG cannot $verb Secrets in $ns: this step is the Owner's, with his admin kubeconfig; nothing changed"
  done
  secret_read "$ns" || die "cannot read $ns/$SECRET; nothing changed"
  if [ "$S_PRESENT" = yes ]; then
    say "$ns/$SECRET is there: data sha256 ${S_DATA:-(none)}, put with ${S_SHA:-(none)}; keys: $(keys_line "$S_KEYS")"
    if [ "$S_DATA" = "$want" ] && [ "$S_SHA" = "$want" ] && [ "$S_KEYS" = "$names" ]; then
      say "it holds this set already; nothing changed"
      next_steps "$env"
      return 0
    fi
    out=$(kubectl_write replace "$ns" "$want") || die "$ns/$SECRET was not replaced (kubectl: $out); run: bash $0 check $env"
  else
    out=$(kubectl_write create "$ns" "$want") || die "$ns/$SECRET was not created (kubectl: $out); run: bash $0 check $env"
  fi
  say "kubectl: $out"
  secret_read "$ns" || die "cannot read $ns/$SECRET back"
  if [ "$S_PRESENT" != yes ] || [ "$S_DATA" != "$want" ] || [ "$S_SHA" != "$want" ] || [ "$S_KEYS" != "$names" ]; then
    die "$ns/$SECRET does not read back as this set (data sha256 ${S_DATA:-none}, put with ${S_SHA:-none}; keys: $(keys_line "$S_KEYS"))"
  fi
  say "$ns/$SECRET holds the set: sha256 $want"
  next_steps "$env"
}

step_check() {
  local env=${1:-} ns list sha="" names="" line loaded ready=yes
  ns=$(ns_of "$env")
  if list=$(set_py list "$SET_DIR" 2> "$TMPD/set.err"); then
    sha=$(echo "$list" | sed -n 's/^sha256 //p')
    names=$(echo "$list" | sed '$d' | cut -d' ' -f1)
    say "the set in $SET_DIR:"
    echo "$list"
  else
    say "no set here: $(cat "$TMPD/set.err")"
    ready=no
  fi
  if ! secret_read "$ns"; then
    say "$ns/$SECRET: cannot read it with KUBECONFIG=$KUBECONFIG (the Owner's admin kubeconfig can)"
  elif [ "$S_PRESENT" = no ]; then
    say "$ns/$SECRET: not there"
    ready=no
  else
    say "$ns/$SECRET: data sha256 ${S_DATA:-(none)}, put with ${S_SHA:-(none)}; keys: $(keys_line "$S_KEYS")"
    if [ -n "$sha" ] && { [ "$S_DATA" != "$sha" ] || [ "$S_KEYS" != "$names" ]; }; then
      say "$ns/$SECRET holds another set than the one here"
      ready=no
    fi
  fi
  # The set is read once, at start: its line is among the first of the log.
  kubectl -n "$ns" logs deploy/platform-api --limit-bytes=4000000 > "$TMPD/log" 2> "$TMPD/log.err" ||
    die "cannot read platform-api's log in $ns: $(head -1 "$TMPD/log.err" | cut -c1-200)"
  line=$(grep -E 'agentrt: (exam set loaded|the exam set did not load|AGENTRT_EXAM_DIR is not set)' "$TMPD/log" | tail -1 || true)
  loaded=$(echo "$line" | sed -n 's/.*sha256=\([0-9a-f]\{64\}\).*/\1/p')
  if [ -z "$line" ]; then
    say "platform-api in $ns: no exam line in its log since it started"
    ready=no
  elif [ -n "$loaded" ]; then
    say "platform-api in $ns loaded a set: sha256 $loaded"
    [ "$loaded" = "$sha" ] || {
      say "that is not the set here"
      ready=no
    }
  else
    say "platform-api in $ns: $(echo "$line" | sed 's/.*agentrt: //')"
    ready=no
  fi
  if [ "$ready" = yes ]; then
    say "ready: platform-api in $ns grades with the set here (sha256 $sha)"
    return 0
  fi
  say "not ready"
  return 3
}

step=${1:-}
if [ -z "$step" ]; then
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
shift
case "$step" in
  digest | check | put) ;;
  *) die "unknown step: $step" ;;
esac
"step_$step" "$@"
