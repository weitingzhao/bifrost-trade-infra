#!/usr/bin/env bash
# TD-444 step 5: copy, verify and cut over the NAS data onto the SSD RAID1 (runbook §2, §3.3–§3.7, §4).
#
# Runs on the NAS as root, from the unpacked material package (runbook §3.2). Writing commands
# run only from the package's own copy (<pkg>/scripts/nas/td444-move.sh), after the package
# matched SHA256SUMS. Helpers next to it: td444-guard.sh (copy guard, abort traps),
# td444-minio.sh (MinIO stages), backup-checks.sh (integrity checks shared with the roll-up)
# and registry-check.py (its registry graph check, needs python3).
#   sudo bash <pkg>/scripts/nas/td444-move.sh --pkg <pkg> --sums <pkg>/../SHA256SUMS --map <private map> <command> ...
# The map (private; template td444-map.example) lists every copy as
#   <group> <key> <kind> <source dir> <target dir> [<snapshot root>]
#
# Read-only commands (write only their own log):
#   check-pkg  map-check  exports  identity-check <group>  verify <group>  status <name>  temps
#   minio-eligibility | minio-wal-layout | minio-base-check | minio-continuity   (see td444-minio.sh)
# Writing commands (each needs --confirm <the group, or the word in its help line>):
#   identity-record <group>        record the mount identity (state only)
#   pre <group> [--from-snapshot]  copy, add only, never delete (§3.3)
#   final <group>                  the only --delete pass: identity, path and delete-list checks,
#                                  typed "yes", copy, full verification (§3.3); a registry line
#                                  also needs --reg-digests <file> (<repository>@sha256:<hex> lines)
#   verify <group> --from-snapshot --confirm <group>   (creates a snapshot)
#   snap-clean                     delete the recorded read-only snapshots   (--confirm snap-clean)
#   minio-m0 .. minio-m4b, minio-m4a-stop, minio-rollback-a, minio-readback   (--confirm minio)
#
# Every step appends attempt/done/fail lines to a phase file and logs to $STATE/logs/. Copies
# run under the guard of td444-guard.sh: temperature pause 72 °C / resume 65 °C / pause when a
# sensor gives no reading for 180 s, --bwlimit, --timeout, and INT/TERM/HUP/exit stop the copy.
set -euo pipefail
umask 077

PROG=${0##*/}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE=/volume1/@bifrost/td444
MAP="" PKG="" SUMS="" CONFIRM="" RUN_ID="" RANGE="" DATA="" METHOD="mc"
BWLIMIT="" TIMEOUT=0 FROM_SNAPSHOT=0 EXPECT_COMPOSE_SHA="" REG_DIGESTS=""
TEMP_PAUSE=72 TEMP_RESUME=65 TEMP_MISSING=180 TEMP_POLL=30 TEMP_NAME=nvme TEMP_SENSORS=2
HWMON=${TD444_HWMON:-/sys/class/hwmon}   # tests point this at a fake tree
COMPOSE_DIR=/volume1/docker/minio-backup CONTAINER=minio-backup BUCKET=bifrost-postgres-backup
SRC_ROOTS=(/volume1/k3s-hot /volume1/k3s-cold /volume2/k3s-fast /volume2/minio-backup)
DST_ROOTS=(/volume2/k3s-fast /volume2/minio-backup /volume1/k3s-cold/td444-recovery /volume1/minio-recovery-td444)
EXPORT_REF=/volume1/k3s-hot
EXPORT_NEW=(/volume2/k3s-fast /volume2/market-archive-backup)
HELPERS=(td444-move.sh td444-guard.sh td444-minio.sh backup-checks.sh registry-check.py)

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FAIL: $*"; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 2; }

ARGS=()
while (($#)); do
  case "$1" in
    --map) MAP=$2; shift 2 ;;            --pkg) PKG=$2; shift 2 ;;
    --sums) SUMS=$2; shift 2 ;;          --state) STATE=$2; shift 2 ;;
    --confirm) CONFIRM=$2; shift 2 ;;    --run-id) RUN_ID=$2; shift 2 ;;
    --range) RANGE=$2; shift 2 ;;        --data) DATA=$2; shift 2 ;;
    --method) METHOD=$2; shift 2 ;;      --bwlimit) BWLIMIT=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;    --from-snapshot) FROM_SNAPSHOT=1; shift ;;
    --expect-compose-sha256) EXPECT_COMPOSE_SHA=$2; shift 2 ;;
    --reg-digests) REG_DIGESTS=$2; shift 2 ;;
    --temp-pause) TEMP_PAUSE=$2; shift 2 ;;      --temp-resume) TEMP_RESUME=$2; shift 2 ;;
    --temp-missing) TEMP_MISSING=$2; shift 2 ;;  --temp-poll) TEMP_POLL=$2; shift 2 ;;
    --temp-sensors) TEMP_SENSORS=$2; shift 2 ;;  --compose-dir) COMPOSE_DIR=$2; shift 2 ;;
    -h|--help) usage ;;
    --*) die "unknown option $1" ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
