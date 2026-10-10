#!/usr/bin/env bash
# Merge release-permissions.json into ~/.claude/settings.json `permissions.allow` / `permissions.ask`.
#
# Why permissions and not autoMode.allow: the prose "Approved Release Runbook" allow entry did not stop
# the classifier from blocking approved release steps on 2026-10-05. Narrow Bash allow rules are resolved
# before the classifier in auto mode (only broad ones like Bash(*) are suspended; autoMode.classifyAllShell
# stays false), and ask rules beat allow rules, so the ask list fences every allow wildcard.
# PreToolUse hooks (scripts/agent-guard/preflight.js, D10) still run first.
#
# Idempotent: existing entries are kept, payload entries are added once. Backup: settings.json.bak-<timestamp>.
#
#   bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-release-permissions.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORKSPACE="${BIFROST_WORKSPACE:-$(cd "$HERE/../../../.." && pwd -P)}"
USER_SETTINGS="$HOME/.claude/settings.json"
STAMP="$(date +%Y%m%dT%H%M%S)"

[ -f "$WORKSPACE/bifrost-platform/config/ops-context.yaml" ] || { echo "not a Bifrost workspace: $WORKSPACE (set BIFROST_WORKSPACE)" >&2; exit 1; }
[ -f "$USER_SETTINGS" ] || echo '{}' > "$USER_SETTINGS"
cp "$USER_SETTINGS" "$USER_SETTINGS.bak-$STAMP"

python3 - "$USER_SETTINGS" "$HERE/release-permissions.json" "$WORKSPACE" <<'PY'
import json, sys
user, payload, workspace = sys.argv[1:]
p = json.load(open(payload))
# The payload spells the workspace root as @WORKSPACE@; each machine gets its own.
p = {k: [r.replace("@WORKSPACE@", workspace) for r in v] for k, v in p.items() if k in ("allow", "ask")}
u = json.load(open(user))
perms = u.setdefault("permissions", {})
for key in ("allow", "ask"):
    cur = perms.setdefault(key, [])
    added = [r for r in p[key] if r not in cur]
    cur.extend(added)
    print(f"{key}: +{len(added)} (now {len(cur)})")
with open(user, "w") as f:
    json.dump(u, f, indent=2, ensure_ascii=False); f.write("\n")
u = json.load(open(user))
missing = [r for k in ("allow", "ask") for r in p[k] if r not in u["permissions"][k]]
if missing:
    sys.exit(f"NOT WRITTEN: {missing}")
if u.get("autoMode", {}).get("classifyAllShell"):
    sys.exit("autoMode.classifyAllShell is true: Bash allow rules are suspended in auto mode")
print("OK: all release permission rules present in", user)
PY
