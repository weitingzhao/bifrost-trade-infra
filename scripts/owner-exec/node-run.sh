#!/usr/bin/env bash
# owner-exec node tool — version 1 — DRAFT (算力线, 2026-11-18). Not landed in infra.
#
# What it is: a generator. The executor (owner-exec) has no repository checkout, so a card cannot "call" a script in
# git. This script composes the COMPLETE, self-contained command text for one card; the Agent pastes that text into
# an owner_run_command request; the Owner reads it and enters his code. Nothing runs on the cluster from here, and
# nothing is left running afterwards: one Pod, one node, a deadline, deleted at the end. No new credential, no resident
# privileged process, no SSH key.
#
#   node-run.sh render --tier device --node <node> --recipe nvme-smart
#   node-run.sh render --tier host   --node <node> --cmd '<fixed command text>' --pods-file <listing>
#        <listing> = the output of: kubectl get pods -A --field-selector spec.nodeName=<node>,status.phase!=Succeeded,status.phase!=Failed --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name
#   node-run.sh render --tier host   --node gpu-server --recipe <name> [--param K=V ...] --pods-file <listing>
#        named host recipes (law 85, 2026-11-24): the card says recipe=<name> class=<read-only|reversible> and the
#        recipe file's sha256, so the executor can run a read-only one without an Owner code once it trusts the name+hash.
#   node-run.sh hash                       sha256 of the runtime part (cite it on the card)
#   node-run.sh selftest                   renders every case, parses the YAML, runs the refusal tests (no cluster needed)
#
# TIER device  — fixed, named recipes only (no free command). Privileged only so a device node can be opened. No hostPID,
#                hostNetwork, hostIPC, hostPath, chroot, nsenter; no ServiceAccount token. The recipe is read-only by
#                construction (nvme-smart sends two NVMe admin opcodes from a whitelist and never opens a namespace).
# TIER host    — a free command, run in the node's own namespaces (hostPID + nsenter): THE NODE'S ROOT. The card says so
#                in its first line. The command text is the Owner's control (he reads it and enters his code, every card).
#                Owner decision 2026-11-18 (LAW-6): the host tier may be used on a node that runs Trade or IB
#                services. So the tool no longer refuses such a node. Instead it LISTS, in the first lines of the card, the
#                Trade, redis-ib, IB gateway and daemon Pods that run on the node when the card is generated (--pods-file),
#                and prints the list again at run time. D10 is not lifted: no orders, no change to a trading service, nothing
#                done to those Pods, their volumes or their Secrets. The tool keeps one refusal at generation:
#                  - a text tripwire on the command (Trade namespaces, redis-ib, ib-gateway, daemon, Secret directories).
#                    It catches mistakes; it is NOT a barrier: a root command can spell the same thing in a way no regex
#                    sees. The control is the Owner reading the card. Short enough to read on a phone: use the device tier
#                    or a platform action when either will do.
# Not covered: machines outside the cluster (Mac minis, NAS, ubt-k3s-06). A node that is off (gpu-server) is refused with
# "node not Ready": wake it first with the platform's wake action, then run the card.
set -uo pipefail
VERSION=1
IMG='192.168.10.73:30500/bifrost-research@sha256:8cd0b34bbff05e1c6bc21b555e9d196813c484f6d49514583a78def32b4b83c5'  # bifrost-research:0.205.0 (0.183.0's digest left the registry: cards #626-#628 failed on 2026-11-19)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "node-run: $*" >&2; exit 2; }
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi; }   # coreutils on the CI image, shasum on a Mac

# ---- the text tripwire, shared by render and selftest ----
TRIPWIRE='bifrost-(prod|stg|dev)([^a-z0-9-]|$)|redis-ib|ib-gateway|ib:operator|(^|[^a-z0-9-])daemon([^a-z0-9-]|$)|kubernetes\.io~secret|/var/lib/kubelet/pods|/run/secrets|serviceaccount/token'
tripwire_hit() { printf '%s' "$1" | grep -Eio "$TRIPWIRE" | head -1; }