((${#ARGS[@]})) || usage
CMD=${ARGS[0]}
ARG1=${ARGS[1]:-}
for v in "$TIMEOUT" "$TEMP_PAUSE" "$TEMP_RESUME" "$TEMP_MISSING" "$TEMP_POLL" "$TEMP_SENSORS"; do
  [[ $v =~ ^[0-9]+$ ]] || die "--timeout and --temp-* take whole numbers"
done
((TEMP_RESUME < TEMP_PAUSE && TEMP_SENSORS >= 1)) || die "--temp-resume must be below --temp-pause; --temp-sensors >= 1"
[[ -z $BWLIMIT || $BWLIMIT =~ ^[0-9]+[KMG]?$ ]] || die "--bwlimit must look like 200M"
[[ -z $RUN_ID || $RUN_ID =~ ^[A-Za-z0-9-]{1,40}$ ]] || die "--run-id: letters, digits, dashes"
((EUID == 0)) || die "run as root (sudo)"

mkdir -p "$STATE/logs" "$STATE/identity"
chmod 700 "$STATE"
LOG="$STATE/logs/$(date -u +%Y%m%dT%H%M%SZ)-$CMD${ARG1:+-$ARG1}${RUN_ID:+-$RUN_ID}.log"
exec > >(tee -a "$LOG") 2>&1
log "$PROG $CMD ${ARG1:-} (log $LOG)"

phase_file() { printf '%s/%s.phase' "$STATE" "$1"; }
phase() { # phase <name> attempt|done|fail <stage> [note]
  printf '%s %s %s%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2" "$3" "${4:+ $4}" >> "$(phase_file "$1")"
  log "phase $1: $2 $3${4:+ ($4)}"
}
has_phase() { [[ -f $(phase_file "$1") ]] && grep -Eq " $2 $3( |\$)" "$(phase_file "$1")"; }
require_confirm() { [[ $CONFIRM == "$1" ]] || die "this command writes; repeat it with --confirm $1"; }
ask_yes() {
  local answer
  [[ -r /dev/tty ]] || die "no terminal to confirm on; run with ssh -t"
  printf '%s Type yes to continue: ' "$1" > /dev/tty
  read -r answer < /dev/tty
  [[ $answer == yes ]] || die "not confirmed"
}

# shellcheck source=td444-guard.sh
. "$SCRIPT_DIR/td444-guard.sh"
# shellcheck source=backup-checks.sh
. "$SCRIPT_DIR/backup-checks.sh"

check_pkg() { # the package matches its sums, and this run executes the package's own scripts
  local f
  [[ -n $PKG && -n $SUMS && -d $PKG && -r $SUMS ]] || die "--pkg and --sums are required"
  (cd "$PKG" && sha256sum -c --quiet --strict "$SUMS") || die "package does not match $SUMS"
  [[ $SCRIPT_DIR == "$(realpath -e "$PKG/scripts/nas")" && $(realpath -e "$0") == "$SCRIPT_DIR/td444-move.sh" ]] \
    || die "run the package's own copy: $PKG/scripts/nas/td444-move.sh (this is $0)"
  for f in "${HELPERS[@]}"; do
    grep -Eq "^[0-9a-f]{64}  \./scripts/nas/$f\$" "$SUMS" || die "$f is not listed in $SUMS"
  done
  log "package matches $SUMS; running its td444-move.sh $(sha256sum "$0" | cut -d' ' -f1)"
}

# ---------------------------------------------------------------- map (the allow-list)
M_GROUP=() M_KEY=() M_KIND=() M_SRC=() M_DST=() M_SNAP=()
under() { local p=$1 r; shift; for r in "$@"; do [[ $p == "$r"/* ]] && return 0; done; return 1; }
overlap() { [[ $1 == "$2" || $1 == "$2"/* || $2 == "$1"/* ]]; }
load_map() {
  [[ -n $MAP && -r $MAP ]] || die "--map <file> is required"
  local n=0 g k kind s d snap extra p i j
  while read -r g k kind s d snap extra; do
    n=$((n + 1))
    [[ -z ${g:-} || $g == \#* ]] && continue
    [[ -z ${extra:-} ]] || die "map line $n: too many fields"
    [[ $g =~ ^[a-z][a-z0-9-]*$ && $k =~ ^[A-Z][A-Z0-9]*$ ]] || die "map line $n: bad group or key"
    case $kind in logical|finance|gitea|cluster-state|monitoring|registry|minio|plain) ;; *) die "map line $n: unknown kind $kind" ;; esac
    for p in "$s" "$d" ${snap:+"$snap"}; do
      [[ $p == /* && $p != */ && $p != *//* && $p != *..* ]] || die "map line $n: bad path $p"
    done
    under "$s" "${SRC_ROOTS[@]}" || die "map line $n: source $s is outside the allowed roots"
    under "$d" "${DST_ROOTS[@]}" || die "map line $n: target $d is outside the allowed roots"
    ! overlap "$s" "$d" || die "map line $n: source and target overlap"
    [[ -z ${snap:-} || $s == "$snap" || $s == "$snap"/* ]] || die "map line $n: snapshot root does not contain the source"
    M_GROUP+=("$g") M_KEY+=("$k") M_KIND+=("$kind") M_SRC+=("$s") M_DST+=("$d") M_SNAP+=("${snap:-}")
  done < "$MAP"
  ((${#M_KEY[@]})) || die "map is empty"
  # whole-map rules: unique keys; no two targets equal or nested; a target never overlaps
  # another line's source, except that a *-recovery line reads exactly a normal line's target
  for i in "${!M_KEY[@]}"; do
    for j in "${!M_KEY[@]}"; do
      ((i < j)) || continue
      [[ ${M_KEY[$i]} != "${M_KEY[$j]}" ]] || die "map: key ${M_KEY[$i]} is used twice"
      ! overlap "${M_DST[$i]}" "${M_DST[$j]}" || die "map: targets of ${M_KEY[$i]} and ${M_KEY[$j]} overlap"
    done
    for j in "${!M_KEY[@]}"; do
      ((i != j)) || continue
      overlap "${M_DST[$i]}" "${M_SRC[$j]}" || continue
      [[ ${M_GROUP[$j]} == *-recovery && ${M_GROUP[$i]} != *-recovery && ${M_SRC[$j]} == "${M_DST[$i]}" ]] \
        || die "map: target of ${M_KEY[$i]} overlaps the source of ${M_KEY[$j]}"
    done
  done
}
entries() { # entries <group>: indexes; "all" = every group except *-recovery
  local i out=()
  for i in "${!M_KEY[@]}"; do
    if [[ ${M_GROUP[$i]} == "$1" || ($1 == all && ${M_GROUP[$i]} != *-recovery) ]]; then out+=("$i"); fi
  done
  ((${#out[@]})) || die "no map entries for group $1"
  printf '%s\n' "${out[@]}"
}
group_ok() { entries "$1" > /dev/null; }
dst_parent_ok() { # the target's parent exists, or is an allowed target root whose own parent exists
  local parent r; parent=$(dirname "$1")
  [[ -d $parent ]] && return 0
  for r in "${DST_ROOTS[@]}"; do [[ $parent == "$r" && -d $(dirname "$r") ]] && return 0; done
  return 1
}
check_real_paths() { # the source exists with no symlink in it; the target's parent is real
  local s=${M_SRC[$1]} d=${M_DST[$1]}
  [[ -d $s && $(realpath -e "$s") == "$s" ]] || die "${M_KEY[$1]}: source $s is missing or not a real path"
  dst_parent_ok "$d" && [[ $(realpath -m "$d") == "$d" ]] || die "${M_KEY[$1]}: target parent of $d is missing or a link"
  if [[ -e $d && $(realpath -e "$d") != "$d" ]]; then die "${M_KEY[$1]}: target $d is a link"; fi
}
make_dst_root() {
  local parent r; parent=$(dirname "${M_DST[$1]}")
  for r in "${DST_ROOTS[@]}"; do
    if [[ $parent == "$r" && ! -d $r && -d $(dirname "$r") ]]; then mkdir -m 700 "$r"; log "created $r"; fi
  done
}
nested_subvolume() { find "$1" -mindepth 1 -xdev -type d -inum 256 -print -quit 2> /dev/null; }

# ---------------------------------------------------------------- mount identity (§2)
ident_of() { # SOURCE FSTYPE ro|rw UUID subvolid, of the path or its nearest existing parent
  local p=$1 src fstype opts uuid
  while [[ ! -e $p ]]; do p=$(dirname "$p"); done
  read -r src fstype opts uuid < <(findmnt -no SOURCE,FSTYPE,OPTIONS,UUID -T "$p")
  [[ ,$opts, == *,rw,* ]] && opts=rw || opts=ro
  printf '%s %s %s %s %s' "$src" "$fstype" "$opts" "${uuid:--}" "$(btrfs inspect-internal rootid "$p" 2> /dev/null || echo -)"
}
apparent_bytes() { du -s -B1 --apparent-size "$1" | cut -f1; }
avail_bytes() { local p=$1; while [[ ! -e $p ]]; do p=$(dirname "$p"); done; df -B1 --output=avail "$p" | tail -1 | tr -d ' '; }
identity_record() {
  local i rec="$STATE/identity/$1.rec"
  group_ok "$1"
  : > "$rec.tmp"
  while read -r i; do
    check_real_paths "$i"
    printf '%s src %s\n' "${M_KEY[$i]}" "$(ident_of "${M_SRC[$i]}")" >> "$rec.tmp"
    printf '%s dst %s\n' "${M_KEY[$i]}" "$(ident_of "${M_DST[$i]}")" >> "$rec.tmp"
  done < <(entries "$1")
  mv "$rec.tmp" "$rec"
  cat "$rec"
  log "identity of $1 recorded in $rec"
}
identity_check() { # every path of the group: same mount identity as recorded, 1.2x free space
  local i rec="$STATE/identity/$1.rec" now need have bad=0 side
  group_ok "$1"
  [[ -f $rec ]] || die "no identity record for $1 (identity-record $1 first)"
  while read -r i; do
    check_real_paths "$i"
    for side in src dst; do
      if [[ $side == src ]]; then now=$(ident_of "${M_SRC[$i]}"); else now=$(ident_of "${M_DST[$i]}"); fi
      if ! grep -Fxq "${M_KEY[$i]} $side $now" "$rec"; then log "${M_KEY[$i]} $side changed: now '$now'"; bad=1; fi
    done
    need=$(( $(apparent_bytes "${M_SRC[$i]}") * 12 / 10 ))
    have=$(avail_bytes "${M_DST[$i]}")
    if ((have < need)); then log "${M_KEY[$i]}: target has $have bytes free, needs $need (1.2x)"; bad=1; fi
  done < <(entries "$1")
  ((bad == 0)) || die "mount identity or free space check failed for $1"
  log "mount identity and free space of $1 match the record"
}

RSYNC_ACLS=""
rsync_caps() { # once, in the calling shell: "no ACLs" in rsync -V (UGOS 1.18) means copies leave -A out
  local v
  [[ -n $RSYNC_ACLS ]] && return 0
  # Read it whole: rsync writes -V line by line, so a pipe into grep -q ends it by SIGPIPE and
  # pipefail reads that as "no match" (the NAS's first pre kept -A that way).
  v=$(rsync -V) || die "rsync -V failed"
  if [[ $v == *'no ACLs'* ]]; then RSYNC_ACLS=0; log "this rsync has no ACL support (rsync -V)"; else RSYNC_ACLS=1; log "this rsync has ACL support: copies keep -A"; fi
}
rsync_opts() { # -A only when this rsync has ACL support (no_extended_acls guards the copies without it)
  [[ -n $RSYNC_ACLS ]] || rsync_caps > /dev/null 2>&1
  if ((RSYNC_ACLS)); then printf '%s\n' -aHAX; else printf '%s\n' -aHX; fi
  printf '%s\n' --numeric-ids ${BWLIMIT:+--bwlimit="$BWLIMIT"}
}
no_extended_acls() { # no_extended_acls <key> <dir>: without -A, any extended POSIX ACL under dir would be lost: stop (§2)
  local out
  rsync_caps
  ((RSYNC_ACLS)) && return 0
  out=$(mktemp)
  getfacl -R --skip-base -p "$2" > "$out" \
    || { rm -f "$out"; die "$1: cannot read the POSIX ACLs under $2; this rsync has no ACL support (stop and check, §2)"; }
  if grep -q '^# file' "$out"; then
    log "$1: these carry extended POSIX ACLs, which this rsync (no ACL support) cannot copy:"; grep '^# file' "$out" | head -5
    rm -f "$out"; die "$1: extended POSIX ACLs under $2 (stop and check, §2)"
  fi
  rm -f "$out"
  log "$1: no extended POSIX ACLs under $2; this rsync has no ACL support, so copies leave -A out"
}
make_snapshot() { # read-only snapshot of the snapshot root, recorded with its UUID; prints the source view
  local i=$1 root=${M_SNAP[$1]} mnt snapdir snap uuid
  [[ -n $root ]] || die "${M_KEY[$i]}: no snapshot root in the map"
  btrfs subvolume show "$root" > /dev/null 2>&1 || die "${M_KEY[$i]}: $root is not a btrfs subvolume"
  if [[ ${M_SRC[$i]} != "$root" ]] && btrfs subvolume show "${M_SRC[$i]}" > /dev/null 2>&1; then
    die "${M_KEY[$i]}: the source is itself a subvolume, not inside $root's snapshot"
  fi
  [[ -z $(nested_subvolume "${M_SRC[$i]}") ]] || die "${M_KEY[$i]}: nested subvolume under ${M_SRC[$i]}; refusing"
  mnt=$(findmnt -no TARGET -T "$root")
  snapdir="$mnt/@bifrost/td444-snap"
  mkdir -p "$snapdir"
  snap="$snapdir/${M_KEY[$i]}-$(date -u +%Y%m%dT%H%M%SZ)"
  btrfs subvolume snapshot -r "$root" "$snap" > /dev/null
  uuid=$(btrfs subvolume show "$snap" | awk '$1 == "UUID:" { print $2; exit }')
  [[ -n $uuid ]] || die "${M_KEY[$i]}: snapshot $snap has no UUID"
  printf '%s %s\n' "$snap" "$uuid" >> "$STATE/snapshots.list"
  log "${M_KEY[$i]}: read-only snapshot $snap ($uuid)" >&2
  printf '%s%s' "$snap" "${M_SRC[$i]#"$root"}"
}
content_verify() { # exit 0 and an empty itemize list, or failure (§3.3)
  local out rc=0 t0=$SECONDS
  rsync_caps
  out="$STATE/logs/verify-$1-$(date -u +%Y%m%dT%H%M%SZ).list"
  # shellcheck disable=SC2046  # option words, none with spaces
  guarded rsync $(rsync_opts) -c -n --delete --itemize-changes "$2/" "$3/" > "$out" || rc=$?
  ((rc == 0)) || die "$1: verification rsync exited $rc (list $out)"
  if [[ -s $out ]]; then
    log "$1: $(wc -l < "$out") differences, first ones:"; head -20 "$out"
    die "$1: target differs from source (list $out)"
  fi
  log "$1: content identical (rsync -c, empty list), T_c=$((SECONDS - t0))s"
  printf '%s %s\n' "$1" "$((SECONDS - t0))" >> "$STATE/tc.list"
}
manifest_check() { # the kind's own check (backup-checks.sh); MinIO objects are the M stages' evidence
  if [[ $2 == minio ]]; then
    log "$1: MinIO objects are checked by minio-base-check, minio-continuity and minio-readback (runbook §4 group 6)"; return 0
  fi
  BC_REG_DIGESTS=$REG_DIGESTS
  check_kind "$2" "$3" || die "$1: own manifest check ($2) failed on $3"
  log "$1: own manifests ($2) verify"
}
kind_inputs_ok() { # what the own checks of a group need, before any copy
  local i
  while read -r i; do
    [[ ${M_KIND[$i]} == registry ]] || continue
    [[ -n $REG_DIGESTS && -s $REG_DIGESTS ]] || die "${M_KEY[$i]}: --reg-digests <file> is required (the recorded <repository>@sha256:<hex> digests, runbook §4 group 4)"
    command -v python3 > /dev/null || die "${M_KEY[$i]}: python3 is needed for the registry check (runbook §3.8)"
  done < <(entries "$1")
}

# ---------------------------------------------------------------- pre / final / verify
cmd_pre() { # every check of the whole group passes before the first directory or copy
  local g=$1 i view rc
  require_confirm "$g"; check_pkg; no_active_copy; group_ok "$g"
  identity_check "$g"
  while read -r i; do
    check_real_paths "$i"
    no_extended_acls "${M_KEY[$i]}" "${M_SRC[$i]}"
    if ((FROM_SNAPSHOT)); then [[ -n ${M_SNAP[$i]} ]] || die "${M_KEY[$i]}: --from-snapshot needs a snapshot root"; fi
  done < <(entries "$g")
  ABORT_PHASE=$g
  while read -r i; do
    make_dst_root "$i"
    mkdir -p "${M_DST[$i]}"
    view=${M_SRC[$i]}
    ABORT_STAGE="pre:${M_KEY[$i]}"
    phase "$g" attempt "pre:${M_KEY[$i]}"
    if ((FROM_SNAPSHOT)); then view=$(make_snapshot "$i"); fi
    rc=0
    # shellcheck disable=SC2046
    guarded rsync $(rsync_opts) --log-file="$STATE/logs/rsync-pre-${M_KEY[$i]}.log" "$view/" "${M_DST[$i]}/" || rc=$?
    if ((rc != 0)); then phase "$g" fail "pre:${M_KEY[$i]}" "rsync $rc"; die "${M_KEY[$i]}: pre copy exited $rc"; fi
    if ((FROM_SNAPSHOT)); then content_verify "${M_KEY[$i]}" "$view" "${M_DST[$i]}"; fi
    phase "$g" "done" "pre:${M_KEY[$i]}"
  done < <(entries "$g")
}
cmd_final() {
  local g=$1 i dl n rc
  require_confirm "$g"; check_pkg; no_active_copy; group_ok "$g"; kind_inputs_ok "$g"
  identity_check "$g"
  while read -r i; do
    [[ -d ${M_DST[$i]} ]] || die "${M_KEY[$i]}: target ${M_DST[$i]} missing; run pre first"
    no_extended_acls "${M_KEY[$i]}" "${M_SRC[$i]}"
  done < <(entries "$g")
  ABORT_PHASE=$g
  while read -r i; do
    ABORT_STAGE="final:${M_KEY[$i]}"
    phase "$g" attempt "final:${M_KEY[$i]}"
    dl="$STATE/logs/delete-${M_KEY[$i]}-$(date -u +%Y%m%dT%H%M%SZ).list"
    rc=0
    # shellcheck disable=SC2046
    rsync $(rsync_opts) -n --delete --itemize-changes "${M_SRC[$i]}/" "${M_DST[$i]}/" > "$dl.all" || rc=$?
    ((rc == 0)) || { phase "$g" fail "final:${M_KEY[$i]}" "dry-run $rc"; die "${M_KEY[$i]}: delete-list dry run exited $rc"; }
    grep '^\*deleting' "$dl.all" > "$dl" || true
    n=$(wc -l < "$dl")
    log "${M_KEY[$i]}: ${M_SRC[$i]} -> ${M_DST[$i]}: $(wc -l < "$dl.all") changes, $n deletions (list $dl)"
    head -50 "$dl"
    ask_yes "${M_KEY[$i]}: $n files will be deleted from ${M_DST[$i]}."
    rc=0
    # shellcheck disable=SC2046
    guarded rsync $(rsync_opts) --delete --log-file="$STATE/logs/rsync-final-${M_KEY[$i]}.log" "${M_SRC[$i]}/" "${M_DST[$i]}/" || rc=$?
    ((rc == 0)) || { phase "$g" fail "final:${M_KEY[$i]}" "rsync $rc"; die "${M_KEY[$i]}: final copy exited $rc"; }
    content_verify "${M_KEY[$i]}" "${M_SRC[$i]}" "${M_DST[$i]}"
    manifest_check "${M_KEY[$i]}" "${M_KIND[$i]}" "${M_DST[$i]}"
    phase "$g" "done" "final:${M_KEY[$i]}"
  done < <(entries "$g")
}
cmd_verify() {
  local g=$1 i view
  group_ok "$g"; kind_inputs_ok "$g"
  if ((FROM_SNAPSHOT)); then [[ $CONFIRM == "$g" ]] || die "--from-snapshot creates a snapshot; add --confirm $g"; fi
  while read -r i; do
    check_real_paths "$i"
    view=${M_SRC[$i]}
    if ((FROM_SNAPSHOT)); then view=$(make_snapshot "$i"); fi
    content_verify "${M_KEY[$i]}" "$view" "${M_DST[$i]}"
    manifest_check "${M_KEY[$i]}" "${M_KIND[$i]}" "${M_DST[$i]}"
  done < <(entries "$g")
}
cmd_snap_clean() { # only snapshots this script recorded: same path, same UUID, read-only
  require_confirm snap-clean; no_active_copy
  [[ -f $STATE/snapshots.list ]] || { log "no snapshots recorded"; return 0; }
  local s u now
  while read -r s u; do
    [[ -n $s ]] || continue
    if [[ ! -e $s ]]; then log "already gone: $s"; continue; fi
    [[ $s == */@bifrost/td444-snap/* && $(realpath -e "$s") == "$s" ]] || die "refusing $s: not a recorded snapshot path"
    now=$(btrfs subvolume show "$s" 2> /dev/null | awk '$1 == "UUID:" { print $2; exit }')
    [[ -n $u && $now == "$u" ]] || die "refusing $s: UUID '$now' is not the recorded '$u'"
    [[ $(btrfs property get -ts "$s" ro 2> /dev/null) == ro=true ]] || die "refusing $s: not read-only"
    btrfs subvolume delete "$s" > /dev/null || die "could not delete $s"
    log "deleted snapshot $s"
  done < "$STATE/snapshots.list"
  mv "$STATE/snapshots.list" "$STATE/snapshots.list.done-$(date -u +%Y%m%dT%H%M%SZ)"
}

# ---------------------------------------------------------------- exports (§2)
norm_exports() { # "client option" lines of one exported path, sorted
  exportfs -v | awk -v want="$1" '
    function emit(s,   e, c, o, n, a, k) {
      while (match(s, /[^ \t()]+\([^)]*\)/)) {
        e = substr(s, RSTART, RLENGTH); s = substr(s, RSTART + RLENGTH)
        c = substr(e, 1, index(e, "(") - 1); o = substr(e, index(e, "(") + 1); sub(/\)$/, "", o)
        n = split(o, a, ","); for (k = 1; k <= n; k++) if (path == want) print c, a[k]
      }
    }
    /^\// { path = $1; emit(substr($0, length($1) + 1)); next }
    { emit($0) }' | LC_ALL=C sort -u
}
dir_attrs() { # dir_attrs <dir> <out>: mode/owner, ACL, xattrs; fails when any of them cannot be read
  local mo acl xat
  rm -f "$2"
  mo=$(stat -c '%a %u %g' "$1") || { log "cannot read the mode and owner of $1"; return 1; }
  # %a prints no leading zeros: a UGOS share root is mode 000 (access by ACL) and reads "0".
  [[ $mo =~ ^[0-7]{1,4}\ [0-9]+\ [0-9]+$ ]] || { log "unexpected mode and owner '$mo' of $1"; return 1; }
  acl=$(getfacl -n -p --omit-header "$1") || { log "cannot read the ACL of $1"; return 1; }
  xat=$(getfattr -d -m - --absolute-names "$1") || { log "cannot read the xattrs of $1"; return 1; }
  { printf 'mode-owner %s\n' "$mo"
    printf '%s\n' "$acl" | sed 's/^/acl /'
    # system.* (POSIX ACLs, UGOS's own ACL system.ugacl_self) decide access and are compared;
    # user.* and ug.* are UGOS's settings and bookkeeping (hide in Network, quota version,
    # archive bit): kept as meta lines, shown but not compared.
    printf '%s\n' "$xat" | grep -v '^# file' | sed '/^$/d; s/^system\./xattr system./; /^xattr /!s/^/meta /' || true
  } > "$2"
}
cmd_exports() {
  command -v exportfs > /dev/null && command -v getfacl > /dev/null && command -v getfattr > /dev/null \
    || die "exportfs, getfacl and getfattr are needed (stop and check, §2)"
  local ref p bad=0 a b
  ref=$(norm_exports "$EXPORT_REF")
  [[ -n $ref ]] || die "$EXPORT_REF is not exported"
  a=$(mktemp); b=$(mktemp)
  dir_attrs "$EXPORT_REF" "$a" || die "share root $EXPORT_REF: attributes unreadable (§2: stop and check)"
  for p in "${EXPORT_NEW[@]}"; do
    if diff <(printf '%s\n' "$ref") <(norm_exports "$p") > /dev/null; then
      log "export $p: same clients and options as $EXPORT_REF"
    else
      log "export $p differs from $EXPORT_REF:"; diff <(printf '%s\n' "$ref") <(norm_exports "$p") || true; bad=1
    fi
    if ! dir_attrs "$p" "$b"; then log "share root $p: attributes unreadable"; bad=1
    elif diff <(grep -v '^meta ' "$a") <(grep -v '^meta ' "$b") > /dev/null; then
      log "share root $p: mode, owner, ACL and xattrs match"
      diff <(grep '^meta ' "$a") <(grep '^meta ' "$b") > /dev/null \
        || { log "share root $p: UGOS settings differ from $EXPORT_REF (not access; noted):"; diff <(grep '^meta ' "$a") <(grep '^meta ' "$b") || true; }
    else log "share root $p differs:"; diff <(grep -v '^meta ' "$a") <(grep -v '^meta ' "$b") || true; bad=1
    fi
    namei -l "$p" || true
  done
  rm -f "$a" "$b"
  ((bad == 0)) || die "exports or share roots differ or cannot be read (§2)"
}

# shellcheck source=td444-minio.sh
. "$SCRIPT_DIR/td444-minio.sh"

case $CMD in
  check-pkg) check_pkg ;;
  map-check) load_map; log "map ${MAP}: ${#M_KEY[@]} lines pass the per-line and whole-map rules" ;;
  exports) cmd_exports ;;
  temps) read_temps; log "highest SSD temperature: ${TEMP_MAX:-none} °C ($TEMP_N of $TEMP_SENSORS sensors read)"
         for h in "$HWMON"/hwmon*; do if [[ $(cat "$h/name" 2> /dev/null) == "$TEMP_NAME" ]]; then printf '%s %s\n' "$h" "$(cat "$h/temp1_input" 2> /dev/null || echo unreadable)"; fi; done ;;
  status) [[ -n $ARG1 ]] || usage; cat "$(phase_file "$ARG1")" ;;
  identity-record) load_map; require_confirm "$ARG1"; check_pkg; identity_record "$ARG1" ;;
  identity-check) load_map; identity_check "$ARG1" ;;
  pre) load_map; cmd_pre "$ARG1" ;;
  final) load_map; cmd_final "$ARG1" ;;
  verify) load_map; cmd_verify "$ARG1" ;;
  snap-clean) cmd_snap_clean ;;
  minio-m2) load_map; cmd_minio ;;
  minio-*) cmd_minio ;;
  *) usage ;;
esac
log "done: $CMD ${ARG1:-}"
