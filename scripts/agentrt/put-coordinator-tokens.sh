#!/usr/bin/env bash
# Owner-only C-7 setup: put-coordinator-tokens.sh stg|prod [replace].
# Tokens travel only in shell variables and pipes until the final 600 files.
case $- in *x*) set +x; echo 'refused: tracing is not supported' >&2; exit 1 ;; esac
set +x
[ -z "${BASH_XTRACEFD:-}" ] || { echo 'refused: tracing is not supported' >&2; exit 1; }
set -euo pipefail
umask 077

die() { echo "refused: $*" >&2; exit 1; }
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || die 'usage: put-coordinator-tokens.sh stg|prod [replace]'
case "$1" in
  stg)
    ns=bifrost-platform-stg
    proposer_key=PLATFORM_SEAT_COORDINATOR_STG_TOKEN
    agentd_key=PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN
    suffix=-stg
    ;;
  prod)
    ns=bifrost-platform-prod
    proposer_key=PLATFORM_PROD_SEAT_COORDINATOR_TOKEN
    agentd_key=PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN
    suffix=""
    ;;
  *) die 'usage: put-coordinator-tokens.sh stg|prod [replace]' ;;
esac
mode=${2:-create}
case "$mode" in create|replace) ;; *) die 'usage: put-coordinator-tokens.sh stg|prod [replace]' ;; esac
[ "$#" -lt 2 ] || [ "$mode" = replace ] || die 'the only optional argument is replace'
export KUBECONFIG="${PUT_TOKEN_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}"
proposer_file="$HOME/.config/bifrost/coordinator-proposer${suffix}.token"
agentd_file="$HOME/.config/bifrost/coordinator-agentd${suffix}.token"

# Check both destinations before generating tokens or touching the Secret.
# Recheck at open time, never follow links, and do not truncate an unsafe file.
local_files() {
  python3 -I -c '
import os, stat, sys
action, mode, *paths = sys.argv[1:]
def check(path):
    parent = os.path.dirname(path)
    while parent != os.path.dirname(parent):
        if os.path.lexists(parent):
            s = os.lstat(parent)
            if not stat.S_ISDIR(s.st_mode):
                raise ValueError("destination parent is not a real directory")
        parent = os.path.dirname(parent)
    if os.path.lexists(path):
        s = os.lstat(path)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
            raise ValueError("destination must be a regular file owned by this user, without links")
        if mode != "replace":
            raise ValueError("local token file already exists; use replace only for an intended rotation")
for path in paths:
    check(path)
if action == "write":
    values = sys.stdin.read().splitlines()
    if len(values) != len(paths):
        raise ValueError("missing generated tokens")
    for path, value in zip(paths, values):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        check(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        if mode != "replace":
            flags |= os.O_EXCL
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w") as f:
            s = os.fstat(f.fileno())
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
                raise ValueError("unsafe destination")
            os.fchmod(f.fileno(), 0o600)
            f.truncate(0)
            f.write(value + "\n")
' "$1" "$mode" "$proposer_file" "$agentd_file" 2>/dev/null
}
local_files check || die 'local token destination exists or is unsafe; no writes made'

secret_keys() {
  # The Secret response goes straight to isolated Python; only key names leave it.
  kubectl -n "$ns" get secret bifrost-platform-role-tokens -o json 2>/dev/null |
    python3 -I -c 'import json, sys; print("\n".join(sorted(json.load(sys.stdin).get("data", {}))))' 2>/dev/null
}
has_key() { printf '%s\n' "$keys" | grep -Fxq -- "$1"; }
keys=$(secret_keys) || die 'could not read Secret key names; no writes made'
if [ "$mode" != replace ] && { has_key "$proposer_key" || has_key "$agentd_key"; }; then
  die 'coordinator Secret key already exists; use replace only for an intended rotation; no writes made'
fi

unset proposer_token agentd_token
proposer_token=$(openssl rand -hex 32 2>/dev/null) || die 'token generation failed; no writes made'
agentd_token=$(openssl rand -hex 32 2>/dev/null) || die 'token generation failed; no writes made'
[[ "$proposer_token" =~ ^[0-9a-f]{64}$ && "$agentd_token" =~ ^[0-9a-f]{64}$ ]] || die 'invalid generated token; no writes made'
[ "$proposer_token" != "$agentd_token" ] || die 'generated tokens must differ; no writes made'
patch_secret() {
  # /dev/stdin keeps the patch off disk, including during server dry-run.
  # Suppress kubectl diagnostics: an API error may echo the rejected payload.
  printf '%s\n%s\n' "$proposer_token" "$agentd_token" |
    python3 -I -c 'import json, sys; print(json.dumps({"stringData": dict(zip(sys.argv[1:], sys.stdin.read().splitlines()))}))' "$proposer_key" "$agentd_key" |
    kubectl -n "$ns" patch secret bifrost-platform-role-tokens --type merge --patch-file /dev/stdin "$@" >/dev/null 2>&1
}
patch_secret --dry-run=server || die 'Secret server dry-run failed; no writes made'
patch_secret || die 'Secret patch failed; its outcome may be unknown; local files were not written'
keys=$(secret_keys) || die 'Secret readback failed after patch; local files were not written'
has_key "$proposer_key" && has_key "$agentd_key" || die 'Secret readback is missing a coordinator key; local files were not written'
printf '%s\n%s\n' "$proposer_token" "$agentd_token" | local_files write || die 'Secret patched, but local token files could not both be written'
unset proposer_token agentd_token
printf '%s\n%s\n%s\n%s\n' "$proposer_key" "$agentd_key" "$proposer_file" "$agentd_file"