# ---- the runtime part (static; its hash is what a card cites). Variables TIER NODE RECIPE are set above it. ----
runtime() { cat <<'RUNTIME'
NS=bifrost-owner-exec
RUN="node-run-$(date -u +%Y%m%d-%H%M%S)"   # lowercase only: a Pod name is an RFC 1123 label (card #601 died on "T" and "Z")
NAME="$RUN-$(echo "$NODE" | tr -c 'a-z0-9' '-' | sed 's/-*$//')"
[[ "$NAME" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] && [ "${#NAME}" -le 63 ] || { echo "RESULT=FAIL stage=name detail=$NAME is not a valid Pod name"; exit 1; }
cleanup() { kubectl delete pod "$NAME" -n "$NS" --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT
die() { echo "RESULT=FAIL stage=$1 detail=$2"; exit 1; }

# 1. the node must exist and be Ready (a node that is off is refused: wake it first)
ready=$(kubectl get node "$NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
[ "$ready" = True ] || die node-not-ready "$NODE ready=${ready:-missing}"

# 2. host tier only: print which Trade / IB workloads are live on the node right now (information, not a refusal: the Owner decided
#    on 2026-11-18 that the host tier may be used on such nodes, one card at a time, each card read and approved by him).
if [ "$TIER" = host ]; then
  live=$(kubectl get pods -A --field-selector "spec.nodeName=$NODE,status.phase!=Succeeded,status.phase!=Failed" --no-headers -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name 2>/dev/null \
        | awk '$1=="bifrost-prod"||$1=="bifrost-stg"||$1=="bifrost-dev"||$2 ~ /^redis-ib/||$2 ~ /^ib-gateway/||$2 ~ /^daemon/ {print $1"/"$2}' | paste -sd, -)
  echo "live Trade/IB pods on $NODE at run time: ${live:-none}"
fi

# 3. build the Pod. device: no host namespaces at all. host: hostPID + nsenter into PID 1's namespaces.
if [ "$TIER" = device ]; then
  CMD='["python3", "-I", "-c"]'; HOSTPID=false
  ARGS=$(printf '%s\n' "$RECIPE_SCRIPT" | sed 's/^/      /')
else
  CMD='["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--", "/bin/sh", "-c"]'; HOSTPID=true
  ARGS=$(printf '%s\n' "$HOSTCMD" | sed 's/^/      /')
fi
cat <<EOF | kubectl apply -f - >/dev/null || die create-pod "$NAME"
apiVersion: v1
kind: Pod
metadata:
  name: $NAME
  namespace: $NS
  labels: {bifrost.io/purpose: node-run, bifrost.io/node-run-tier: $TIER}
spec:
  nodeName: $NODE
  restartPolicy: Never
  automountServiceAccountToken: false
  hostPID: $HOSTPID
  hostNetwork: false
  hostIPC: false
  activeDeadlineSeconds: ${DEADLINE:-300}
  containers:
  - name: run
    image: $IMG
    imagePullPolicy: IfNotPresent
    command: $CMD
    args:
    - |
$ARGS
    securityContext: {privileged: true, runAsUser: 0}
    resources:
      requests: {cpu: 50m, memory: 32Mi}
      limits: {cpu: "1", memory: 256Mi}
EOF
for _ in $(seq 1 ${WAIT_LOOPS:-150}); do
  phase=$(kubectl get pod "$NAME" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)
  if [ "$phase" = Succeeded ] || [ "$phase" = Failed ]; then break; fi
  sleep 2
done
echo "tier=$TIER node=$NODE phase=${phase:-unknown}"
kubectl logs "$NAME" -n "$NS" 2>&1 | tail -c 1700
[ "$phase" = Succeeded ] || die run "pod ended in phase ${phase:-unknown}"
RUNTIME
}

recipe_script() { case "$1" in
  nvme-smart) cat "$HERE/recipes/nvme_smart.py" ;;
  *) return 1 ;;
esac; }

# Host-tier named recipes (law 85). name -> file, node it may run on, class, allowed parameters.
host_recipe_file() { case "$1" in
  gpu-strata-status)  echo "$HERE/recipes/gpu_strata_status.sh" ;;
  gpu-models)         echo "$HERE/recipes/gpu_models.sh" ;;
  gpu-strata-profile) echo "$HERE/recipes/gpu_strata_profile.sh" ;;
  *) return 1 ;;
esac; }
host_recipe_class() { case "$1" in gpu-strata-status|gpu-models) echo read-only ;; gpu-strata-profile) echo reversible ;; esac; }
host_recipe_node()  { case "$1" in gpu-*) echo gpu-server ;; esac; }
# one line per allowed parameter: NAME regex-of-values
host_recipe_params() { case "$1" in
  gpu-strata-profile) printf 'MODEL ^(iq3|q4)$\nCTX ^(32768|65536|131072|262144)$\n' ;;
esac; }

