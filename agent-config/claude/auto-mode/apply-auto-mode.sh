#!/usr/bin/env bash
# Apply the Bifrost auto-mode configuration (Claude Code `autoMode` classifier rules).
#
#   project scope -> agent-config/claude/settings.local.json   (real file behind /stocks/.claude;
#                                                              gitignored, local to this machine)
#   user scope    -> ~/.claude/settings.json                   (generic machine-level lines only)
#
# The owner runs this by hand: the auto-mode classifier refuses to let an agent rewrite
# its own auto-mode rules (built-in hard_deny "Auto-Mode Bypass"), and the
# /auto-mode-setup wizard refuses to write through the /stocks/.claude symlink.
# Backups are written next to each file as *.bak-<timestamp>.
#
#   bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-auto-mode.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HERE/../settings.local.json"
USER_SETTINGS="$HOME/.claude/settings.json"
STAMP="$(date +%Y%m%dT%H%M%S)"

[ -f "$PROJECT" ] || echo '{}' > "$PROJECT"
[ -f "$USER_SETTINGS" ] || echo '{}' > "$USER_SETTINGS"
cp "$PROJECT" "$PROJECT.bak-$STAMP"
cp "$USER_SETTINGS" "$USER_SETTINGS.bak-$STAMP"

python3 - "$PROJECT" "$HERE/project.autoMode.json" "$USER_SETTINGS" "$HERE/user.autoMode.json" <<'PY'
import json, sys
project, project_block, user, user_block = sys.argv[1:5]

d = json.load(open(project))
d["autoMode"] = json.load(open(project_block))
# Classic permission rules that auto-allow arbitrary code or open-ended installs never
# reach the classifier; drop them so those commands are judged like any other.
bypass = {"Bash(python3 -)", "Bash(python3 -c ' *)", "Bash(node -e ' *)", "Bash(npm install *)"}
allow = d.setdefault("permissions", {}).get("allow", [])
d["permissions"]["allow"] = [a for a in allow if a not in bypass]
print("removed from project permissions.allow:", sorted(bypass & set(allow)))
with open(project, "w") as f:
    json.dump(d, f, indent=2, ensure_ascii=False); f.write("\n")

u = json.load(open(user))
u["autoMode"] = json.load(open(user_block))
with open(user, "w") as f:
    json.dump(u, f, indent=2, ensure_ascii=False); f.write("\n")
print("user settings keys:", list(u.keys()))
PY

echo
echo "=== effective auto-mode config (merged user + project) ==="
cd "$HERE/../../../.."   # auto-mode -> claude -> agent-config -> bifrost-trade-infra -> the workspace root
claude auto-mode config | python3 -c '
import json, sys
d = json.load(sys.stdin)
for k in ("environment", "allow", "soft_deny", "hard_deny"):
    print(f"{k}: {len(d.get(k, []))} entries")
print("\ncustom rule titles:")
for k in ("allow", "soft_deny", "hard_deny"):
    for r in d[k]:
        print(f"  [{k}] {r.split(chr(58))[0][:70]}")
'
echo
echo "=== AI critique of the custom rules (optional, takes a minute; Ctrl-C to skip) ==="
claude auto-mode critique || true
