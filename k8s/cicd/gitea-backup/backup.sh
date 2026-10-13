#!/usr/bin/env bash
# Bash in gitea/gitea:1.21.11 supports pipefail. Plaintext stays in WORK_DIR.
set -euo pipefail
umask 077
DATA_DIR=${DATA_DIR:-/data}
BACKUP_DIR=${BACKUP_DIR:-/backup}
WORK_DIR=${WORK_DIR:-/work}
RECIPIENT_FILE=${RECIPIENT_FILE:-/etc/gitea-backup/recipient}
REQUIRE_MOUNT=${REQUIRE_MOUNT:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
lock_owned=0
partial_owned=0
partial=""
final=""
latest_tmp=""
scratch=""
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
# BusyBox uses stat -c; BSD stat uses -f. No date -d is needed.
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }
cleanup() {
  rc=$?
  trap - EXIT
  # A final directory is immutable, even if updating LATEST fails.
  if [[ $rc != 0 && $partial_owned == 1 && -d "$partial" ]]; then
    rm -rf "$partial/STATUS"
  fi
  [[ -z "$latest_tmp" ]] || rm -rf "$latest_tmp"
  [[ -z "$scratch" ]] || rm -rf "$scratch"
  if [[ $lock_owned == 1 ]]; then rm -rf "$BACKUP_DIR/.lock"; fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
is_mount() { awk -v p="$1" '$5 == p { f=1 } END { exit !f }' /proc/self/mountinfo; }
[[ -d "$DATA_DIR" && -d "$BACKUP_DIR" && -d "$WORK_DIR" ]] || die 'required directory missing'
if [[ $REQUIRE_MOUNT == 1 ]]; then
  is_mount "$DATA_DIR" && is_mount "$BACKUP_DIR" && is_mount "$WORK_DIR" || die 'required mount missing'
fi
# No write probe on the live tree: the mount and PVC are both read-only.
[[ -r "$RECIPIENT_FILE" ]] || die 'recipient file missing'
RECIPIENT=$(tr -d '[:space:]' < "$RECIPIENT_FILE")
case "$RECIPIENT" in
  *SECRET*|*PRIVATE*) die 'recipient looks like a private key; refusing' ;;
  age1*) [[ "$RECIPIENT" =~ ^age1[0-9a-z]+$ ]] || die 'invalid age recipient' ;;
  *) die 'age recipient missing or still the placeholder AGE_RECIPIENT' ;;
esac
now=$(date -u +%s)
if ! mkdir "$BACKUP_DIR/.lock" 2>/dev/null; then
  started=$(cat "$BACKUP_DIR/.lock/started" 2>/dev/null || true)
  # A run killed between mkdir and the write leaves the file missing or empty.
  [[ "$started" =~ ^[0-9]+$ ]] || started=$(mtime "$BACKUP_DIR/.lock")
  [[ "$started" =~ ^[0-9]+$ ]] || die 'NAS lock has invalid start time; inspect it before removal.'
  age_seconds=$((now - started))
  if (( age_seconds <= 10800 )); then die "Another Gitea backup holds the NAS lock (age $age_seconds seconds); refusing a concurrent run."; fi
  printf 'Stale NAS lock older than 3 hours (%s seconds); breaking it.\n' "$age_seconds" >&2
  # Simultaneous stale-lock breakers may both proceed; see README.
  rm -rf "$BACKUP_DIR/.lock"
  mkdir "$BACKUP_DIR/.lock" || die 'Another run acquired the lock while breaking the stale lock.'
