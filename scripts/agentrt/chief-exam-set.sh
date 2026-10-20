#!/usr/bin/env bash
# chief-exam-set.sh — the Owner's steps for the chief of staff's exam set (W-31
# 2.4 chief exam S5; agent-config/work/multi-agent/CUT-chief-exam-2026-10-19.md
# §5, §6 甲). The set is five q*.json that hold the grading keys. It lives on
# this Mac only, never in a repository: an Agent host checks repositories out,
# and a seat reads whatever its user can. platform-api reads the set once, at
# start, from the Secret bifrost-chief-exam, which the overlay patch
# platform-<env>/platform-api-exam-set.patch.yaml mounts at AGENTRT_EXAM_DIR.
#
#   digest          the set here: its files, their sizes and the sha256 that
#                   platform-api logs when it loads the set (no cluster)
#   check stg|prod  read only: the set here; the Secret's keys and the sha256
#                   it was put with; what platform-api said at its start.
#                   Exit 0 when platform-api loaded this set, 3 when not
#   put stg|prod    check the set, then create the Secret, or replace it when
#                   it holds another set; platform-api reads it at its next
#                   start
#
# The set's directory is CHIEF_EXAM_DIR (default below). Every step stops at
# its first error. Nothing prints the set's content or the Secret's data: file
# names, sizes and the sha256 only. Written for the macOS system bash (3.2).
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

# set_py <list|manifest> [namespace]: checks the set in SET_DIR (one each of
# q1- to q5-<name>.json, regular files, JSON questions of the chief's exam,
# under 512 KiB together) and writes its list ("<file> <bytes>" lines, then
# "sha256 <digest>") or the Secret that holds it. The digest is exam.Load's:
# over the files in name order, each "<name>\0<bytes>\0" and its content.
set_py() {
  python3 -I -c '
import base64, fnmatch, hashlib, json, os, re, sys

def die(m):
    print("chief-exam-set: " + m, file=sys.stderr)
    sys.exit(1)

mode, d = sys.argv[1], sys.argv[2]
if not os.path.isdir(d):
    die(d + " is not a directory: there is no set here")
names = sorted(n for n in os.listdir(d) if fnmatch.fnmatchcase(n, "q*.json"))
if [n.split("-", 1)[0] for n in names] != ["q1", "q2", "q3", "q4", "q5"] or not all(
        re.fullmatch(r"q[1-5]-[a-z0-9-]+\.json", n) for n in names):
    die("%s holds %d q*.json (%s); a set is one each of q1- to q5-<name>.json" % (d, len(names), ", ".join(names) or "none"))
h = hashlib.sha256()
files = []
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
    if not isinstance(q, dict) or q.get("exam") != "chief_of_staff" or not q.get("items"):
        die(n + " is not a question of the chief of staff exam (its exam, its items)")
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
else:
    json.dump({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
               "metadata": {"name": "bifrost-chief-exam", "namespace": sys.argv[3],
                            "labels": {"app.kubernetes.io/part-of": "bifrost-platform",
                                       "app.kubernetes.io/component": "chief-exam"},
                            "annotations": {"bifrost.io/exam-set-sha256": digest}},
               "data": {n: base64.b64encode(raw).decode() for n, raw in files}}, sys.stdout)
' "$@"
}

# secret_read <namespace>: S_PRESENT (yes / no), S_SHA (the sha256 it was put
# with) and S_KEYS (its keys, one a line); never its data. Non-zero when the
# Secret cannot be read.
secret_read() {
  local name
  S_PRESENT=no S_SHA="" S_KEYS=""
  name=$(kubectl -n "$1" get secret "$SECRET" --ignore-not-found -o name) || return 1
  [ -n "$name" ] || return 0
  S_PRESENT=yes
  S_SHA=$(kubectl -n "$1" get secret "$SECRET" -o 'jsonpath={.metadata.annotations.bifrost\.io/exam-set-sha256}') || return 1
  S_KEYS=$(kubectl -n "$1" get secret "$SECRET" -o 'go-template={{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}') || return 1
}

keys_line() { echo $1; }

next_steps() {
  say "platform-api reads the set when it starts: a pod that started with the overlay patch platform-api-exam-set.patch.yaml before this Secret existed needs one restart"
  say "then: bash $0 check $1"
}

step_digest() {
  set_py list "$SET_DIR"
}

step_put() {
  local env=${1:-} ns list sha names verb ans
  ns=$(ns_of "$env")
  list=$(set_py list "$SET_DIR")
  sha=$(echo "$list" | sed -n 's/^sha256 //p')
  names=$(echo "$list" | sed '$d' | cut -d' ' -f1)
  say "the set in $SET_DIR:"
  echo "$list"
  kubectl get namespace "$ns" -o name > /dev/null || die "cannot read the namespace $ns with KUBECONFIG=$KUBECONFIG; nothing changed"
  for verb in create update; do
    ans=$(kubectl auth can-i "$verb" secrets -n "$ns" 2> /dev/null || true)
    [ "$ans" = yes ] || die "KUBECONFIG=$KUBECONFIG cannot $verb Secrets in $ns: this step is the Owner's, with his admin kubeconfig; nothing changed"
  done
  secret_read "$ns" || die "cannot read $ns/$SECRET; nothing changed"
  if [ "$S_PRESENT" = yes ]; then
    say "$ns/$SECRET is there, put with sha256 ${S_SHA:-(none)}; keys: $(keys_line "$S_KEYS")"
    if [ "$S_SHA" = "$sha" ] && [ "$S_KEYS" = "$names" ]; then
      say "it holds this set already; nothing changed"
      next_steps "$env"
      return 0
    fi
    set_py manifest "$SET_DIR" "$ns" | kubectl replace -f - || die "$ns/$SECRET was not replaced (see above)"
  else
    set_py manifest "$SET_DIR" "$ns" | kubectl create -f - || die "$ns/$SECRET was not created (see above)"
  fi
  secret_read "$ns" || die "cannot read $ns/$SECRET back"
  if [ "$S_PRESENT" != yes ] || [ "$S_SHA" != "$sha" ] || [ "$S_KEYS" != "$names" ]; then
    die "$ns/$SECRET does not read back as this set (sha256 ${S_SHA:-none}; keys: $(keys_line "$S_KEYS"))"
  fi
  say "$ns/$SECRET holds the set: sha256 $sha"
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
  if ! secret_read "$ns" 2> /dev/null; then
    say "$ns/$SECRET: cannot read it with KUBECONFIG=$KUBECONFIG (the Owner's admin kubeconfig can)"
  elif [ "$S_PRESENT" = no ]; then
    say "$ns/$SECRET: not there"
    ready=no
  else
    say "$ns/$SECRET: put with sha256 ${S_SHA:-(none)}; keys: $(keys_line "$S_KEYS")"
    if [ -n "$sha" ] && { [ "$S_SHA" != "$sha" ] || [ "$S_KEYS" != "$names" ]; }; then
      say "$ns/$SECRET holds another set than the one here"
      ready=no
    fi
  fi
  # The set is read once, at start: its line is among the first of the log.
  kubectl -n "$ns" logs deploy/platform-api --limit-bytes=4000000 > "$TMPD/log" 2> "$TMPD/log.err" ||
    die "cannot read platform-api's log in $ns: $(head -1 "$TMPD/log.err")"
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
  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
shift
case "$step" in
  digest | check | put) ;;
  *) die "unknown step: $step" ;;
esac
"step_$step" "$@"
