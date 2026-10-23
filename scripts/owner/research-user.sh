#!/usr/bin/env bash
# W-31 3.1 (Screening, S2 A, Owner 2026-10-22): give one person their own Research user.
#
#   KUBECONFIG=<your admin kubeconfig> bash scripts/owner/research-user.sh add <user>    add <user>, restart research-api and research-mcp, copy the new token
#   KUBECONFIG=<your admin kubeconfig> bash scripts/owner/research-user.sh copy <user>   copy an existing user's token to the clipboard again
#
# Run it in your own terminal. It reads and writes the Secret research/bifrost-research-secrets, key RESEARCH_USERS
# ("user:token,user:token", bifrost-research src/bifrost_research/auth/bearer.py). It never prints a token: the new one goes to
# the clipboard only. It prints user names, HTTP status codes and what it did. research-api (it checks tokens) and research-mcp are
# restarted; Dagster is left alone so a running job is not cut: it reads the new user list at its next restart (the next research
# release, or scripts/research-secret-restart.sh), and only then does the journal distiller (known_owner_ids) include the new user.
# If the Secret has no RESEARCH_USERS but has the older single RESEARCH_API_TOKEN, that token is kept as a user (named by
# RESEARCH_DEFAULT_OWNER, else "owner") so the sign-in in use keeps working. If neither is there, Research runs without sign-in and
# adding a user would switch sign-in on for everyone: the script stops and changes nothing.
set -euo pipefail

NS=research
SECRET=bifrost-research-secrets
CHECK_URL=http://192.168.10.73:30880/api/plugin/research/research/screens
say() { echo "[$(date -u +%H:%M:%SZ)] $*"; }
die() { say "STOP: $*"; exit 1; }

step="${1:-}"; user="${2:-}"
case "$step" in add|copy) ;; *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;; esac
[[ "$user" =~ ^[a-z][a-z0-9_-]{1,31}$ ]] || die "user must be lowercase letters, digits, _ or -, 2-32 long, starting with a letter"
[[ -n "${KUBECONFIG:-}" ]] || die "set KUBECONFIG to your admin kubeconfig (this is not the agent's job)"
command -v kubectl >/dev/null || die "kubectl not found"
command -v pbcopy >/dev/null || die "pbcopy not found"

work="$(mktemp -d)"; chmod 700 "$work"; trap 'rm -rf "$work"' EXIT
kubectl -n "$NS" get secret "$SECRET" -o json > "$work/secret.json" || die "cannot read $NS/$SECRET with this kubeconfig"

# All token handling happens inside Python; it writes the patch and the clipboard text to files in the private temp dir.
python3 - "$step" "$user" "$work" <<'EOF'
import base64, json, os, secrets, sys
step, user, work = sys.argv[1:4]
data = json.load(open(os.path.join(work, "secret.json"))).get("data", {}) or {}
dec = lambda k: base64.b64decode(data[k]).decode() if k in data else ""
def parse(raw):
    out = []
    for part in raw.split(","):
        if ":" in part:
            name, tok = part.split(":", 1)
            if name.strip() and tok.strip():
                out.append((name.strip(), tok.strip()))
    return out
users = parse(dec("RESEARCH_USERS").strip())
names = [n for n, _ in users]
def write(name, text):
    p = os.path.join(work, name)
    with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
        f.write(text)
if step == "copy":
    toks = [t for n, t in users if n == user]
    if not toks:
        print(f"STOP: no Research user named {user}; users now: {', '.join(names) or '(none)'}"); sys.exit(1)
    write("clip", toks[0]); write("check", toks[0])
    print(f"users: {', '.join(names)}")
    sys.exit(0)
if not users:
    legacy = dec("RESEARCH_API_TOKEN").strip()
    if not legacy:
        print("STOP: Research has no sign-in configured (no RESEARCH_USERS, no RESEARCH_API_TOKEN); adding a user would switch it on for everyone. Nothing changed.")
        sys.exit(1)
    keep = dec("RESEARCH_DEFAULT_OWNER").strip() or "owner"
    users = [(keep, legacy)]
    names = [keep]
    print(f"kept the existing single token as user '{keep}'")
if user in names:
    print(f"STOP: {user} is already a Research user (users: {', '.join(names)}). To copy that token again: scripts/owner/research-user.sh copy {user}")
    sys.exit(1)
tok = "rsu_" + secrets.token_urlsafe(32)
users.append((user, tok))
raw = ",".join(f"{n}:{t}" for n, t in users)
write("patch.json", json.dumps({"data": {"RESEARCH_USERS": base64.b64encode(raw.encode()).decode()}}))
write("clip", tok); write("check", tok)
# one token per existing user, to prove nobody lost their sign-in
write("others", "".join(f"{n} {t}\n" for n, t in users if n != user))
print(f"users after the change: {', '.join(n for n, _ in users)}")
EOF

if [[ "$step" == "add" ]]; then
  kubectl -n "$NS" patch secret "$SECRET" --type merge --patch-file "$work/patch.json" >/dev/null || die "patching $NS/$SECRET failed; nothing else was done"
  say "added $user to RESEARCH_USERS in $NS/$SECRET"
  for d in research-api research-mcp; do
    kubectl -n "$NS" rollout restart "deploy/$d" >/dev/null
    kubectl -n "$NS" rollout status "deploy/$d" --timeout=240s || die "$d did not come back in 4 minutes; look at: kubectl -n $NS get pods"
    say "$d restarted"
  done
  say "Dagster not restarted: it picks up the new user at its next restart"
fi

# The token reaches curl through a header file in the private temp dir, never through its arguments.
status() {
  { printf 'Authorization: Bearer '; cat "$1"; printf '\n'; } > "$work/hdr"
  curl -s -m 15 -o /dev/null -w '%{http_code}' -H @"$work/hdr" "$CHECK_URL"
}
code=""
for i in 1 2 3 4 5 6; do code="$(status "$work/check")"; [[ "$code" == 200 ]] && break; sleep 5; done
say "$user signs in to Research: HTTP $code (200 = works)"
if [[ -f "$work/others" ]]; then
  while read -r name tok; do
    [[ -n "$name" ]] || continue
    printf '%s' "$tok" > "$work/one"
    say "$name still signs in: HTTP $(status "$work/one")"
  done < "$work/others"
fi
pbcopy < "$work/clip"
say "the token of $user is on your clipboard (not shown). Give it to $user privately; it is pasted once in Research's sign-in (top right of Research › Stock screen)."
[[ "$code" == 200 ]] || die "$user could not sign in yet; tell the coordinating thread the lines above"
