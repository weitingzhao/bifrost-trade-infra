#!/usr/bin/env bash
# owner-exec, PROD: the one time the Owner sits at the computer for it.
#
#   bash scripts/owner-exec/enroll.sh
#
# Run it in your own Terminal window, not in a terminal an agent can read: a
# QR code holding the authenticator seed is drawn on screen for a moment.
#
# What it does, in order. It stops at the first thing that is not right, and
# says what it had created by then.
#   1. Server dry-run of every cluster-wide object. Nothing is created if any fails.
#   2. Namespace bifrost-owner-exec, the runner's identity, its NetworkPolicy.
#   3. The seed: made here, sent straight into a Secret, never written to disk.
#      You scan the QR code with your authenticator app and type the 6 digits
#      it shows; the screen and scrollback are then cleared.
#   4. The admission policy that keeps the runner's identity out of Trade, and
#      proof: dry-runs as the runner that must be refused, and one that must pass.
#   5. The runner itself; waits until it is ready.
#   6. The admission policy that keeps everyone else out of the namespace, and
#      proof. If the runner cannot restart under it, that policy's binding is
#      removed again and the script says so.
#   7. One health call through https://ops.bifrost.lan.
#
# Safe to run again: existing objects are updated in place, and an existing
# seed is kept unless you answer "replace".
#
# The dry-runs in steps 4 and 6 name Trade namespaces and redis-ib. They are
# --dry-run=server requests made as the runner's identity that the API server
# is expected to refuse; nothing is stored and no Trade workload is contacted.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KCFG="${OWNER_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
NS=bifrost-owner-exec
RUNNER="system:serviceaccount:${NS}:owner-exec"
HOST="${OWNER_EXEC_HOST:-ops.bifrost.lan}"

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf '\nSTOPPED: %s\n' "$*" >&2; exit 1; }
k()    { kubectl --kubeconfig "$KCFG" "$@"; }

for tool in kubectl python3 qrencode curl; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed (qrencode: brew install qrencode)"
done
[[ -r "$KCFG" ]] || die "admin kubeconfig not readable at $KCFG (set OWNER_KUBECONFIG)"
[[ -t 0 && -t 1 ]] || die "run this in an interactive terminal"
k auth can-i '*' '*' --all-namespaces >/dev/null 2>&1 || die "this kubeconfig is not a cluster admin"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The image PROD's platform-api runs, by digest. It must already carry owner-exec.
IMAGE="$(k -n bifrost-platform-prod get deploy platform-api -o jsonpath='{.spec.template.spec.containers[0].image}')"
[[ "$IMAGE" == *@sha256:* ]] || die "PROD platform-api is not pinned by digest: $IMAGE"
k -n bifrost-platform-prod exec deploy/platform-api -- sh -c 'command -v owner-exec && command -v kubectl && command -v bash' >/dev/null 2>&1 \
  || die "PROD's platform-api image has no owner-exec / kubectl / bash yet: release platform to PROD first"
say "runner image: $IMAGE"

kubectl kustomize "$ROOT/k8s/owner-exec" | sed "s|OWNER_EXEC_IMAGE|$IMAGE|g" > "$WORK/all.yaml"
python3 - "$WORK" <<'PY'
import sys, pathlib, yaml
work = pathlib.Path(sys.argv[1])
docs = [d for d in yaml.safe_load_all((work / "all.yaml").read_text()) if d]
def pick(pred): return [d for d in docs if pred(d)]
def dump(name, items): (work / name).write_text(yaml.safe_dump_all(items, sort_keys=False))
kind = lambda d: d["kind"]; name = lambda d: d["metadata"]["name"]
vap = lambda d: kind(d).startswith("ValidatingAdmissionPolicy")
dump("1-base.yaml", pick(lambda d: kind(d) in ("Namespace", "ServiceAccount", "ClusterRole", "ClusterRoleBinding", "NetworkPolicy")))
dump("2-no-trade.yaml", pick(lambda d: vap(d) and name(d) == "bifrost-owner-exec-no-trade"))
dump("3-runner.yaml", pick(lambda d: kind(d) in ("Deployment", "Service", "IngressRoute")))
dump("4-namespace-guard.yaml", pick(lambda d: vap(d) and name(d) == "bifrost-owner-exec-namespace"))
dump("0-cluster-wide.yaml", pick(lambda d: kind(d) in ("Namespace", "ClusterRole", "ClusterRoleBinding") or vap(d)))
assert sum(len(list(yaml.safe_load_all((work / f).read_text()))) for f in ("1-base.yaml", "2-no-trade.yaml", "3-runner.yaml", "4-namespace-guard.yaml")) == len(docs), "a manifest was left out"
PY