fi
lock_owned=1
printf '%s\n' "$now" > "$BACKUP_DIR/.lock/started"
scratch=$(mktemp -d "$WORK_DIR/run.XXXXXX")
# All hooks are inert unless this one explicit variable is set. No production
# manifest sets it. Handshakes have a bounded wait and can be used on every retry.
hook() {
  [[ -n "${GITEA_BACKUP_TEST_HOOK_DIR:-}" ]] || return 0
  local key="$1" dir="$GITEA_BACKUP_TEST_HOOK_DIR" i
  [[ ! -e "$dir/fail-$key" ]] || die "test write fault: $key"
  [[ -e "$dir/wait-$key" ]] || return 0
  printf 'ready\n' > "$dir/$key.ready"
  for i in $(seq 1 300); do
    [[ ! -e "$dir/$key.release" ]] || return 0
    sleep 0.1
  done
  die "test handshake timeout: $key"
}
hook locked
stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
[[ "$stamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || die 'invalid UTC stamp'
partial="$BACKUP_DIR/$stamp.partial"
final="$BACKUP_DIR/$stamp"
[[ ! -e "$partial" ]] || die "run name already taken: $stamp"
newest=""
for d in "$BACKUP_DIR"/*; do
  name=${d##*/}
  name=${name%.partial}
  [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || continue
  [[ "$name" < "$newest" ]] || newest=$name
done
[[ -z "$newest" || "$stamp" > "$newest" ]] || die "clock not monotonic: proposed $stamp, newest $newest"
[[ ! -e "$partial" && ! -e "$final" ]] || die "run name already taken: $stamp"
# Do not create a NAS run until verification has passed.
app_ini="$DATA_DIR/gitea/conf/app.ini"
ini_get() {
  awk -v section="$1" -v key="$2" '
    /^[[:space:]]*[#;]/ { next }
    /^[[:space:]]*\[/ { sec=$0; gsub(/[][]|[[:space:]]/, "", sec); next }
    sec == section { eq=index($0,"="); k=substr($0,1,eq-1); v=substr($0,eq+1);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k); gsub(/^[[:space:]]+|[[:space:]]+$/, "", v);
      if (eq && k == key) { print v; exit } }
  ' "$app_ini"
}
db_src=$(ini_get database PATH)
[[ -n "$db_src" ]] || die 'app.ini has no database PATH'
[[ "$db_src" == /* ]] || db_src="$DATA_DIR/gitea/$db_src"
[[ "$db_src" == "$DATA_DIR/"* && "$db_src" != *'/../'* ]] || die 'database outside live data tree'
db_rel=${db_src#"$DATA_DIR/"}
repo_root=$(ini_get repository ROOT)
repo_root=${repo_root:-$DATA_DIR/git/repositories}
[[ "$repo_root" == "$DATA_DIR/git/repositories" ]] || die 'unsupported repository ROOT; expected data/git/repositories'
repo_set() {
  [[ -d "$1/git/repositories" ]] || return 0
  find "$1/git/repositories" -mindepth 2 -maxdepth 2 -type d -name '*.git' ! -name '*.wiki.git' | sed "s|^$1/||" > "$scratch/disk-raw"
  LC_ALL=C sort -u "$scratch/disk-raw" > "$scratch/disk-sorted"
  [[ $(wc -l < "$scratch/disk-raw" | tr -d ' ') == $(wc -l < "$scratch/disk-sorted" | tr -d ' ') ]] || die 'duplicate repository paths on disk'
  cat "$scratch/disk-sorted"
}
equal=0
for attempt in 1 2 3; do
  stage="$scratch/stage"
  rm -rf "$stage"
  mkdir "$stage"
  sqlite3 "file:${db_src}?mode=ro" '.timeout 60000' ".backup $scratch/gitea.db" > "$scratch/sqlite.log" 2>&1
  hook "after-db-$attempt"
  [[ $(sqlite3 "$scratch/gitea.db" 'PRAGMA integrity_check;') == ok ]] || die 'PRAGMA integrity_check failed'
  # Gitea 1.21.11 models/repo/repo.go RepoPath uses owner.LowerName and
  # repository.LowerName: <repository ROOT>/<owner lower_name>/<repo lower_name>.git.
  # JOIN user includes organizations; COUNT detects missing owner rows.
  sqlite3 "$scratch/gitea.db" "SELECT 'git/repositories/' || u.lower_name || '/' || r.lower_name || '.git' FROM repository r JOIN user u ON u.id=r.owner_id ORDER BY u.lower_name,r.lower_name;" > "$scratch/db-set"
  count=$(sqlite3 "$scratch/gitea.db" 'SELECT count(*) FROM repository;')
  [[ "$count" =~ ^[0-9]+$ && $count -gt 0 ]] || die 'zero repositories or invalid database count'
  [[ $(wc -l < "$scratch/db-set" | tr -d ' ') == "$count" ]] || die 'repository owners missing from database'
  LC_ALL=C sort -u "$scratch/db-set" > "$scratch/db-set.sorted"
  [[ $(wc -l < "$scratch/db-set.sorted" | tr -d ' ') == "$count" ]] || die 'duplicate repository paths'
  mv "$scratch/db-set.sorted" "$scratch/db-set"
  while read -r rel; do
    [[ "$rel" =~ ^git/repositories/[a-z0-9_.-]+/[a-z0-9_.-]+\.git$ && "$rel" != *'/../'* ]] || die 'unsafe repository path in database'
  done < "$scratch/db-set"
  excludes=(--exclude="./$db_rel" --exclude="./$db_rel-wal" --exclude="./$db_rel-shm" --exclude="./$db_rel-journal"
    --exclude=./gitea/sessions --exclude=./gitea/queues --exclude=./gitea/indexers --exclude=./gitea/log --exclude=./gitea/tmp)
  # Image SSH host keys are root-only. Restore generates new keys.
  if [[ ! -r "$DATA_DIR/ssh" || ! -x "$DATA_DIR/ssh" ]]; then excludes+=(--exclude=./ssh); fi
  # Producer is running while the test handshake holds the consumer. A push
  # completes inside this copy pipeline, not by comparing coarse timestamps.
  tar -C "$DATA_DIR" -cf - "${excludes[@]}" . | { hook "copy-$attempt"; tar -C "$stage" -xf -; }
  mkdir -p "$stage/$(dirname "$db_rel")"
  cp "$scratch/gitea.db" "$stage/$db_rel"
  repo_set "$stage" > "$scratch/disk-set"
  if cmp -s "$scratch/db-set" "$scratch/disk-set"; then equal=1; break; fi
  printf 'Repository set mismatch, attempt %s; database-only / disk-only (non-wiki orphan directories fail):\n' "$attempt" >&2
  LC_ALL=C comm -3 "$scratch/db-set" "$scratch/disk-set" >&2
 done
[[ $equal == 1 ]] || die 'repository sets still differ after 3 stages (names above)'
# Wiki repositories have no database row, but must be archived and fsck'd.
find "$stage/git/repositories" -mindepth 2 -maxdepth 2 -type d -name '*.git' | sed "s|^$stage/||" | LC_ALL=C sort -u > "$scratch/fsck-set"
while read -r rel; do
  good=0
  for retry in 1 2 3; do
    if git --git-dir="$stage/$rel" fsck --connectivity-only > "$scratch/fsck.log" 2>&1; then good=1; break; fi
    [[ $retry != 3 ]] || break
    rm -rf "$stage/$rel"
    tar -C "$DATA_DIR" -cf - "$rel" | tar -C "$stage" -xf -
  done
  [[ $good == 1 ]] || die "repository $rel failed git fsck after 3 copies"
done < "$scratch/fsck-set"
repo_set "$stage" > "$scratch/disk-set"
cmp "$scratch/db-set" "$scratch/disk-set" || die 'repository set changed during fsck retries'
hook manifest
printf 'path\trefs\n' > "$scratch/MANIFEST.tsv"
while read -r rel; do
  refs=$(git --git-dir="$stage/$rel" for-each-ref --format='%(refname)=%(objectname)' | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//')
  printf '%s\t%s\n' "$rel" "$refs" >> "$scratch/MANIFEST.tsv"
done < "$scratch/db-set"
tail -n +2 "$scratch/MANIFEST.tsv" | cut -f1 > "$scratch/manifest-set"
cmp "$scratch/db-set" "$scratch/manifest-set" || die 'manifest does not contain exactly the database set'
# Archive first: verification mutates only the disposable stage, never this archive.
tar -C "$stage" -cf "$scratch/data.tar" .
archive_sum=$(sha256sum "$scratch/data.tar" | awk '{print $1}')
repo_bytes=$(find "$stage/git/repositories" -type f -exec sh -eu -c 'for f; do wc -c < "$f"; done' sh {} + | awk '{n+=$1} END {print n+0}')
hook verify
bash "$HERE/verify-stage.sh" "$stage" "$scratch/MANIFEST.tsv" "$scratch/VERIFIED"
mkdir "$partial"
partial_owned=1
chmod 0700 "$partial"
age_header_ok() {
  local magic second size
  magic=$(head -c 22 "$1")
  [[ "$magic" == age-encryption.org/v1 ]] || return 1
  second=$(awk 'NR==2 {print substr($0,1,3);exit}' "$1")
  size=$(wc -c < "$1")
  [[ "$second" == '-> ' && $size -gt 80 ]]
}
encrypt() {
  local src="$1" dest="$2"
  if ! age -r "$RECIPIENT" -o "$dest.partial" < "$src"; then rm -f "$dest.partial"; die 'age encryption failed'; fi
  if ! age_header_ok "$dest.partial"; then rm -f "$dest.partial"; die 'age header rejected; removed ciphertext'; fi
  mv "$dest.partial" "$dest"
}
hook nas-manifest
encrypt "$scratch/MANIFEST.tsv" "$partial/MANIFEST.tsv.age"
encrypt "$scratch/data.tar" "$partial/data.tar.age"
printf 'database_bytes\t%s\nrepository_bytes\t%s\narchive_bytes\t%s\nrepository_count\t%s\n' \
  "$(wc -c < "$scratch/gitea.db" | tr -d ' ')" "$repo_bytes" \
  "$(wc -c < "$scratch/data.tar" | tr -d ' ')" "$count" > "$partial/SIZES.tsv"
cp "$scratch/VERIFIED" "$partial/VERIFIED"
hook sums
(cd "$partial"; sha256sum data.tar.age MANIFEST.tsv.age > SHA256SUMS)
printf '# plaintext_sha256 data.tar %s\n' "$archive_sum" >> "$partial/SHA256SUMS"
# BusyBox sha256sum need not accept comment lines. Check only the two
# ciphertext rows; plaintext_sha256 is a separate restore-only assertion.
awk '!/^#/ {print}' "$partial/SHA256SUMS" > "$scratch/ciphertext-sums"
(cd "$partial"; sha256sum -c "$scratch/ciphertext-sums")
# Prepare/read back LATEST before STATUS; rename only after finalized OK.
latest_tmp="$BACKUP_DIR/LATEST.$stamp.tmp"
hook latest
printf '%s\n' "$stamp" > "$latest_tmp"
[[ $(cat "$latest_tmp") == "$stamp" && $(wc -c < "$latest_tmp" | tr -d ' ') == $((${#stamp}+1)) ]] || die 'LATEST readback failed'
chmod 0600 "$latest_tmp"
find "$partial" -type f -exec chmod 0600 {} +
hook status
printf 'OK\n' > "$partial/STATUS"
[[ $(cat "$partial/STATUS") == OK ]] || die 'STATUS readback failed'
# mv into an existing directory would nest this run inside another one.
[[ ! -e "$final" ]] || die "Run directory $stamp already exists; refusing to publish into it."
# Bash defers traps while waiting for mv. Ignore signals through BOTH renames.
trap '' TERM INT
hook publish
mv "$partial" "$final"
hook published
mv "$latest_tmp" "$BACKUP_DIR/LATEST"
trap 'exit 1' TERM INT
# Retention executes only after successful publication. It always protects LATEST.
hook retention
latest=$(cat "$BACKUP_DIR/LATEST")
: > "$scratch/oks"
for d in "$BACKUP_DIR"/*; do
  name=${d##*/}
  [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || continue
  [[ -f "$d/STATUS" ]] || continue
  if [[ $(cat "$d/STATUS") == OK ]]; then printf '%s\n' "$name" >> "$scratch/oks"; fi
done
LC_ALL=C sort -r "$scratch/oks" > "$scratch/oks.sorted"
head -n 14 "$scratch/oks.sorted" > "$scratch/keep"
printf '%s\n' "$latest" >> "$scratch/keep"
while read -r name; do
  [[ "$name" != "$latest" ]] || continue
  if ! grep -Fxq "$name" "$scratch/keep"; then rm -rf "$BACKUP_DIR/$name"; fi
done < "$scratch/oks.sorted"
for d in "$BACKUP_DIR"/*.partial; do
  [[ -d "$d" && "${d##*/}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z\.partial$ ]] || continue
  if (( now - $(mtime "$d") > 172800 )); then rm -rf "$d"; fi
done
printf 'Backup verified, encrypted and published: %s\n' "$stamp"
