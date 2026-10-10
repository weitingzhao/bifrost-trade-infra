#!/usr/bin/env bash
# Apply the Bifrost auto-mode configuration (Claude Code `autoMode` classifier rules).
#
# The classifier reads `autoMode` only from user settings, managed settings and --settings.
# It ignores the key in project settings (.claude/settings.json and .claude/settings.local.json),
# so a checked-in repo cannot inject its own allow rules:
# https://code.claude.com/docs/en/auto-mode-config.md (verified on 2.1.268, 2026-09-26).
# Both payloads therefore land in user scope:
#
#   user.autoMode.json + project.autoMode.json -> ~/.claude/settings.json   (one merged autoMode)
#   agent-config/claude/settings.local.json    -> permissions only; a stale autoMode block is removed
#
# The owner runs this by hand: the auto-mode classifier refuses to let an agent rewrite
# its own auto-mode rules (built-in hard_deny "Auto-Mode Bypass"), and the
# /auto-mode-setup wizard refuses to write through the /stocks/.claude symlink.
# Backups are written next to each file as *.bak-<timestamp>.
# The run fails if any custom entry is missing from `claude auto-mode config` afterwards.
#
#   bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-auto-mode.sh
#
# Chat approval (LANE-B3) is not an autoMode rule. permissions.ask entries
#   mcp__bifrost-approve__approve_request
#   mcp__bifrost-approve__reject_request
# live in release-permissions.json. This script does not write permissions.ask.
# The Owner applies them with apply-release-permissions.sh (do not run it from an agent).
# Whether auto mode actually pops an allow dialog for those two MCP tools has to be
# verified live; a payload on disk does not prove the dialog appears.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORKSPACE="${BIFROST_WORKSPACE:-$(cd "$HERE/../../../.." && pwd -P)}"
PROJECT="$HERE/../settings.local.json"
USER_SETTINGS="$HOME/.claude/settings.json"
STAMP="$(date +%Y%m%dT%H%M%S)"

[ -f "$WORKSPACE/bifrost-platform/config/ops-context.yaml" ] || { echo "not a Bifrost workspace: $WORKSPACE (set BIFROST_WORKSPACE)" >&2; exit 1; }
[ -f "$PROJECT" ] || echo '{}' > "$PROJECT"
[ -f "$USER_SETTINGS" ] || echo '{}' > "$USER_SETTINGS"
cp "$PROJECT" "$PROJECT.bak-$STAMP"
cp "$USER_SETTINGS" "$USER_SETTINGS.bak-$STAMP"

python3 - "$PROJECT" "$USER_SETTINGS" "$WORKSPACE" "$HERE/user.autoMode.json" "$HERE/project.autoMode.json" <<'PY'
import json, re, sys
project, user, workspace, *blocks = sys.argv[1:]
KEYS = ("environment", "allow", "soft_deny", "hard_deny")
DEFAULTS = "$defaults"

# The payloads spell the workspace root as @WORKSPACE@ and Claude's per-project directory
# name (~/.claude/projects/<slug>) as @WORKSPACE_SLUG@.
slug = re.sub(r"[^A-Za-z0-9]", "-", workspace)
def render(v):
    return v.replace("@WORKSPACE_SLUG@", slug).replace("@WORKSPACE@", workspace) if isinstance(v, str) else v
blocks = [{k: [render(r) for r in v] for k, v in json.load(open(b)).items()} for b in blocks]
unknown = set().union(*blocks) - set(KEYS)
if unknown:
    sys.exit(f"unknown autoMode keys in payload: {sorted(unknown)}")

# Concatenate in payload order (user lines first; the workspace block says it supersedes them).
# "$defaults" is kept once, at the front, when any payload inherits the built-in rules for that list.
merged = {}
for key in KEYS:
    parts = [b[key] for b in blocks if key in b]
    if not parts:
        continue
    rules = []
    for r in (r for p in parts for r in p):
        if r != DEFAULTS and r not in rules:
            rules.append(r)
    merged[key] = ([DEFAULTS] if any(DEFAULTS in p for p in parts) else []) + rules

d = json.load(open(project))
if d.pop("autoMode", None) is not None:
    print("removed ignored autoMode block from project settings.local.json")
# Classic permission rules that auto-allow arbitrary code or open-ended installs never
# reach the classifier; drop them so those commands are judged like any other.
bypass = {"Bash(python3 -)", "Bash(python3 -c ' *)", "Bash(node -e ' *)", "Bash(npm install *)"}
allow = d.setdefault("permissions", {}).get("allow", [])
d["permissions"]["allow"] = [a for a in allow if a not in bypass]
print("removed from project permissions.allow:", sorted(bypass & set(allow)))
with open(project, "w") as f:
    json.dump(d, f, indent=2, ensure_ascii=False); f.write("\n")

u = json.load(open(user))
u["autoMode"] = merged
with open(user, "w") as f:
    json.dump(u, f, indent=2, ensure_ascii=False); f.write("\n")
print("user autoMode written:", {k: len(v) for k, v in merged.items()})
PY

echo
echo "=== effective auto-mode config (user scope + built-in defaults) ==="
cd "$WORKSPACE"
claude auto-mode config | python3 -c '
import json, sys
d = json.load(sys.stdin)
want = json.load(open(sys.argv[1]))["autoMode"]
for k in ("environment", "allow", "soft_deny", "hard_deny"):
    print(f"{k}: {len(d.get(k, []))} entries")
print("\ncustom rule titles:")
for k in ("allow", "soft_deny", "hard_deny"):
    for r in want.get(k, []):
        if r != "$defaults":
            print(f"  [{k}] {r.split(chr(58))[0][:70]}")
custom = [(k, r) for k, rules in want.items() for r in rules if r != "$defaults"]
missing = [(k, r) for k, r in custom if r not in d.get(k, [])]
if missing:
    print(f"\nNOT LIVE — {len(missing)} of {len(custom)} custom entries are missing from the effective config:")
    for k, r in missing:
        print(f"  [{k}] {r[:90]}")
    sys.exit(1)
print(f"\nOK: all {len(custom)} custom entries are live")
' "$USER_SETTINGS"
echo
echo "=== AI critique of the custom rules (optional, takes a minute; Ctrl-C to skip) ==="
claude auto-mode critique || true
