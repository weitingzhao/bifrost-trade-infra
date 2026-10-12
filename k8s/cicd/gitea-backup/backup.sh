#!/usr/bin/env bash
# Nightly backup of the in-cluster Gitea (SQLite + the data tree).
#
# The live data mount is read-only. `gitea dump` is not used: 1.21.11 opens
# SQLite as file:<path>?mode=rwc and mkdir's the database directory
# (modules/setting/database.go DBConnStr). The copy here is SQLite's online
# backup over a read-only connection, then PRAGMA integrity_check on the copy.
#
# Layout under BACKUP_DIR (claim cicd/gitea-backup, nfs-cold):
#   <UTC stamp>/gitea.db          online backup of the SQLite file
#   <UTC stamp>/data.tar          rest of the data tree (repos, app.ini, custom,
#                                 avatars, attachments, LFS). Excludes the live
#                                 database files, sessions, queues, indexers,
#                                 logs, and temp.
#   <UTC stamp>/MANIFEST.tsv      one row per repository: path, every ref=sha
#   <UTC stamp>/SIZES.tsv         database, repositories, total
#   <UTC stamp>/SHA256SUMS
#   <UTC stamp>/STATUS            written last: OK, or FAILED: <why>
#   .partial-<stamp>/             while a run is writing
#   drills/                       restore drill reports (drill.sh)
#   LATEST                        name of the newest OK run
#
# A run whose STATUS is not exactly OK is never LATEST and is not counted as
# a backup by retention. Retention runs only after an OK run: newest 7 OK
# runs, plus the newest OK run in each of the 4 trailing 7-day windows
# anchored on the newest OK run. The newest OK run is never deleted.
#
# Env: DATA_DIR (default /data), BACKUP_DIR (default /backup),
#      KEEP_DAILY (default 7), KEEP_WEEKS (default 4),
#      REQUIRE_MOUNT (default 1: refuse unless both dirs are mountpoints).
set -uo pipefail
umask 077

DATA_DIR="${DATA_DIR:-/data}"
BACKUP_DIR="${BACKUP_DIR:-/backup}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKS="${KEEP_WEEKS:-4}"
REQUIRE_MOUNT="${REQUIRE_MOUNT:-1}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "FATAL: $*"; exit 2; }

is_mount() { awk -v p="$1" '$5 == p { found = 1 } END { exit !found }' /proc/self/mountinfo; }

[[ -d "$DATA_DIR" && -r "$DATA_DIR" ]] || die "DATA_DIR $DATA_DIR is not a readable directory"
[[ -d "$BACKUP_DIR" && -w "$BACKUP_DIR" ]] || die "BACKUP_DIR $BACKUP_DIR is not a writable directory"
if [[ "$REQUIRE_MOUNT" == 1 ]]; then
  is_mount "$DATA_DIR" || die "DATA_DIR $DATA_DIR is not a mountpoint"
  is_mount "$BACKUP_DIR" || die "BACKUP_DIR $BACKUP_DIR is not a mountpoint"
fi
if touch "$DATA_DIR/.gitea-backup-write-probe" 2>/dev/null; then
  rm -f "$DATA_DIR/.gitea-backup-write-probe"
  die "DATA_DIR $DATA_DIR is writable; refusing to run"
fi

command -v sqlite3 >/dev/null || die "sqlite3 is not in the image"
command -v git >/dev/null || die "git is not in the image"
command -v tar >/dev/null || die "tar is not in the image"
command -v sha256sum >/dev/null || die "sha256sum is not in the image"

app_ini="$DATA_DIR/gitea/conf/app.ini"
[[ -f "$app_ini" ]] || die "no app.ini at $app_ini"