render() {
  local tier="" node="" recipe="" cmd="" podsfile="" params="" rclass=""
  while [ $# -gt 0 ]; do case "$1" in
    --tier) tier="$2"; shift 2;; --node) node="$2"; shift 2;; --recipe) recipe="$2"; shift 2;; --cmd) cmd="$2"; shift 2;; --pods-file) podsfile="$2"; shift 2;;
    --param) params="$params$2"$'\n'; shift 2;;
    *) die "unknown option $1";; esac; done
  case "$node" in ubt-k3s-0[1-9]|gpu-server) ;; *) die "node must be a cluster node (ubt-k3s-0N or gpu-server): '$node'";; esac
  case "$tier" in
    device)
      [ -z "$cmd" ] || die "tier device takes a recipe, not a free command"
      recipe_script "$recipe" >/dev/null || die "unknown recipe '$recipe' (known: nvme-smart)" ;;
    host)
      if [ -n "$recipe" ]; then
        [ -z "$cmd" ] || die "a host recipe takes no --cmd"
        host_recipe_file "$recipe" >/dev/null || die "unknown host recipe '$recipe' (known: gpu-strata-status, gpu-models, gpu-strata-profile)"
        [ "$(host_recipe_node "$recipe")" = "$node" ] || die "recipe $recipe runs only on $(host_recipe_node "$recipe")"
        rclass=$(host_recipe_class "$recipe")
        local want got k v line
        want=$(host_recipe_params "$recipe" | awk 'NF{print $1}' | sort | paste -sd' ' -)
        got=$(printf '%s' "$params" | awk -F= 'NF{print $1}' | sort | paste -sd' ' -)
        [ "$want" = "$got" ] || die "recipe $recipe needs exactly these parameters: ${want:-none} (got: ${got:-none})"
        while IFS= read -r line; do [ -n "$line" ] || continue
          k=${line%%=*}; v=${line#*=}
          printf '%s' "$v" | grep -Eq "$(host_recipe_params "$recipe" | awk -v k="$k" '$1==k{print $2}')" || die "parameter $k=$v is not allowed for $recipe"
        done <<< "$params"
        cmd="$(printf '%s' "$params" | awk -F= 'NF{printf "%s=%s\n",$1,$2}')
$(cat "$(host_recipe_file "$recipe")")"
      fi
      [ -n "$cmd" ] || die "tier host needs --cmd or --recipe"
      hit=$(tripwire_hit "$cmd"); [ -z "$hit" ] || die "refused: the command text mentions '$hit' (Trade / IB / Secret directories are not for this path; this check is a tripwire, not a barrier)"
      [ -n "$podsfile" ] && [ -r "$podsfile" ] || die "tier host needs --pods-file (the card must list the Trade / IB pods on the node)" ;;
    *) die "tier must be device or host" ;;
  esac
  # The pinned image must still be in the registry, or the card's Pod never starts (2026-11-19,
  # cards #626-#628). NODE_RUN_SKIP_IMAGE_CHECK=1 is for the selftest, which has no registry.
  if [ -z "${NODE_RUN_SKIP_IMAGE_CHECK:-}" ]; then
    local repo digest code
    repo=${IMG#*/}; repo=${repo%%@*}; digest=${IMG#*@}
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 -I \
      -H 'Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
      "http://${IMG%%/*}/v2/$repo/manifests/$digest") || code=none
    [ "$code" = 200 ] || die "the pinned image $IMG is not in the registry (HTTP $code): pin one that is, and keep it in scripts/registry/keepset.py's PINNED_FILES"
  fi
  echo '#!/usr/bin/env bash'
  if [ "$tier" = host ]; then
    echo "# THIS IS THE NODE'S ROOT: the command below runs in the host namespaces of $node (hostPID + nsenter) as root."
    echo "# It can read and change anything on that node, including its disks and the node's own credentials. The command text is the control: read it."
    local live; live=$(awk '$1=="bifrost-prod"||$1=="bifrost-stg"||$1=="bifrost-dev"||$2 ~ /^redis-ib/||$2 ~ /^ib-gateway/||$2 ~ /^daemon/ {print $1"/"$2}' "$podsfile" | paste -sd, -)
    echo "# Trade / IB pods live on $node when this card was generated: ${live:-none}."
    echo "# D10 is not lifted: this card does not place orders, change a trading service, or touch those Pods, their volumes or their Secrets."
  else
    echo "# DEVICE TIER (privileged to open a device node; no host namespaces, no host paths, no token). Recipe $recipe, fixed and read-only."
  fi
  if [ "$tier" = host ] && [ -n "$recipe" ]; then
    echo "# owner-exec node-run v$VERSION tier=$tier node=$node runtime_sha256=$(runtime | sha256) recipe=$recipe class=$rclass recipe_sha256=$(sha256 < "$(host_recipe_file "$recipe")")"
  else
    echo "# owner-exec node-run v$VERSION tier=$tier node=$node runtime_sha256=$(runtime | sha256)"
  fi
  echo "TIER=$tier"; echo "NODE=$node"; echo "DEADLINE=${DEADLINE:-300}"
  echo "IMG='$IMG'"   # 2026-11-19 card #626: the card had no IMG, so the Pod's image was empty
  if [ "$tier" = device ]; then
    echo "read -r -d '' RECIPE_SCRIPT <<'RECIPE_EOF'"; recipe_script "$recipe"; echo "RECIPE_EOF"
  else
    echo "read -r -d '' HOSTCMD <<'HOSTCMD_EOF'"; printf '%s\n' "$cmd"; echo "HOSTCMD_EOF"
  fi
  runtime
}