say "1/7 server dry-run of the cluster-wide objects (nothing is created yet)"
k apply --dry-run=server -f "$WORK/0-cluster-wide.yaml" || die "the API server refused a manifest in dry-run; nothing was created"

say "2/7 namespace, identity, network policy"
k apply -f "$WORK/1-base.yaml"

say "3/7 authenticator seed"
make_seed=yes
if k -n "$NS" get secret owner-exec-seed >/dev/null 2>&1; then
  printf 'A seed already exists. Type "replace" to make a new one (your app entry must then be re-scanned), anything else keeps it: '
  read -r answer
  [[ "$answer" == replace ]] || make_seed=no
fi
if [[ "$make_seed" == yes ]]; then
  SEED="$(python3 -c 'import secrets,base64; print(base64.b32encode(secrets.token_bytes(20)).decode())')"
  printf %s "$SEED" | k -n "$NS" create secret generic owner-exec-seed --from-file=seed=/dev/stdin --dry-run=client -o yaml | k apply -f - >/dev/null
  clear
  printf 'Scan this with your authenticator app (it will show as "Bifrost: owner-exec").\n\n'
  printf 'otpauth://totp/Bifrost:owner-exec?secret=%s&issuer=Bifrost' "$SEED" | qrencode -t ANSIUTF8
  ok=no
  for attempt in 1 2 3; do
    printf '\nType the 6 digits the app shows now: '
    read -r CODE
    if printf '%s\n%s\n' "$SEED" "$CODE" | python3 -c '
import sys, hmac, hashlib, base64, struct, time
seed, code = sys.stdin.read().split()
key = base64.b32decode(seed)
def at(step):
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 15
    return "%06d" % ((struct.unpack(">I", mac[off:off+4])[0] & 0x7fffffff) % 1000000)
now = int(time.time()) // 30
sys.exit(0 if code in {at(now - 1), at(now), at(now + 1)} else 1)
'; then ok=yes; break; fi
    printf 'That code does not match. Check the phone clock is on automatic time and try the next code.\n'
  done
  unset SEED CODE
  clear; printf '\033[3J'
  if [[ "$ok" != yes ]]; then
    k -n "$NS" delete secret owner-exec-seed >/dev/null
    die "the app's code never matched; the seed was deleted again. Created so far: namespace, identity, network policy. Run the script again."
  fi
  say "seed stored and confirmed against your app; screen cleared"
else
  say "kept the existing seed"
fi

# as_runner <expect: refused|allowed> <description> <kubectl args...>
as_runner() {
  local expect="$1" what="$2"; shift 2
  local out rc=0
  out="$(k --as="$RUNNER" "$@" --dry-run=server 2>&1)" || rc=$?
  if [[ "$expect" == refused ]]; then
    [[ $rc -ne 0 && "$out" == *"ValidatingAdmissionPolicy"* ]] && { printf '  refused, as it must be: %s\n' "$what"; return 0; }
    printf '  NOT refused by the policy: %s\n    %s\n' "$what" "$out"; return 1
  fi
  [[ $rc -eq 0 ]] && { printf '  allowed, as it must be: %s\n' "$what"; return 0; }
  printf '  refused but should pass: %s\n    %s\n' "$what" "$out"; return 1
}

