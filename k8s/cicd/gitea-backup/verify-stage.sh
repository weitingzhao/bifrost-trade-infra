#!/usr/bin/env bash
# Disposable restored stage only. Logs and generated token never leave /work.
set -euo pipefail
umask 077
stage=$1
manifest=$2
verified=$3
stage=$(cd "$stage" && pwd)
app_ini="$stage/gitea/conf/app.ini"
scratch=$(mktemp -d "$(dirname "$stage")/verify.XXXXXX")
pid=""
cleanup() {
  rc=$?
  trap - EXIT
  if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  rm -rf "$scratch"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
# Rebase every path in the copied config. /data is the deployment's data root;
# DATA_DIR also supports the isolated no-Docker fixtures. Only this copy changes.
awk -v old="${DATA_DIR:-/data}" -v new="$stage" '{ gsub(old,new); print }' "$app_ini" > "$scratch/app.ini"
cp "$scratch/app.ini" "$app_ini"
db_path=$(awk '
  /^\[/ { s=$0; gsub(/[][]|[[:space:]]/,"",s) }
  s == "database" && /^[[:space:]]*PATH[[:space:]]*=/ { v=$0; sub(/^[^=]*=[[:space:]]*/,"",v); sub(/[[:space:]]*$/,"",v); print v; exit }
' "$app_ini")
[[ "$db_path" == /* ]] || db_path="$stage/gitea/$db_path"
[[ "$db_path" == "$stage/"* && -f "$db_path" ]] || die 'stage database path invalid'
admin=$(sqlite3 "file:$db_path?mode=ro" 'SELECT name FROM user WHERE is_admin=1 ORDER BY id LIMIT 1;')
[[ -n "$admin" ]] || die 'stage has no admin user'
export GITEA_CUSTOM="$stage/gitea"
export GITEA_WORK_DIR="$stage/gitea"
export USER=git
export GITEA__server__PROTOCOL=http
export GITEA__server__HTTP_ADDR=127.0.0.1
export GITEA__server__HTTP_PORT=3000
export GITEA__server__DOMAIN=127.0.0.1
export GITEA__server__ROOT_URL=http://127.0.0.1:3000/
export GITEA__server__DISABLE_SSH=true
export GITEA__server__START_SSH_SERVER=false
export GITEA__server__APP_DATA_PATH="$stage/gitea"
export GITEA__database__DB_TYPE=sqlite3
export GITEA__database__PATH="$db_path"
export GITEA__repository__ROOT="$stage/git/repositories"
export GITEA__log__MODE=console
export GITEA__service__DISABLE_REGISTRATION=true
export GITEA__mailer__ENABLED=false
# Gitea 1.21: webhook.ALLOWED_HOST_LIST restricts destinations; mirror.ENABLED,
# cron.ENABLED, actions.ENABLED and mailer.ENABLED disable background activity.
export GITEA__webhook__ALLOWED_HOST_LIST=loopback
export GITEA__cron__ENABLED=false
export GITEA__mirror__ENABLED=false
export GITEA__actions__ENABLED=false
export GITEA__lfs__PATH="$stage/git/lfs"
# environment-to-ini is provided by the same Gitea image as round 1.
environment-to-ini --config "$app_ini" > "$scratch/config.log" 2>&1
grep -q '^HTTP_ADDR *= *127\.0\.0\.1$' "$app_ini" || die 'stage HTTP_ADDR is not loopback'
gitea web --config "$app_ini" --work-path "$stage/gitea" --custom-path "$stage/gitea" > "$scratch/web.log" 2>&1 &
pid=$!
ready=0
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:3000/; then ready=1; break; fi
  kill -0 "$pid" 2>/dev/null || die 'stage Gitea exited before listening (logs remain private)'
  sleep 1
done
[[ $ready == 1 ]] || die 'stage Gitea did not answer on loopback'
# Require all HTTP listeners on port 3000 to be IPv4 loopback. A fake curl
# in unit tests handles readiness; this check remains active in Docker/Linux.
if [[ -r /proc/net/tcp ]]; then
  awk '$4=="0A" && substr($2,length($2)-4)==":0BB8" { if ($2!="0100007F:0BB8") bad=1; found=1 } END { exit (!found || bad) }' /proc/net/tcp || die 'stage listener is not exclusively loopback'
  if [[ -r /proc/net/tcp6 ]]; then
    awk '$4=="0A" && substr($2,length($2)-4)==":0BB8" { bad=1 } END { exit bad }' /proc/net/tcp6 || die 'unexpected IPv6 HTTP listener'
  fi
fi
token=""
# SQLite may be busy while the web process starts; bounded retry, private log.
for attempt in $(seq 1 10); do
  if token=$(gitea admin user generate-access-token --config "$app_ini" --work-path "$stage/gitea" --custom-path "$stage/gitea" \
    --username "$admin" --token-name "backup-$$-$attempt" --scopes all --raw 2> "$scratch/token.log") && [[ -n "$token" ]]; then break; fi
  token=""
  [[ $attempt == 10 ]] || sleep 1
done
[[ -n "$token" ]] || die 'stage token generation failed after 10 attempts'
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.extraHeader
export GIT_CONFIG_VALUE_0="Authorization: token $token"
count=0
refs_count=0
[[ $(head -n 1 "$manifest") == $'path\trefs' ]] || die 'manifest header invalid'
tail -n +2 "$manifest" > "$scratch/rows"
while IFS=$'\t' read -r path refs; do
  [[ -n "$path" ]] || die 'empty manifest row'
  rel=${path#git/repositories/}
  [[ "$rel" != *.wiki.git && "$rel" != "$path" && "$rel" =~ ^[a-z0-9_.-]+/[a-z0-9_.-]+\.git$ ]] || die 'unsafe manifest repository path'
  dest="$scratch/clone"
  git clone --mirror "http://127.0.0.1:3000/$rel" "$dest" > "$scratch/clone.log" 2>&1 || die "HTTP clone failed: $path"
  got=$(git --git-dir="$dest" for-each-ref --format='%(refname)=%(objectname)' | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//')
  [[ "$got" == "$refs" ]] || die "HTTP ref mismatch: $path"
  count=$((count+1))
  n=$(printf '%s\n' "$got" | awk '{print NF}')
  refs_count=$((refs_count+n))
  rm -rf "$dest"
done < "$scratch/rows"
[[ $count == $(awk 'END {print NR+0}' "$scratch/rows") ]] || die 'clone count does not equal manifest rows'
[[ $count -gt 0 ]] || die 'zero repositories verified'
# Defense in depth: the copied DB set must match the entire manifest again.
sqlite3 "$db_path" "SELECT 'git/repositories/' || u.lower_name || '/' || r.lower_name || '.git' FROM repository r JOIN user u ON u.id=r.owner_id ORDER BY u.lower_name,r.lower_name;" > "$scratch/db-set"
cut -f1 "$scratch/rows" > "$scratch/manifest-set"
for set in db-set manifest-set; do
  LC_ALL=C sort -u "$scratch/$set" > "$scratch/$set.sorted"
  [[ $(wc -l < "$scratch/$set" | tr -d ' ') == $(wc -l < "$scratch/$set.sorted" | tr -d ' ') ]] || die "duplicate repository paths in $set"
done
cmp "$scratch/db-set.sorted" "$scratch/manifest-set.sorted" || die 'verified manifest does not match stage database'
printf '%s repositories and %s refs matched over HTTP\n' "$count" "$refs_count" > "$verified"
