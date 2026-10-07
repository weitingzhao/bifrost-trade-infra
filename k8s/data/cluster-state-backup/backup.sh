#!/bin/sh
# Daily NAS copy of the newest k3s etcd snapshot, plus age-encrypted
# Kubernetes Secrets, platform-state-* ConfigMaps, and the k3s server token.
#
# Secret and ConfigMap YAML is piped into `age -o`. This script never
# redirects that YAML to a file. A failed or unrecognizable age run deletes
# its partial output before the script exits. The etcd snapshot is an exact
# copy (sha256 must match the source file); it is not age-wrapped.
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

# Read plaintext on stdin. The only file created is ciphertext.
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
    .*|*.tmp) continue ;;
  esac
  m=$(mtime "$f")
  if [ "$m" -gt "$newest_m" ]; then
    newest=$f
    newest_m=$m
  fi
done
[ -n "$newest" ] || die "no snapshot file in $SNAPSHOT_DIR"
src_size=$(file_size "$newest")
[ "$src_size" -gt 0 ] || die "newest snapshot is empty"

day=$(date -u +%Y-%m-%d)
DAILY="$BACKUP_ROOT/daily"
MONTHLY="$BACKUP_ROOT/monthly"
mkdir -p "$DAILY" "$MONTHLY"
WORK="$DAILY/.partial-$day"
rm -rf "$WORK"
mkdir -p "$WORK"

base=$(basename "$newest")
cp -f "$newest" "$WORK/$base"
src_sum=$(sha256sum "$newest" | awk 'NR==1 { print $1 }')
dst_sum=$(sha256sum "$WORK/$base" | awk 'NR==1 { print $1 }')
[ "$src_sum" = "$dst_sum" ] || die "snapshot sha256 mismatch"
dst_size=$(file_size "$WORK/$base")
[ "$dst_size" -gt 0 ] || die "copied snapshot is empty"
printf '%s  %s\n' "$dst_sum" "$base" > "$WORK/SHA256SUMS"

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

{
  printf 'snapshot %s bytes %s sha256 %s\n' "$base" "$dst_size" "$dst_sum"
  printf 'secrets.yaml.age bytes %s age_header ok\n' "$(file_size "$WORK/secrets.yaml.age")"
  printf 'platform-state.yaml.age bytes %s age_header ok\n' "$(file_size "$WORK/platform-state.yaml.age")"
  printf 'server-token.age bytes %s age_header ok\n' "$(file_size "$WORK/server-token.age")"
} > "$WORK/MANIFEST"
printf 'OK\n' > "$WORK/STATUS"

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

month=$(printf '%s' "$day" | cut -c1-7)
MTMP="$MONTHLY/.partial-$month"
rm -rf "$MTMP"
cp -a "$DAILY/$day" "$MTMP"
snap=$(awk '$1 == "snapshot" { print $2 }' "$MTMP/MANIFEST")
sum=$(awk '$1 == "snapshot" { print $6 }' "$MTMP/MANIFEST")
got=$(sha256sum "$MTMP/$snap" | awk 'NR==1 { print $1 }')
[ "$got" = "$sum" ] || die "monthly snapshot sha256 mismatch"
age_header_ok "$MTMP/secrets.yaml.age" || die "monthly secrets age header failed"
age_header_ok "$MTMP/platform-state.yaml.age" || die "monthly platform-state age header failed"
age_header_ok "$MTMP/server-token.age" || die "monthly server-token age header failed"
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

log "verified daily/${day} snapshot_sha256=ok age_header=ok files=${base},secrets.yaml.age,platform-state.yaml.age,server-token.age"
exit 0
