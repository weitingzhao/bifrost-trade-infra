#!/bin/sh
# Daily NAS copy of the newest k3s etcd snapshot, plus Kubernetes Secrets,
# platform-state-* ConfigMaps, and the k3s server token. All four are
# age-encrypted before they touch the target disk.
#
# The snapshot is read from the read-only hostPath. age writes ciphertext
# straight to a temp name in the target directory and that name is renamed
# only after the age header checks. No unencrypted snapshot is written to
# the target, including temp files. Source size and sha256 are computed
# before encryption and recorded in MANIFEST (filenames, sizes, sha256,
# timestamp only). Monthly keeps ciphertext and MANIFEST, nothing else.
# See docs/runbooks/cluster-state-restore.md.
set -eu
set -o pipefail
umask 077

BACKUP_ROOT=${BACKUP_ROOT:-/backup}
SNAPSHOT_DIR=${SNAPSHOT_DIR:-/snapshots}
RECIPIENT_FILE=${RECIPIENT_FILE:-/etc/cluster-state-backup/recipient}
TOKEN_FILE=${TOKEN_FILE:-/host/k3s-server-token}
KEEP_DAILY=${KEEP_DAILY:-30}
KEEP_MONTHLY=${KEEP_MONTHLY:-12}
REQUIRE_MOUNT=${REQUIRE_MOUNT:-1}

WORK=""
MTMP=""

cleanup() {
  status=$?
  case "${WORK}" in
    */.partial-*)
      if [ -d "$WORK" ]; then
        rm -rf "$WORK"
      fi
      ;;
  esac
  case "${MTMP}" in
    */.partial-*)
      if [ -d "$MTMP" ]; then
        rm -rf "$MTMP"
      fi
      ;;
  esac
  exit "$status"
}
trap cleanup EXIT

die() {
  echo "FATAL: $*" >&2
  exit 1
}

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

is_mount() {
  awk -v p="$1" '$5 == p { found = 1 } END { exit !found }' /proc/self/mountinfo
}

file_size() {
  wc -c < "$1" | tr -d ' '
}

mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"
}

sha256_of() {
  sha256sum "$1" | awk 'NR==1 { print $1 }'
}

# Reject anything that is not an age ciphertext header. Do not print the
# file: a rejection may be plaintext that must not reach the log.
age_header_ok() {
  f=$1
  magic=$(head -c 22 "$f" 2>/dev/null || true)
  [ "$magic" = "age-encryption.org/v1" ] || return 1
  second=$(awk 'NR==2 { print substr($0, 1, 3); exit }' "$f")
  [ "$second" = "-> " ] || return 1
  size=$(file_size "$f")
  [ "$size" -gt 80 ] || return 1
  return 0
}

# Read plaintext on stdin. The only file created is ciphertext: age writes
# a temp name, the header is checked, then the temp name is renamed.
encrypt_stdin() {
  dest=$1
  tmp="${dest}.partial"
  rm -f "$tmp"
  if ! age -r "$RECIPIENT" -o "$tmp"; then
    rm -f "$tmp"
    echo "FATAL: age failed writing $(basename "$dest")" >&2
    return 1
  fi
  if ! age_header_ok "$tmp"; then
    rm -f "$tmp"
    echo "FATAL: age header rejected for $(basename "$dest"); removed the file" >&2
    return 1
  fi
  mv "$tmp" "$dest"
}

allowed_backup_name() {
  case "$1" in
    etcd-snapshot-*.age|secrets.yaml.age|platform-state.yaml.age|server-token.age|MANIFEST)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Monthly replication. The source name is checked before the copy, so a
# plaintext snapshot cannot be written to the target by this path.
copy_age_or_manifest() {
  src=$1
  dest_dir=$2
  name=$(basename "$src")
  if ! allowed_backup_name "$name"; then
    die "refusing to copy $name onto the monthly target"
  fi
  cp -f "$src" "$dest_dir/$name"
}

field() {
  file=$1
  name=$2
  key=$3
  awk -v name="$name" -v key="$key" '
    $1 == "file" && $2 == name {
      for (i = 1; i <= NF; i++) if ($i == key) { print $(i + 1); exit }
    }
  ' "$file"
}

refuse_plaintext_snapshot() {
  dir=$1
  for f in "$dir"/etcd-snapshot-*; do
    [ -e "$f" ] || continue
    case "$f" in
      *.age) ;;
      *) die "plaintext snapshot on the target: $(basename "$f")" ;;
    esac
  done
}

verify_ciphertext() {
  dir=$1
  name=$2
  manifest=$3
  age_header_ok "$dir/$name" || die "age header rejected for $name"
  want_size=$(field "$manifest" "$name" ciphertext_bytes)
  got_size=$(file_size "$dir/$name")
  [ -n "$want_size" ] && [ "$got_size" = "$want_size" ] || die "ciphertext size mismatch for $name"
  want_sum=$(field "$manifest" "$name" ciphertext_sha256)
  got_sum=$(sha256_of "$dir/$name")
  [ -n "$want_sum" ] && [ "$got_sum" = "$want_sum" ] || die "ciphertext sha256 mismatch for $name"
}

