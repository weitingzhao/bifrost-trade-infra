#!/usr/bin/env bash
# TD-21 review after the first US trading session on the per-env redis-ib users (plugin 0.3.0,
# switched 2026-10-02): DEV and STG authenticate as trade-dev / trade-stg, PROD alone as trade-prod.
# Read-only: CLIENT LIST, ACL LOG and Loki. Never prints a password: the admin password is read from
# the plugin checkout's .env and handed to redis-cli on stdin, as scripts/redis-ib-env-users.sh does.
#
#   scripts/release/td21_redis_ib_review.sh [since-ISO-UTC]     (default: 2026-10-05T13:00:00Z)
#
# PASS when all of these hold (the script prints each and a verdict):
#   1. Connections: every bifrost-dev pod is trade-dev, every bifrost-stg pod trade-stg, only
#      bifrost-prod pods use trade-prod; no Trade pod authenticates as ib-gateway / platform / default.
#   2. ACL LOG, trade-dev / trade-stg, since the given time: no "key" or "channel" refusal, and no
#      "command" refusal other than srem / hdel / del (POST /quotes/cleanup on a DEV / STG Live page
#      trying to drop on-demand symbols from the shared set -- the ACL doing its job; listed apart).
#   3. Gateway (Loki, data/ib-gateway): no "refused op" line (a DEV / STG process asked for
#      disconnect_all / reconnect_all on its env stream).
#   4. api in bifrost-dev / bifrost-stg (Loki): no NOPERM line other than the /quotes/cleanup one.
# The ACL LOG keeps the newest 128 entries (acllog-max-len): when it is full with entries all newer
# than the window start, the oldest refusals are gone and the review FAILs as unreadable.
# Exit 0 PASS, 1 FAIL, 2 could not read.
set -euo pipefail

SINCE="${1:-2026-10-05T13:00:00Z}"
PLUGIN="${PLUGIN:-$HOME/Desktop/stocks/bifrost-platform-plugin}"
ENV_FILE="${ENV_FILE:-$PLUGIN/.env}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE (REDIS_IB_GATEWAY_PASS)" >&2; exit 2; }