say "4/7 keep the runner's identity out of Trade"
k apply --dry-run=server -f "$WORK/2-no-trade.yaml" >/dev/null || die "the no-trade policy failed dry-run. Created so far: namespace, identity, network policy, seed. The runner is NOT started."
k apply -f "$WORK/2-no-trade.yaml"
proved=no
for wait in 2 4 6 8 10; do   # a new policy takes a few seconds to be enforced
  sleep "$wait"
  if as_runner refused "create in bifrost-prod" -n bifrost-prod create configmap owner-exec-probe >/dev/null 2>&1; then proved=yes; break; fi
done
[[ "$proved" == yes ]] || die "the no-trade policy is not being enforced after 30 seconds. The runner is NOT started. Remove with: kubectl delete -f k8s/owner-exec/admission.yaml"
fail=0
as_runner refused "create in bifrost-prod"            -n bifrost-prod create configmap owner-exec-probe || fail=1
as_runner refused "create in bifrost-stg"             -n bifrost-stg  create configmap owner-exec-probe || fail=1
as_runner refused "create in bifrost-dev"             -n bifrost-dev  create configmap owner-exec-probe || fail=1
as_runner refused "scale Deployment daemon"           -n bifrost-stg  scale deployment daemon --replicas=0 || fail=1
as_runner refused "create a Deployment named daemon"  -n default create deployment daemon --image=registry.k8s.io/pause:3.9 || fail=1
as_runner refused "write redis-ib in data"            -n data create configmap redis-ib-owner-exec-probe || fail=1
as_runner refused "write ib-gateway in data"          -n data create configmap ib-gateway-owner-exec-probe || fail=1
as_runner allowed "an ordinary write elsewhere (positive control)" -n default create configmap owner-exec-probe || fail=1
[[ $fail -eq 0 ]] || die "the no-trade policy does not behave as written (see above). The runner is NOT started."

say "5/7 the runner"
k apply --dry-run=server -f "$WORK/3-runner.yaml" >/dev/null || die "the runner's manifests failed dry-run; it is not started."
k apply -f "$WORK/3-runner.yaml"
k -n "$NS" rollout status deploy/owner-exec --timeout=180s || die "the runner did not become ready: kubectl -n $NS describe pod; kubectl -n $NS logs deploy/owner-exec -c runner"

say "6/7 keep everyone else out of the namespace"
k apply --dry-run=server -f "$WORK/4-namespace-guard.yaml" >/dev/null || die "the namespace policy failed dry-run. The runner is up without it."
k apply -f "$WORK/4-namespace-guard.yaml"
sleep 10
guard_ok=yes
out="$(k --as=system:serviceaccount:cicd:argocd-application-controller -n "$NS" create configmap owner-exec-probe --dry-run=server 2>&1)" && guard_ok=no
[[ "$out" == *"ValidatingAdmissionPolicy"* ]] || guard_ok=no
if [[ "$guard_ok" == yes ]]; then
  printf '  refused, as it must be: Argo CD writing into the namespace\n'
  k -n "$NS" rollout restart deploy/owner-exec >/dev/null
  k -n "$NS" rollout status deploy/owner-exec --timeout=180s || guard_ok=no
fi
if [[ "$guard_ok" != yes ]]; then
  k delete validatingadmissionpolicybinding bifrost-owner-exec-namespace >/dev/null 2>&1 || true
  k -n "$NS" rollout status deploy/owner-exec --timeout=180s || true
  die "the namespace policy did not behave (it must refuse Argo CD and still let the runner restart). Its binding was removed again; the runner is up WITHOUT that guard. Tell the agent: $out"
fi

say "7/7 health through https://$HOST"
sleep 5
body="$(curl -sk -m 10 "https://$HOST/api/owner-exec/health" || true)"
[[ "$body" == *'"ok":true'* ]] || die "no healthy answer through https://$HOST/api/owner-exec/health (got: ${body:-nothing}). The runner is up; the route is not."

cat <<DONE

Done. owner-exec is running in $NS.
  - Codes are accepted from about 90 seconds after its last start.
  - Next: on your phone, open a harmless test card (an echo) on https://$HOST,
    type the code from your app, press "Approve and run".
  - To remove everything: kubectl --kubeconfig <admin> delete -k k8s/owner-exec
    (then delete the entry in your authenticator app).
DONE