if [ "$REQUIRE_MOUNT" = 1 ] && ! is_mount "$BACKUP_ROOT"; then
  die "$BACKUP_ROOT is not a mountpoint; refusing to write"
fi
[ -d "$BACKUP_ROOT" ] && [ -w "$BACKUP_ROOT" ] || die "$BACKUP_ROOT is not writable"

[ -r "$RECIPIENT_FILE" ] || die "recipient file missing"
RECIPIENT=$(tr -d '[:space:]' < "$RECIPIENT_FILE")
case "$RECIPIENT" in
  *SECRET*|*PRIVATE*)
    die "recipient looks like a private key; refusing"
    ;;
  age1[0-9a-z]*)
    ;;
  *)
    die "age recipient missing or still the placeholder AGE_RECIPIENT"
    ;;
esac

[ -d "$SNAPSHOT_DIR" ] || die "snapshot dir missing"

newest=""
newest_m=0
for f in "$SNAPSHOT_DIR"/*; do
  [ -f "$f" ] || continue
  if [ -L "$f" ]; then
    continue
  fi
  base=$(basename "$f")
  case "$base" in
    .*|*.tmp|*.partial|*.age) continue ;;
  esac
  m=$(mtime "$f")
  if [ "$m" -gt "$newest_m" ]; then
    newest=$f
    newest_m=$m
  fi
done
[ -n "$newest" ] || die "no snapshot file in $SNAPSHOT_DIR"

base=$(basename "$newest")
case "$base" in
  *[!A-Za-z0-9._-]*) die "snapshot name rejected" ;;
esac
case "$base" in
  etcd-snapshot-*) snap_age="${base}.age" ;;
  *) snap_age="etcd-snapshot-${base}.age" ;;
esac
case "$snap_age" in
  etcd-snapshot-*.age) ;;
  *) die "snapshot ciphertext name rejected" ;;
esac

# Integrity of the plaintext is recorded before encryption. k3s publishes a
# snapshot by rename, so this file is complete. The hash is what restore
# checks after decrypting; it is not a reason to store the plaintext.
src_size=$(file_size "$newest") || die "cannot stat snapshot"
[ "$src_size" -gt 0 ] || die "newest snapshot is empty"
src_sum=$(sha256_of "$newest") || die "cannot hash snapshot"
printf '%s\n' "$src_sum" | grep -E '^[0-9a-f]{64}$' >/dev/null || die "snapshot sha256 unreadable"

day=$(date -u +%Y-%m-%d)
DAILY="$BACKUP_ROOT/daily"
MONTHLY="$BACKUP_ROOT/monthly"
mkdir -p "$DAILY" "$MONTHLY"
WORK="$DAILY/.partial-$day"
rm -rf "$WORK"
mkdir -p "$WORK"

# Stdin is the read-only hostPath. age creates only ciphertext in $WORK.
encrypt_stdin "$WORK/$snap_age" < "$newest" || die "snapshot encryption failed"
age_header_ok "$WORK/$snap_age" || die "snapshot age header rejected"

# Names only. The YAML is the following pipeline, into age.
list_configmap_names() {
  kubectl get configmaps -A --no-headers \
    -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name
}
cm_names=/tmp/cm-names.txt
list_configmap_names > "$cm_names"
cm_count=$(awk '$2 ~ /^platform-state-/ { c++ } END { print c+0 }' "$cm_names")
[ "$cm_count" -gt 0 ] || die "no platform-state-* ConfigMaps"

export_platform_state() {
  while read -r ns name _; do
    case "$name" in
      platform-state-*)
        kubectl get configmap "$name" -n "$ns" -o yaml || return 1
        printf '\n---\n'
        ;;
    esac
  done < "$cm_names"
}

kubectl get secrets --all-namespaces -o yaml | encrypt_stdin "$WORK/secrets.yaml.age" \
  || die "secrets export failed"
export_platform_state | encrypt_stdin "$WORK/platform-state.yaml.age" \
  || die "platform-state export failed"

[ -f "$TOKEN_FILE" ] && [ -r "$TOKEN_FILE" ] || die "server token not readable"
encrypt_stdin "$WORK/server-token.age" < "$TOKEN_FILE" \
  || die "server token encryption failed"

snap_ct=$(file_size "$WORK/$snap_age")
snap_ct_sum=$(sha256_of "$WORK/$snap_age")
sec_ct=$(file_size "$WORK/secrets.yaml.age")
sec_ct_sum=$(sha256_of "$WORK/secrets.yaml.age")
cm_ct=$(file_size "$WORK/platform-state.yaml.age")
cm_ct_sum=$(sha256_of "$WORK/platform-state.yaml.age")
tok_ct=$(file_size "$WORK/server-token.age")
tok_ct_sum=$(sha256_of "$WORK/server-token.age")
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
{
  printf 'timestamp %s\n' "$ts"
  printf 'file %s plaintext_bytes %s plaintext_sha256 %s ciphertext_bytes %s ciphertext_sha256 %s\n' \
    "$snap_age" "$src_size" "$src_sum" "$snap_ct" "$snap_ct_sum"
  printf 'file %s ciphertext_bytes %s ciphertext_sha256 %s\n' secrets.yaml.age "$sec_ct" "$sec_ct_sum"
  printf 'file %s ciphertext_bytes %s ciphertext_sha256 %s\n' platform-state.yaml.age "$cm_ct" "$cm_ct_sum"
  printf 'file %s ciphertext_bytes %s ciphertext_sha256 %s\n' server-token.age "$tok_ct" "$tok_ct_sum"
} > "$WORK/MANIFEST"
printf 'OK\n' > "$WORK/STATUS"
refuse_plaintext_snapshot "$WORK"

if [ -d "$DAILY/$day" ]; then
  rm -rf "$DAILY/.old-$day"
  mv "$DAILY/$day" "$DAILY/.old-$day"
fi
if ! mv "$WORK" "$DAILY/$day"; then
  if [ -d "$DAILY/.old-$day" ]; then
    mv "$DAILY/.old-$day" "$DAILY/$day"
  fi
  die "cannot finalize daily/$day"
fi
rm -rf "$DAILY/.old-$day"
WORK=""
refuse_plaintext_snapshot "$DAILY/$day"

month=$(printf '%s' "$day" | cut -c1-7)
MTMP="$MONTHLY/.partial-$month"
rm -rf "$MTMP"
mkdir -p "$MTMP"
copy_age_or_manifest "$DAILY/$day/$snap_age" "$MTMP"
copy_age_or_manifest "$DAILY/$day/secrets.yaml.age" "$MTMP"
copy_age_or_manifest "$DAILY/$day/platform-state.yaml.age" "$MTMP"
copy_age_or_manifest "$DAILY/$day/server-token.age" "$MTMP"
copy_age_or_manifest "$DAILY/$day/MANIFEST" "$MTMP"
for f in "$MTMP"/*; do
  [ -f "$f" ] || continue
  name=$(basename "$f")
  if ! allowed_backup_name "$name"; then
    die "monthly directory has $name, which is not ciphertext or MANIFEST"
  fi
  if [ "$name" = "MANIFEST" ]; then
    continue
  fi
  verify_ciphertext "$MTMP" "$name" "$MTMP/MANIFEST"
done
[ -f "$MTMP/MANIFEST" ] || die "monthly copy missing MANIFEST"
[ -f "$MTMP/$snap_age" ] || die "monthly copy missing snapshot ciphertext"
awk '$1 == "timestamp" && $2 ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}T/ { ok = 1 } END { exit !ok }' \
  "$MTMP/MANIFEST" || die "monthly MANIFEST has no timestamp"
plain_sum=$(field "$MTMP/MANIFEST" "$snap_age" plaintext_sha256)
printf '%s\n' "$plain_sum" | grep -E '^[0-9a-f]{64}$' >/dev/null \
  || die "monthly MANIFEST missing plaintext_sha256"
refuse_plaintext_snapshot "$MTMP"
rm -rf "$MONTHLY/.old-$month"
if [ -d "$MONTHLY/$month" ]; then
  mv "$MONTHLY/$month" "$MONTHLY/.old-$month"
fi
if ! mv "$MTMP" "$MONTHLY/$month"; then
  if [ -d "$MONTHLY/.old-$month" ]; then
    mv "$MONTHLY/.old-$month" "$MONTHLY/$month"
  fi
  die "cannot finalize monthly/$month"
fi
rm -rf "$MONTHLY/.old-$month"
MTMP=""

prune_dated() {
  dir=$1
  keep=$2
  pat=$3
  ls -1 "$dir" 2>/dev/null | grep -E "$pat" | sort -r \
    | awk -v n="$keep" 'NR<=n { next } { print }' > /tmp/prune-names || true
  while read -r name; do
    [ -n "$name" ] || continue
    case "$name" in
      .*) continue ;;
    esac
    rm -rf "$dir/$name"
    log "rotated out ${dir##*/}/$name"
  done < /tmp/prune-names
}

prune_dated "$DAILY" "$KEEP_DAILY" '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
prune_dated "$MONTHLY" "$KEEP_MONTHLY" '^[0-9]{4}-[0-9]{2}$'
now=$(date -u +%s)
for dir in "$DAILY" "$MONTHLY"; do
  for stale in "$dir"/.partial-* "$dir"/.old-*; do
    [ -e "$stale" ] || continue
    m=$(mtime "$stale")
    if [ $((now - m)) -gt 86400 ]; then
      rm -rf "$stale"
    fi
  done
done

log "verified daily/${day} snapshot_sha256=ok age_header=ok files=${snap_age},secrets.yaml.age,platform-state.yaml.age,server-token.age"
exit 0