admin() {  # redis-cli in the redis-ib pod as ib-gateway; the password goes in on stdin
  local pw
  pw="$(sed -n 's/^REDIS_IB_GATEWAY_PASS=//p' "$ENV_FILE" | head -1 | sed 's/^"//; s/"$//')"
  [[ -n "$pw" ]] || { echo "REDIS_IB_GATEWAY_PASS not set in $ENV_FILE" >&2; exit 2; }
  kubectl -n data exec -i deploy/redis-ib -- \
    sh -c 'REDISCLI_AUTH="$(cat)" exec redis-cli --no-auth-warning --user ib-gateway "$@"' sh "$@" <<<"$pw"
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
kubectl get pods -A --field-selector=status.phase=Running -o json >"$WORK/pods.json"
admin CLIENT LIST >"$WORK/clients.txt"
admin --json ACL LOG 128 >"$WORK/acllog.json"
admin INFO server | tr -d '\r' | grep -E '^(redis_version|uptime_in_seconds):' >"$WORK/info.txt"

loki() {  # instant LogQL over [since, now]
  python3 - "$1" "$SINCE" <<'PY'
import json, subprocess, sys, time, urllib.parse
from datetime import datetime
q, since = sys.argv[1], sys.argv[2]
secs = max(60, int(time.time() - datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()))
logql = q.replace("[RANGE]", f"[{secs}s]")
path = ("/api/v1/namespaces/monitoring/services/loki:3100/proxy/loki/api/v1/query?"
        + urllib.parse.urlencode({"query": logql, "time": str(int(time.time() * 1e9))}))
p = subprocess.run(["kubectl", "get", "--raw", path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
if p.returncode != 0:
    print("UNAVAILABLE " + p.stderr.strip()[:200]); sys.exit(0)
rows = json.loads(p.stdout)["data"]["result"]
print(json.dumps({",".join(f"{k}={v}" for k, v in sorted(r["metric"].items())): int(float(r["value"][1])) for r in rows}))
PY
}
loki 'sum by (namespace, app) (count_over_time({namespace="data", app="ib-gateway"} |= "refused op" [RANGE]))' >"$WORK/gw.txt"
loki 'sum by (namespace, app) (count_over_time({namespace=~"bifrost-(dev|stg)"} |~ "NOPERM|No permissions" [RANGE]))' >"$WORK/noperm.txt"
loki 'sum by (namespace, app) (count_over_time({namespace=~"bifrost-(dev|stg)"} |~ "NOPERM|No permissions" |= "/quotes/cleanup" [RANGE]))' >"$WORK/noperm_cleanup.txt"

python3 - "$WORK" "$SINCE" <<'PY'
import json, sys, time
from collections import Counter
from datetime import datetime
work, since = sys.argv[1], sys.argv[2]
age_limit = time.time() - datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
pods = {}
for p in json.load(open(f"{work}/pods.json"))["items"]:
    ip = p["status"].get("podIP")
    if ip and not p["spec"].get("hostNetwork"):
        pods[ip] = (p["metadata"]["namespace"], p["metadata"]["name"])
fails, notes = [], []
print(f"== redis-ib: {open(f'{work}/info.txt').read().strip().replace(chr(10), '  ')}")
uptime = int(open(f"{work}/info.txt").read().split("uptime_in_seconds:")[1].split()[0])
if uptime < age_limit:
    notes.append(f"redis-ib restarted {uptime}s ago: ACL LOG only covers that long")

print("== 1. connections (user -> namespace/pod)")
want = {"bifrost-dev": "trade-dev", "bifrost-stg": "trade-stg", "bifrost-prod": "trade-prod"}
seen = Counter()
for line in open(f"{work}/clients.txt"):
    f = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
    ip = f.get("addr", "").rsplit(":", 1)[0]
    ns, pod = pods.get(ip, ("?", ip))
    user = f.get("user", "?")
    seen[(user, ns, pod)] += 1
    if ns in want and user != want[ns]:
        fails.append(f"{ns}/{pod} authenticates as {user} (want {want[ns]})")
    if user == "trade-prod" and ns not in ("bifrost-prod",):
        fails.append(f"trade-prod used by {ns}/{pod}")
for (user, ns, pod), n in sorted(seen.items()):
    print(f"  {user:<11} {ns}/{pod}  x{n}")
for ns, user in want.items():
    if not any(u == user and n == ns for (u, n, _p) in seen):
        notes.append(f"no connection from {ns} as {user} right now (pods idle or down?)")

print(f"== 2. ACL LOG refusals for trade-dev / trade-stg since {since}")
expected, unexpected = Counter(), Counter()
log = json.load(open(f"{work}/acllog.json")) or []
if len(log) >= 128 and max(float(e.get("age-seconds", 0)) for e in log) < age_limit:
    fails.append("ACL LOG is full (128) with entries all newer than the window start: older refusals were evicted;"
                 " read it again sooner (or raise acllog-max-len) before calling this a pass")
for e in log:
    if e.get("username") not in ("trade-dev", "trade-stg") or float(e.get("age-seconds", 0)) > age_limit:
        continue
    ci = dict(kv.split("=", 1) for kv in (e.get("client-info") or "").split() if "=" in kv)
    ns, pod = pods.get(ci.get("addr", "").rsplit(":", 1)[0], ("?", "?"))
    key = (e["username"], e.get("reason"), e.get("context"), e.get("object"), f"{ns}/{pod}")
    n = int(e.get("count", 1))
    if e.get("reason") == "command" and str(e.get("object", "")).lower() in ("srem", "hdel", "del"):
        expected[key] += n
    else:
        unexpected[key] += n
for k, n in sorted(unexpected.items()):
    print(f"  REFUSED  {n:>5}  {' '.join(map(str, k))}")
    fails.append(f"ACL refused {k[0]} {k[1]} {k[3]} ({k[4]})")
for k, n in sorted(expected.items()):
    print(f"  expected {n:>5}  {' '.join(map(str, k))}   (quote cleanup on the shared set)")
if not unexpected and not expected:
    print("  none")

def loki(name):
    raw = open(f"{work}/{name}.txt").read().strip()
    if raw.startswith("UNAVAILABLE"):
        notes.append(f"Loki unavailable for {name}: rerun when loki-0 is Ready")
        return None
    return json.loads(raw or "{}")

gw, noperm, cleanup = loki("gw"), loki("noperm"), loki("noperm_cleanup")
print("== 3. gateway 'refused op' lines:", gw)
if gw:
    fails.append(f"gateway refused ops: {gw}")
print("== 4. api NOPERM lines in dev / stg:", noperm, " of which /quotes/cleanup:", cleanup)
if noperm is not None and cleanup is not None and sum(noperm.values()) > sum(cleanup.values()):
    fails.append("api NOPERM lines other than /quotes/cleanup")
for n in notes:
    print("note:", n)
print("FAIL" if fails else "PASS")
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
PY