ini_get() {
  awk -v section="$1" -v key="$2" '
    /^[[:space:]]*[#;]/ { next }
    /^[[:space:]]*\[/ {
      sec = $0
      gsub(/[][]/, "", sec)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", sec)
      next
    }
    sec == section {
      eq = index($0, "=")
      if (eq == 0) next
      k = substr($0, 1, eq - 1)
      v = substr($0, eq + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      if (k == key) { print v; exit }
    }
  ' "$app_ini"
}

db_src="$(ini_get database PATH)"
[[ -n "$db_src" ]] || die "app.ini has no [database] PATH"
[[ "$db_src" == /* ]] || db_src="$DATA_DIR/gitea/$db_src"
[[ -f "$db_src" ]] || die "database file not found: $db_src"

stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
final="$BACKUP_DIR/$stamp"
work="$BACKUP_DIR/.partial-$stamp"
[[ ! -e "$final" ]] || die "$final already exists"
mkdir -p "$work" "$BACKUP_DIR/drills" || die "cannot create $work"
chmod 0700 "$work" "$BACKUP_DIR/drills" || die "cannot chmod $work"
chmod 0700 "$BACKUP_DIR" || log "cannot chmod $BACKUP_DIR; continuing"

reasons=""
fail() {
  log "FAIL: $*"
  if [[ -n "$reasons" ]]; then reasons="$reasons; $*"; else reasons="$*"; fi
}

lock_down() {
  local root="$1"
  find "$root" -type d -exec chmod 0700 {} +
  find "$root" -type f -exec chmod 0600 {} +
}

if [[ -z "$reasons" ]]; then
  log "sqlite online backup (mode=ro) $db_src"
  if ! sqlite3 "file:${db_src}?mode=ro" ".timeout 60000" ".backup ${work}/gitea.db" >/dev/null; then
    fail "sqlite online backup failed"
  fi
fi

if [[ -z "$reasons" ]]; then
  integrity="$(sqlite3 "$work/gitea.db" "PRAGMA integrity_check;" 2>&1 || true)"
  if [[ "$integrity" != ok ]]; then
    fail "PRAGMA integrity_check: ${integrity:-<no answer>}"
  else
    log "integrity_check ok ($(wc -c <"$work/gitea.db" | tr -d ' ') bytes)"
  fi
fi

stage="$work/stage"
repo_bytes=0
if [[ -z "$reasons" ]]; then
  mkdir -p "$stage"
  excludes=(
    --exclude=./gitea/gitea.db
    --exclude=./gitea/gitea.db-wal
    --exclude=./gitea/gitea.db-shm
    --exclude=./gitea/gitea.db-journal
    --exclude=./gitea/sessions
    --exclude=./gitea/queues
    --exclude=./gitea/indexers
    --exclude=./gitea/log
    --exclude=./gitea/actions_log
    --exclude=./gitea/tmp
    --exclude=./gitea/uploads
  )
  if [[ ! -r "$DATA_DIR/ssh" || ! -x "$DATA_DIR/ssh" ]]; then
    log "skipping $DATA_DIR/ssh (not readable by uid $(id -u); the image keeps SSH host keys root-owned)"
    excludes+=(--exclude=./ssh)
  fi
  if ! tar -C "$DATA_DIR" -cf - "${excludes[@]}" . | tar -C "$stage" -xf -; then
    fail "cannot copy the data tree"
  fi
  db_base="$(basename "$db_src")"
  find "$stage" -type f \( -name "$db_base" -o -name "${db_base}-wal" -o -name "${db_base}-shm" -o -name "${db_base}-journal" \) -exec rm -f {} +
fi

repo_list() {
  local root="$1" head dir
  find "$root" -type f -name HEAD 2>/dev/null | while read -r head; do
    dir="$(dirname "$head")"
    [[ -d "$dir/objects" ]] || continue
    printf '%s\n' "${dir#"$root"/}"
  done | sort
}

if [[ -z "$reasons" ]]; then
  while read -r rel; do
    [[ -n "$rel" ]] || continue
    dest="$stage/$rel"
    src="$DATA_DIR/$rel"
    ok=0
    attempt=1
    while (( attempt <= 3 )); do
      if git --git-dir="$dest" fsck --connectivity-only >/tmp/fsck.out 2>&1; then
        ok=1
        break
      fi
      if (( attempt == 3 )); then
        log "fsck failed ($rel) attempt $attempt"
        break
      fi
      log "fsck failed ($rel) attempt $attempt; copying again"
      rm -rf "$dest"
      mkdir -p "$(dirname "$dest")"
      if ! tar -C "$DATA_DIR" -cf - "$rel" | tar -C "$stage" -xf -; then
        log "recopy failed ($rel) attempt $attempt"
      fi
      attempt=$((attempt + 1))
    done
    if (( ok != 1 )); then
      fail "repository $rel failed git fsck after 3 copies"
      break
    fi
    log "fsck ok $rel"
  done < <(repo_list "$stage")
fi

if [[ -z "$reasons" ]]; then
  manifest="$work/MANIFEST.tsv"
  printf 'path\trefs\n' >"$manifest"
  while read -r rel; do
    [[ -n "$rel" ]] || continue
    refs="$(git --git-dir="$stage/$rel" for-each-ref --format='%(refname)=%(objectname)' | sort | tr '\n' ' ' | sed 's/ $//')"
    printf '%s\t%s\n' "$rel" "$refs" >>"$manifest"
    bytes="$(find "$stage/$rel" -type f -exec wc -c {} + | awk 'END { print $1+0 }')"
    repo_bytes=$((repo_bytes + bytes))
  done < <(repo_list "$stage")
  if ! tar -C "$stage" -cf "$work/data.tar" .; then
    fail "cannot write data.tar"
  fi
  rm -rf "$stage"
fi

if [[ -z "$reasons" && -f "$work/gitea.db" && -f "$work/data.tar" && -f "$work/MANIFEST.tsv" ]]; then
  db_bytes="$(wc -c <"$work/gitea.db" | tr -d ' ')"
  archive_bytes="$(wc -c <"$work/data.tar" | tr -d ' ')"
  printf 'database\t%s\nrepositories\t%s\ntotal\t%s\n' \
    "$db_bytes" "$repo_bytes" "$((db_bytes + archive_bytes))" >"$work/SIZES.tsv"
  (
    cd "$work" && sha256sum gitea.db data.tar MANIFEST.tsv SIZES.tsv >SHA256SUMS
  ) || fail "cannot write SHA256SUMS"
fi

if [[ -n "$reasons" ]]; then
  printf 'FAILED: %s\n' "$reasons" >"$work/STATUS"
else
  printf 'OK\n' >"$work/STATUS"
fi
lock_down "$work"
rm -rf "$stage"
mv "$work" "$final" || die "cannot finalize $final"
log "wrote $final ($(cat "$final/STATUS"))"

if [[ "$(cat "$final/STATUS")" != OK ]]; then
  log "not updating LATEST and not rotating; this run is not OK"
  exit 1
fi

printf '%s\n' "$stamp" >"$BACKUP_DIR/LATEST.tmp"
chmod 0600 "$BACKUP_DIR/LATEST.tmp"
mv "$BACKUP_DIR/LATEST.tmp" "$BACKUP_DIR/LATEST"

ok_dirs() {
  local d
  for d in $(ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$' | sort -r); do
    [[ "$(cat "$BACKUP_DIR/$d/STATUS" 2>/dev/null)" == OK ]] && echo "$d"
  done
}

stamp_epoch() { date -u -d "${1:0:10}" +%s; }

declare -A keep=()
mapfile -t oks < <(ok_dirs)
n=0
for d in "${oks[@]+"${oks[@]}"}"; do
  keep["$d"]=1
  n=$((n + 1))
  (( n >= KEEP_DAILY )) && break
done
if ((${#oks[@]})); then
  newest="${oks[0]}"
  keep["$newest"]=1
  newest_epoch="$(stamp_epoch "$newest")"
  w=0
  while (( w < KEEP_WEEKS )); do
    end=$((newest_epoch - w * 7 * 86400))
    start=$((end - 7 * 86400))
    for d in "${oks[@]}"; do
      ep="$(stamp_epoch "$d")"
      if (( ep <= end && ep > start )); then
        keep["$d"]=1
        break
      fi
    done
    w=$((w + 1))
  done
  oldest_kept="$newest"
  for d in "${!keep[@]}"; do
    [[ "$d" < "$oldest_kept" ]] && oldest_kept="$d"
  done
  for d in $(ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$'); do
    [[ -n "${keep[$d]:-}" ]] && continue
    [[ "$d" == "$newest" ]] && continue
    status="$(cat "$BACKUP_DIR/$d/STATUS" 2>/dev/null || true)"
    if [[ "$status" == OK || "$d" < "$oldest_kept" ]]; then
      rm -rf -- "${BACKUP_DIR:?}/$d" && log "rotated out $d"
    fi
  done
fi
find "$BACKUP_DIR" -maxdepth 1 -name '.partial-*' -mmin +1440 -exec rm -rf -- {} + 2>/dev/null
log "finished OK"
