#!/usr/bin/env bash
# Restore drill for the Gitea backups written by backup.sh.
#
# Mounts only the backup claim and an emptyDir. Restores LATEST into the
# emptyDir, starts Gitea bound to 127.0.0.1, creates an access token with
# `gitea admin user generate-access-token` (no password), clones every
# repository in MANIFEST.tsv over HTTP, and requires every ref to match.
# Writes <BACKUP_DIR>/drills/<stamp>-<run>.txt. Exits non-zero unless the
# verdict is PASS, so the CronJob's last success time is the drill's health.
#
# Usage: drill.sh [<run dir name>|latest]   (default: latest)
# Env:   BACKUP_DIR (default /backup), DATA_DIR (default /data).
set -uo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backup}"
DATA_DIR="${DATA_DIR:-/data}"
which="${1:-latest}"
gitea_pid=""

if [[ "$which" == latest ]]; then
  which="$(cat "$BACKUP_DIR/LATEST" 2>/dev/null || true)"
fi
run="$BACKUP_DIR/$which"
stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
report="$(mktemp)"
report_dir="$BACKUP_DIR/drills"

say() { printf '%s\n' "$*" | tee -a "$report"; }

finish() {
  local verdict="$1"
  say "VERDICT: $verdict"
  if [[ -n "$gitea_pid" ]]; then
    kill "$gitea_pid" 2>/dev/null || true
    wait "$gitea_pid" 2>/dev/null || true
  fi
  if [[ -d "$report_dir" && -w "$report_dir" ]]; then
    chmod 0700 "$report_dir" 2>/dev/null || true
    out="$report_dir/$stamp-$which.txt"
    cp "$report" "$out" && chmod 0600 "$out"
    echo "report: $out"
  else
    echo "report directory not writable: $report_dir" >&2
  fi
  rm -f "$report"
  [[ "$verdict" == PASS ]]
  exit $?
}

say "restore drill $stamp  run=$which"
[[ -n "$which" && -d "$run" ]] || { say "no backup run found at $run"; finish FAIL; }
say "status: $(cat "$run/STATUS" 2>/dev/null)"
[[ "$(cat "$run/STATUS" 2>/dev/null)" == OK ]] || { say "run is not OK"; finish FAIL; }

if ( cd "$run" && sha256sum -c -s SHA256SUMS ); then
  say "checksums: ok"
else
  say "checksums: MISMATCH"
  finish FAIL
fi

find "$DATA_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -C "$DATA_DIR" -xf "$run/data.tar" || { say "extract data.tar failed"; finish FAIL; }
app_ini="$DATA_DIR/gitea/conf/app.ini"
[[ -f "$app_ini" ]] || { say "restored tree has no app.ini"; finish FAIL; }