# ---- tests that need no cluster ----
selftest() {
  export NODE_RUN_SKIP_IMAGE_CHECK=1
  local fails=0 t="$(mktemp -d)"; trap 'rm -rf "$t"' RETURN
  printf 'monitoring node-exporter-x\ndata redis-ib-554d964cb6-bsdc6\nbifrost-prod api-account-x\nbifrost-prod daemon-585fb9d779-bvmx4\nbifrost-stg frontend-y\n' > "$t/pods.txt"
  mkdir -p "$t/bin"; printf '#!/bin/sh\nexit 0\n' > "$t/bin/kubectl"; chmod +x "$t/bin/kubectl"   # a stub: the selftest never talks to a cluster
  ok()   { echo "PASS  $1"; }
  bad()  { echo "FAIL  $1"; fails=$((fails+1)); }
  refuse() { # name, expected-substring, args...
    local name="$1" want="$2"; shift 2
    local out; out=$("$0" render "$@" 2>&1); local rc=$?
    if [ $rc -ne 0 ] && echo "$out" | grep -q -- "$want"; then ok "refused: $name"; else bad "refused: $name (rc=$rc: $(echo "$out" | head -1))"; fi
  }
  # 1. renders parse as bash, and the Pod YAML they would apply parses and has the right shape
  for spec in "device ubt-k3s-05 --recipe nvme-smart" "device gpu-server --recipe nvme-smart" "host ubt-k3s-05 --cmd lsblk --pods-file $t/pods.txt"; do
    set -- $spec; local tier="$1" node="$2"; shift 2
    "$0" render --tier "$tier" --node "$node" "$@" > "$t/card.sh" || { bad "render $spec"; continue; }
    bash -n "$t/card.sh" && ok "render+bash -n: $spec" || bad "bash -n: $spec"
    sed -e 's/^\[ "\$ready" = True \].*$/true/' -e 's/| kubectl apply -f - >\/dev\/null || die create-pod "\$NAME"/> '"${t//\//\\/}"'\/pod.yaml/' \
        -e '/^for _ in /,$d' -e 's/^if \[ "\$TIER" = host \]; then$/if false; then/' "$t/card.sh" > "$t/render.sh"
    sed -i.bak 's/^ready=.*$/ready=True/' "$t/render.sh" 2>/dev/null
    PATH="$t/bin:$PATH" bash "$t/render.sh" >/dev/null 2>&1
    if python3 - "$t/pod.yaml" "$tier" <<'PY'
import sys, yaml, ast
d = yaml.safe_load(open(sys.argv[1])); tier = sys.argv[2]; s = d["spec"]; c = s["containers"][0]
import re
assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", d["metadata"]["name"]) and len(d["metadata"]["name"]) <= 63, "Pod name must be an RFC 1123 label: " + d["metadata"]["name"]
assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", "node-run-20261118T200057Z-ubt-k3s-05") is None   # the shape that killed #601
assert d["metadata"]["namespace"] == "bifrost-owner-exec"
assert s["automountServiceAccountToken"] is False and s["hostNetwork"] is False and s["hostIPC"] is False
assert not s.get("volumes") and not c.get("env") and "hostPath" not in str(d)
assert s["hostPID"] is (tier == "host")
# 2026-11-19, card #626: the rendered card never set IMG, so the Pod's image was empty and the
# card had to be fixed by hand. Positive control: drop the IMG line from render and this fails.
assert c.get("image") and "@sha256:" in c["image"] and "$" not in c["image"], "the Pod needs the pinned image"
assert c["securityContext"]["privileged"] is True
if tier == "device": ast.parse(c["args"][0]); assert c["command"][0] == "python3"
else: assert c["command"][0] == "nsenter"
PY
    then ok "pod shape: $spec"; else bad "pod shape: $spec"; fi
  done
  # 1b. host recipes (law 85, 2026-11-24: 15 of 18 cards on gpu-server that day were reads or reversible profile changes)
  for spec in "gpu-strata-status" "gpu-models" "gpu-strata-profile --param MODEL=iq3 --param CTX=131072"; do
    set -- $spec; local r="$1"; shift
    out=$("$0" render --tier host --node gpu-server --pods-file "$t/pods.txt" --recipe $r "$@" 2>&1) || { bad "host recipe $r: $(echo "$out" | head -1)"; continue; }
    printf '%s\n' "$out" | bash -n && ok "host recipe renders: $r" || bad "host recipe bash -n: $r"
    printf '%s\n' "$out" | grep -q "recipe=$r class=$(host_recipe_class $r) recipe_sha256=" && ok "host recipe header names it: $r" || bad "host recipe header: $r"
  done
  refuse "recipe on the wrong node"   "runs only on"         --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --recipe gpu-models
  refuse "recipe param out of list"   "not allowed"          --tier host --node gpu-server --pods-file "$t/pods.txt" --recipe gpu-strata-profile --param MODEL=iq3 --param CTX=1048576
  refuse "recipe param missing"       "needs exactly"        --tier host --node gpu-server --pods-file "$t/pods.txt" --recipe gpu-strata-profile --param MODEL=q4
  refuse "recipe plus a free command" "takes no --cmd"       --tier host --node gpu-server --pods-file "$t/pods.txt" --recipe gpu-models --cmd ls
  # 2. refusals at render time
  refuse "free command on device tier" "takes a recipe"      --tier device --node ubt-k3s-05 --recipe nvme-smart --cmd 'ls'
  refuse "unknown recipe"             "unknown recipe"       --tier device --node ubt-k3s-05 --recipe format-disk
  refuse "not a cluster node"         "must be a cluster node" --tier device --node mini-50 --recipe nvme-smart
  refuse "host: Trade namespace"      "bifrost-prod"         --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'kubectl -n bifrost-prod get pods'
  refuse "host: redis-ib"             "redis-ib"             --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'ls /var/lib/redis-ib'
  refuse "host: daemon"               "daemon"               --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'systemctl stop daemon'
  refuse "host: kubelet Secret dirs"  "not for this path" --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'ls /var/lib/kubelet/pods/x/volumes/kubernetes.io~secret'
  refuse "host: no command"           "needs --cmd or --recipe"          --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt"
  refuse "host: no pods listing"      "needs --pods-file"    --tier host --node ubt-k3s-05 --cmd lsblk
  # 3. things that must NOT be refused
  out=$("$0" render --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'df -h /; lsblk' 2>&1) && ok "host: an ordinary read passes" || bad "host: ordinary read refused: $out"
  out=$("$0" render --tier host --node ubt-k3s-01 --pods-file "$t/pods.txt" --cmd 'echo daemonize-not-a-word' 2>&1) && ok "tripwire does not fire inside another word" || bad "tripwire fired on a longer word"
  # 4. the host tier lists the Trade / IB pods on the node in the first lines of the card, and does not refuse such a node
  card=$("$0" render --tier host --node ubt-k3s-05 --pods-file "$t/pods.txt" --cmd 'df -h /' 2>&1); rc=$?
  [ $rc -eq 0 ] && ok "host: a node with Trade/IB pods is not refused" || bad "host: refused a node with Trade/IB pods"
  echo "$card" | head -6 | grep -q "NODE'S ROOT" && ok "host: first line says node root" || bad "host: no node-root line"
  echo "$card" | head -6 | grep -q 'redis-ib-554d964cb6-bsdc6' && ok "host: redis-ib is listed in the first lines" || bad "host: redis-ib not listed"
  echo "$card" | head -6 | grep -q 'bifrost-prod/daemon-585fb9d779-bvmx4' && ok "host: daemon is listed in the first lines" || bad "host: daemon not listed"
  echo "$card" | head -6 | grep -q 'bifrost-prod/api-account-x' && ok "host: a bifrost-prod pod is listed" || bad "host: bifrost-prod pod not listed"
  echo "$card" | head -6 | grep -q 'D10 is not lifted' && ok "host: D10 line is on the card" || bad "host: no D10 line"
  echo "$card" | grep -q 'host-refused' && bad "host: the runtime still refuses" || ok "host: the runtime no longer refuses"
  echo "selftest: $fails failure(s)"; [ "$fails" -eq 0 ]
}

case "${1:-}" in
  render) shift; render "$@" ;;
  hash) runtime | sha256 ;;
  selftest) selftest ;;
  *) sed -n 2,34p "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