db_path="$(awk '
  /^[[:space:]]*\[/ {
    sec = $0
    gsub(/[][]/, "", sec)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", sec)
    next
  }
  sec == "database" {
    eq = index($0, "=")
    if (eq == 0) next
    k = substr($0, 1, eq - 1)
    v = substr($0, eq + 1)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
    if (k == "PATH") { print v; exit }
  }
' "$app_ini")"
[[ -n "$db_path" ]] || { say "restored app.ini has no database PATH"; finish FAIL; }
[[ "$db_path" == /* ]] || db_path="$DATA_DIR/gitea/$db_path"
mkdir -p "$(dirname "$db_path")"
cp "$run/gitea.db" "$db_path" || { say "cannot place database"; finish FAIL; }
chmod 0600 "$db_path"

integrity="$(sqlite3 "$db_path" "PRAGMA integrity_check;" 2>&1 || true)"
if [[ "$integrity" != ok ]]; then
  say "integrity_check: ${integrity:-failed}"
  finish FAIL
fi
say "integrity_check: ok"

admin="$(sqlite3 "file:${db_path}?mode=ro" "SELECT name FROM user WHERE is_admin=1 ORDER BY id LIMIT 1;" 2>/dev/null || true)"
[[ -n "$admin" ]] || { say "no admin user in the restored database"; finish FAIL; }
say "admin: $admin"

export GITEA_CUSTOM="$DATA_DIR/gitea"
export HOME="${HOME:-/data/git}"
export USER=git
export GITEA__server__PROTOCOL=http
export GITEA__server__HTTP_ADDR=127.0.0.1
export GITEA__server__HTTP_PORT=3000
export GITEA__server__DOMAIN=127.0.0.1
export GITEA__server__ROOT_URL=http://127.0.0.1:3000/
export GITEA__server__DISABLE_SSH=true
export GITEA__server__START_SSH_SERVER=false
export GITEA__database__DB_TYPE=sqlite3
export GITEA__database__PATH="$db_path"
export GITEA__log__MODE=console
export GITEA__service__DISABLE_REGISTRATION=true

environment-to-ini --config "$app_ini" >>"$report" 2>&1 || { say "environment-to-ini failed"; finish FAIL; }
if ! grep -q '^HTTP_ADDR *= *127\.0\.0\.1$' "$app_ini"; then
  say "HTTP_ADDR is not 127.0.0.1 after environment-to-ini"
  finish FAIL
fi

gitea web --config "$app_ini" --work-path "$DATA_DIR/gitea" >/tmp/gitea-web.log 2>&1 &
gitea_pid=$!
ready=0
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:3000/; then
    ready=1
    break
  fi
  if ! kill -0 "$gitea_pid" 2>/dev/null; then
    say "gitea exited before listening"
    tail -n 40 /tmp/gitea-web.log >>"$report" 2>/dev/null || true
    finish FAIL
  fi
  sleep 1
done
(( ready )) || { say "gitea did not answer on 127.0.0.1:3000"; tail -n 40 /tmp/gitea-web.log >>"$report"; finish FAIL; }

# /proc/net/tcp local address 127.0.0.1:3000 is 0100007F:0BB8, state 0A (LISTEN).
if ! awk '$4 == "0A" && $2 == "0100007F:0BB8" { found = 1 } END { exit !found }' /proc/net/tcp; then
  say "gitea is not listening on 127.0.0.1:3000"
  awk '$4 == "0A" { print $2 }' /proc/net/tcp >>"$report"
  finish FAIL
fi
say "listening: 127.0.0.1:3000"

token=""
for _ in $(seq 1 10); do
  token="$(gitea admin user generate-access-token \
    --config "$app_ini" \
    --work-path "$DATA_DIR/gitea" \
    --username "$admin" \
    --token-name "drill-$stamp" \
    --scopes all \
    --raw 2>>"$report" || true)"
  [[ -n "$token" ]] && break
  sleep 1
done
[[ -n "$token" ]] || { say "generate-access-token produced no token"; finish FAIL; }
say "token: generated (not recorded)"
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.extraHeader
export GIT_CONFIG_VALUE_0="Authorization: token ${token}"

fail=0
count=0
while IFS=$'\t' read -r path refs; do
  [[ -n "$path" ]] || continue
  count=$((count + 1))
  rel="${path#git/repositories/}"
  owner="${rel%%/*}"
  name="${rel#*/}"
  name="${name%.git}"
  dest="$(mktemp -d)"
  url="http://127.0.0.1:3000/${owner}/${name}.git"
  if ! git clone --mirror "$url" "$dest" >>"$report" 2>&1; then
    say "clone failed: $path"
    fail=1
    rm -rf "$dest"
    continue
  fi
  got="$(git --git-dir="$dest" for-each-ref --format='%(refname)=%(objectname)' | sort | tr '\n' ' ' | sed 's/ $//')"
  rm -rf "$dest"
  if [[ "$got" != "$refs" ]]; then
    say "ref mismatch: $path"
    say "  manifest: $refs"
    say "  cloned:   $got"
    fail=1
  else
    say "ok: $path"
  fi
done < <(tail -n +2 "$run/MANIFEST.tsv")

(( count > 0 )) || { say "MANIFEST.tsv has no repositories"; finish FAIL; }
(( fail )) && finish FAIL
say "compared: $count repositories"
finish PASS
