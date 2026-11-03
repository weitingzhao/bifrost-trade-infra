#!/usr/bin/env bash
# TD-444 step 5: copy, verify and cut over the NAS data onto the SSD RAID1 (runbook §2, §3.3–§3.7, §4).
#
# Runs on the NAS as root, from the unpacked material package (runbook §3.2); the MinIO stages
# live in td444-minio.sh next to it (sourced):
#   sudo bash <pkg>/scripts/nas/td444-move.sh --pkg <pkg> --sums <pkg>/../SHA256SUMS --map <private map> <command> ...
# The map (private, never in git; template: td444-map.example) lists every copy as
#   <group> <key> <kind> <source dir> <target dir> [<snapshot root>]
# Paths must sit under the allowed roots below; the map is the allow-list.
#
# Read-only commands (write only their own log):
#   check-pkg                      verify the package against SHA256SUMS
#   exports                        compare the new NFS exports and share roots with k3s-hot (§2)
#   identity-check <group>         compare the mount identity with the recorded one (§2)
#   verify <group> [--from-snapshot]   full content verification + own manifests (§3.3); prints T_c
#   status <group|minio-RUN>       print the phase file
#   temps                          print the SSD temperatures (hwmon)
#   minio-eligibility --run-id R   may this run fall back to A? (§4 group 6 eligibility table)
#   minio-wal-layout --data DIR    list the WAL objects layout (§4 group 6 precondition)
#   minio-base-check --run-id R --data DIR   M6.1: every object in minio.base still present
#   minio-continuity --run-id R --range FILE --data DIR   M6.2: every segment L..U present
# Writing commands (each needs --confirm <the group, or the word given in its help line>):
#   identity-record <group>        record the mount identity (state only)
#   pre <group> [--from-snapshot]  copy, add only, never delete (§3.3)
#   final <group>                  the only --delete pass: identity, path and delete-list checks,
#                                  typed "yes", copy, full verification (§3.3)
#   snap-clean                     delete the snapshots this script created   (--confirm snap-clean)
#   minio-m0 .. minio-m4b, minio-m4a-stop, minio-rollback-a, minio-readback   (--confirm minio, --run-id R)
#
# Every step appends attempt/done/fail lines to a phase file and logs to $STATE/logs/.
# Long copies run under the temperature guard: pause at --temp-pause (72 °C), resume at or
# below --temp-resume (65 °C), and pause when no SSD temperature could be read for
# --temp-missing seconds (180). --bwlimit and --timeout pass through to every copy.
set -euo pipefail
umask 077

PROG=${0##*/}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE=/volume1/@bifrost/td444
MAP="" PKG="" SUMS="" CONFIRM="" RUN_ID="" RANGE="" DATA="" METHOD="mc"
BWLIMIT="" TIMEOUT=0 FROM_SNAPSHOT=0 EXPECT_COMPOSE_SHA=""
TEMP_PAUSE=72 TEMP_RESUME=65 TEMP_MISSING=180 TEMP_POLL=30 TEMP_NAME=nvme
HWMON=${TD444_HWMON:-/sys/class/hwmon}   # tests point this at a fake tree
COMPOSE_DIR=/volume1/docker/minio-backup CONTAINER=minio-backup BUCKET=bifrost-postgres-backup
SRC_ROOTS=(/volume1/k3s-hot /volume1/k3s-cold /volume2/k3s-fast /volume2/minio-backup)
DST_ROOTS=(/volume2/k3s-fast /volume2/minio-backup /volume1/k3s-cold/td444-recovery /volume1/minio-recovery-td444)
EXPORT_REF=/volume1/k3s-hot
EXPORT_NEW=(/volume2/k3s-fast /volume2/market-archive-backup)

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FAIL: $*"; exit 1; }
usage() { sed -n '2,33p' "$0"; exit 2; }

# ---------------------------------------------------------------- arguments
ARGS=()
while (($#)); do
  case "$1" in
    --map) MAP=$2; shift 2 ;;
    --pkg) PKG=$2; shift 2 ;;
    --sums) SUMS=$2; shift 2 ;;
    --state) STATE=$2; shift 2 ;;
    --confirm) CONFIRM=$2; shift 2 ;;
    --run-id) RUN_ID=$2; shift 2 ;;
    --range) RANGE=$2; shift 2 ;;
    --data) DATA=$2; shift 2 ;;
    --method) METHOD=$2; shift 2 ;;
    --bwlimit) BWLIMIT=$2; shift 2 ;;
    --timeout) TIMEOUT=$2; shift 2 ;;
    --from-snapshot) FROM_SNAPSHOT=1; shift ;;
    --expect-compose-sha256) EXPECT_COMPOSE_SHA=$2; shift 2 ;;
    --temp-pause) TEMP_PAUSE=$2; shift 2 ;;
    --temp-resume) TEMP_RESUME=$2; shift 2 ;;
    --temp-missing) TEMP_MISSING=$2; shift 2 ;;
    --temp-poll) TEMP_POLL=$2; shift 2 ;;
    --compose-dir) COMPOSE_DIR=$2; shift 2 ;;
    -h|--help) usage ;;
    --*) die "unknown option $1" ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
((${#ARGS[@]})) || usage
CMD=${ARGS[0]}
ARG1=${ARGS[1]:-}
for v in "$TIMEOUT" "$TEMP_PAUSE" "$TEMP_RESUME" "$TEMP_MISSING" "$TEMP_POLL"; do
  [[ $v =~ ^[0-9]+$ ]] || die "--timeout and --temp-* take whole numbers"
done
((TEMP_RESUME < TEMP_PAUSE)) || die "--temp-resume must be below --temp-pause"
[[ -z $BWLIMIT || $BWLIMIT =~ ^[0-9]+[KMG]?$ ]] || die "--bwlimit must look like 200M"
[[ -z $RUN_ID || $RUN_ID =~ ^[A-Za-z0-9-]{1,40}$ ]] || die "--run-id: letters, digits, dashes"
((EUID == 0)) || die "run as root (sudo)"

# ---------------------------------------------------------------- logging and phases
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

# ---------------------------------------------------------------- package
check_pkg() {
  [[ -n $PKG && -n $SUMS ]] || die "--pkg and --sums are required"
  log "this script: $(sha256sum "$0" | cut -d' ' -f1), td444-minio.sh: $(sha256sum "$SCRIPT_DIR/td444-minio.sh" | cut -d' ' -f1)"
  (cd "$PKG" && sha256sum -c --quiet "$SUMS") || die "package does not match $SUMS"
  log "package matches $SUMS"
}

# ---------------------------------------------------------------- map
M_GROUP=() M_KEY=() M_KIND=() M_SRC=() M_DST=() M_SNAP=()
under() { # under <path> <root>...
  local p=$1 r; shift
  for r in "$@"; do [[ $p == "$r"/* ]] && return 0; done
  return 1
}
load_map() {
  [[ -n $MAP && -r $MAP ]] || die "--map <file> is required"
  local n=0 g k kind s d snap extra
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
    [[ $s != "$d" && $d != "$s"/* && $s != "$d"/* ]] || die "map line $n: source and target overlap"
    [[ -z ${snap:-} || $s == "$snap" || $s == "$snap"/* ]] || die "map line $n: snapshot root does not contain the source"
    M_GROUP+=("$g") M_KEY+=("$k") M_KIND+=("$kind") M_SRC+=("$s") M_DST+=("$d") M_SNAP+=("${snap:-}")
  done < "$MAP"
  ((${#M_KEY[@]})) || die "map is empty"
}
entries() { # entries <group>: indexes; "all" = every group except *-recovery
  local i out=()
  for i in "${!M_KEY[@]}"; do
    if [[ ${M_GROUP[$i]} == "$1" || ($1 == all && ${M_GROUP[$i]} != *-recovery) ]]; then out+=("$i"); fi
  done
  ((${#out[@]})) || die "no map entries for group $1"
  printf '%s\n' "${out[@]}"
}
group_ok() { entries "$1" > /dev/null; }  # dies in the main shell when the group is empty
check_real_paths() { # the source must exist with no symlink in it; the target's parent must
  local s=${M_SRC[$1]} d=${M_DST[$1]}
  [[ -d $s && $(realpath -e "$s") == "$s" ]] || die "${M_KEY[$1]}: source $s is missing or not a real path"
  [[ -d $(dirname "$d") && $(realpath -m "$d") == "$d" ]] || die "${M_KEY[$1]}: target parent of $d is missing or a link"
}
make_dst_root() { # create a recovery root (an allowed target root) when its parent exists
  local parent r
  parent=$(dirname "${M_DST[$1]}")
  for r in "${DST_ROOTS[@]}"; do
    if [[ $parent == "$r" && ! -d $r && -d $(dirname "$r") ]]; then mkdir -m 700 "$r"; log "created $r"; fi
  done
}
nested_subvolume() { find "$1" -mindepth 1 -xdev -type d -inum 256 -print -quit 2>/dev/null; }

# ---------------------------------------------------------------- mount identity (§2)
ident_of() { # SOURCE FSTYPE ro|rw UUID subvolid, of the path or its nearest existing parent
  local p=$1 opts
  while [[ ! -e $p ]]; do p=$(dirname "$p"); done
  local src fstype uuid
  read -r src fstype opts uuid < <(findmnt -no SOURCE,FSTYPE,OPTIONS,UUID -T "$p")
  [[ ,$opts, == *,rw,* ]] && opts=rw || opts=ro
  printf '%s %s %s %s %s' "$src" "$fstype" "$opts" "${uuid:--}" "$(btrfs inspect-internal rootid "$p" 2>/dev/null || echo -)"
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
identity_check() {
  local i rec="$STATE/identity/$1.rec" now need have bad=0
  group_ok "$1"
  [[ -f $rec ]] || die "no identity record for $1 (identity-record $1 first)"
  while read -r i; do
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

# ---------------------------------------------------------------- temperature guard and copies
max_temp() { # highest SSD temperature in °C, or nothing when none can be read
  local h t best=""
  for h in "$HWMON"/hwmon*; do
    [[ -r $h/name && $(cat "$h/name") == "$TEMP_NAME" && -r $h/temp1_input ]] || continue
    t=$(cat "$h/temp1_input" 2>/dev/null) || continue
    [[ $t =~ ^[0-9]+$ ]] || continue
    t=$((t / 1000))
    [[ -z $best || $t -gt $best ]] && best=$t
  done
  printf '%s' "$best"
}
guarded() { # run "$@" in its own process group under the temperature guard and --timeout
  local pid rc=0 start=$SECONDS paused=0 missing_since="" last_poll=-1000000 t
  setsid "$@" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if ((TIMEOUT > 0 && SECONDS - start >= TIMEOUT)); then
      log "timeout after ${TIMEOUT}s: stopping the copy" >&2
      kill -CONT -- "-$pid" 2>/dev/null || true
      kill -TERM -- "-$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    if ((SECONDS - last_poll >= TEMP_POLL)); then
      last_poll=$SECONDS
      t=$(max_temp)
      if [[ -z $t ]]; then
        [[ -n $missing_since ]] || missing_since=$SECONDS
        if ((paused == 0 && SECONDS - missing_since >= TEMP_MISSING)); then
          kill -STOP -- "-$pid"; paused=1; log "no SSD temperature for ${TEMP_MISSING}s: copy paused" >&2
        fi
      else
        missing_since=""
        if ((paused == 0 && t >= TEMP_PAUSE)); then
          kill -STOP -- "-$pid"; paused=1; log "SSD at ${t} °C (>= ${TEMP_PAUSE}): copy paused" >&2
        elif ((paused == 1 && t <= TEMP_RESUME)); then
          kill -CONT -- "-$pid"; paused=0; log "SSD at ${t} °C (<= ${TEMP_RESUME}): copy resumed" >&2
        fi
      fi
    fi
    sleep 1
  done
  wait "$pid" || rc=$?
  return "$rc"
}
rsync_opts() { printf '%s\n' -aHAX --numeric-ids ${BWLIMIT:+--bwlimit="$BWLIMIT"}; }

make_snapshot() { # make_snapshot <entry>: read-only snapshot of the snapshot root; prints the view of the source
  local i=$1 root=${M_SNAP[$1]} mnt snapdir snap
  [[ -n $root ]] || die "${M_KEY[$i]}: no snapshot root in the map"
  btrfs subvolume show "$root" >/dev/null 2>&1 || die "${M_KEY[$i]}: $root is not a btrfs subvolume"
  [[ -z $(nested_subvolume "${M_SRC[$i]}") ]] || die "${M_KEY[$i]}: nested subvolume under ${M_SRC[$i]}; refusing"
  mnt=$(findmnt -no TARGET -T "$root")
  snapdir="$mnt/@bifrost/td444-snap"
  mkdir -p "$snapdir"
  snap="$snapdir/${M_KEY[$i]}-$(date -u +%Y%m%dT%H%M%SZ)"
  btrfs subvolume snapshot -r "$root" "$snap" >/dev/null
  printf '%s\n' "$snap" >> "$STATE/snapshots.list"
  log "${M_KEY[$i]}: read-only snapshot $snap" >&2
  printf '%s%s' "$snap" "${M_SRC[$i]#"$root"}"
}

# full content check: exit 0 and an empty itemize list, or failure (§3.3)
content_verify() { # content_verify <key> <source view> <target>
  local out rc=0 t0=$SECONDS
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

manifest_check() { # the backup's own checksums (§3.3, §5.1)
  local key=$1 kind=$2 d=$3 l run bad=0
  case $kind in
    logical|finance)
      l=$(cat "$d/LATEST") || die "$key: no LATEST"
      [[ $(cat "$d/daily/$l/STATUS") == OK ]] || die "$key: LATEST run $l is not STATUS=OK"
      (cd "$d/daily/$l" && sha256sum -c --quiet SHA256SUMS) || die "$key: SHA256SUMS of $l failed"
      log "$key: LATEST $l is OK and its SHA256SUMS verify" ;;
    gitea)
      l=$(cat "$d/LATEST") || die "$key: no LATEST"
      [[ $(cat "$d/$l/STATUS") == OK ]] || die "$key: LATEST run $l is not STATUS=OK"
      (cd "$d/$l" && grep -v '^#' SHA256SUMS | sha256sum -c --quiet -) || die "$key: SHA256SUMS of $l failed"
      log "$key: LATEST $l is OK and its SHA256SUMS verify" ;;
    cluster-state)
      for run in "$d"/daily/????-??-??; do
        [[ -d $run ]] || continue
        [[ $(cat "$run/STATUS" 2>/dev/null) == OK ]] || { log "$key: $run has no STATUS=OK"; bad=1; continue; }
        cs_manifest "$run" || bad=1
      done
      for run in "$d"/monthly/????-??; do
        [[ -d $run ]] || continue
        cs_monthly_files "$run" || bad=1
        cs_manifest "$run" || bad=1
      done
      ((bad == 0)) || die "$key: cluster-state MANIFEST check failed"
      log "$key: every daily and monthly MANIFEST verifies" ;;
    registry)
      while IFS= read -r -d '' f; do
        local want got
        want=$(basename "$(dirname "$f")")
        got=$(sha256sum "$f" | cut -d' ' -f1)
        [[ $want == "$got" ]] || { log "$key: blob $want hashes to $got"; bad=1; }
      done < <(find "$d/docker/registry/v2/blobs/sha256" -mindepth 3 -maxdepth 3 -type f -name data -print0)
      ((bad == 0)) || die "$key: registry blob self-check failed"
      log "$key: every blob hashes to its directory name" ;;
    monitoring|minio|plain) ;;
  esac
}
cs_manifest() { # every "file" line: ciphertext bytes and sha256 match (backup.sh:270-282)
  local run=$1 name bytes sum
  [[ -f $run/MANIFEST ]] || { log "$run: no MANIFEST"; return 1; }
  grep -q '^timestamp [0-9]' "$run/MANIFEST" || { log "$run: MANIFEST has no timestamp"; return 1; }
  while read -r name bytes sum; do
    [[ -f $run/$name ]] || { log "$run: $name missing"; return 1; }
    [[ $(stat -c %s "$run/$name") == "$bytes" ]] || { log "$run: $name size differs"; return 1; }
    [[ $(sha256sum "$run/$name" | cut -d' ' -f1) == "$sum" ]] || { log "$run: $name sha256 differs"; return 1; }
  done < <(awk '$1 == "file" { b = ""; s = ""; for (i = 3; i < NF; i++) { if ($i == "ciphertext_bytes") b = $(i+1); if ($i == "ciphertext_sha256") s = $(i+1) } print $2, b, s }' "$run/MANIFEST")
}
cs_monthly_files() { # monthly: exactly four ciphertexts + MANIFEST, no STATUS (backup.sh:299-338)
  local run=$1 names
  names=$(cd "$run" && ls -1 | LC_ALL=C sort | tr '\n' ' ')
  [[ $names =~ ^MANIFEST\ etcd-snapshot-[^\ ]+\.age\ platform-state\.yaml\.age\ secrets\.yaml\.age\ server-token\.age\ $ ]] \
    || { log "$run: unexpected file set: $names"; return 1; }
}

# ---------------------------------------------------------------- pre / final / verify
cmd_pre() {
  local g=$1 i view
  require_confirm "$g"; check_pkg; group_ok "$g"
  while read -r i; do
    make_dst_root "$i"
    check_real_paths "$i"
    mkdir -p "${M_DST[$i]}"
    view=${M_SRC[$i]}
    phase "$g" attempt "pre:${M_KEY[$i]}"
    if ((FROM_SNAPSHOT)); then view=$(make_snapshot "$i"); fi
    local rc=0
    # shellcheck disable=SC2046
    guarded rsync $(rsync_opts) --log-file="$STATE/logs/rsync-pre-${M_KEY[$i]}.log" "$view/" "${M_DST[$i]}/" || rc=$?
    if ((rc != 0)); then phase "$g" fail "pre:${M_KEY[$i]}" "rsync $rc"; die "${M_KEY[$i]}: pre copy exited $rc"; fi
    if ((FROM_SNAPSHOT)); then content_verify "${M_KEY[$i]}" "$view" "${M_DST[$i]}"; fi
    phase "$g" "done" "pre:${M_KEY[$i]}"
  done < <(entries "$g")
}

cmd_final() {
  local g=$1 i dl n rc
  require_confirm "$g"; check_pkg; group_ok "$g"
  identity_check "$g"
  while read -r i; do
    check_real_paths "$i"
    [[ -d ${M_DST[$i]} ]] || die "${M_KEY[$i]}: target ${M_DST[$i]} missing; run pre first"
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
  group_ok "$g"
  while read -r i; do
    check_real_paths "$i"
    view=${M_SRC[$i]}
    if ((FROM_SNAPSHOT)); then
      [[ $CONFIRM == "$g" ]] || die "--from-snapshot creates a snapshot; add --confirm $g"
      view=$(make_snapshot "$i")
    fi
    content_verify "${M_KEY[$i]}" "$view" "${M_DST[$i]}"
    manifest_check "${M_KEY[$i]}" "${M_KIND[$i]}" "${M_DST[$i]}"
  done < <(entries "$g")
}

cmd_snap_clean() {
  require_confirm snap-clean
  [[ -f $STATE/snapshots.list ]] || { log "no snapshots recorded"; return 0; }
  local s
  while read -r s; do
    [[ $s == */@bifrost/td444-snap/* ]] || die "refusing to delete $s"
    if [[ -d $s ]]; then btrfs subvolume delete "$s"; fi
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
dir_attrs() {
  printf 'mode-owner %s\n' "$(stat -c '%a %u %g' "$1")"
  getfacl -n -p --omit-header "$1" 2>/dev/null | sed 's/^/acl /' || return 1
  getfattr -d -m - --absolute-names "$1" 2>/dev/null | grep -v '^# file' | sed 's/^/xattr /' || true
}
cmd_exports() {
  command -v exportfs >/dev/null && command -v getfacl >/dev/null || die "exportfs and getfacl are needed (stop and check, §2)"
  local ref p bad=0
  ref=$(norm_exports "$EXPORT_REF")
  [[ -n $ref ]] || die "$EXPORT_REF is not exported"
  for p in "${EXPORT_NEW[@]}"; do
    if diff <(printf '%s\n' "$ref") <(norm_exports "$p") > /dev/null; then
      log "export $p: same clients and options as $EXPORT_REF"
    else
      log "export $p differs from $EXPORT_REF:"; diff <(printf '%s\n' "$ref") <(norm_exports "$p") || true; bad=1
    fi
    if diff <(dir_attrs "$EXPORT_REF") <(dir_attrs "$p") > /dev/null; then
      log "share root $p: mode, owner, ACL and xattrs match"
    else
      log "share root $p differs:"; diff <(dir_attrs "$EXPORT_REF") <(dir_attrs "$p") || true; bad=1
    fi
    namei -l "$p" || true
  done
  ((bad == 0)) || die "exports or share roots differ (§2)"
}

# ---------------------------------------------------------------- MinIO stages (§4 group 6)
# shellcheck source=td444-minio.sh
. "$SCRIPT_DIR/td444-minio.sh"

# ---------------------------------------------------------------- dispatch
case $CMD in
  check-pkg) check_pkg ;;
  exports) cmd_exports ;;
  temps) log "highest SSD temperature: $(max_temp) °C"; for h in "$HWMON"/hwmon*; do [[ $(cat "$h/name" 2>/dev/null) == "$TEMP_NAME" ]] && printf '%s %s\n' "$h" "$(cat "$h/temp1_input")"; done; true ;;
  status) [[ -n $ARG1 ]] || usage; cat "$(phase_file "$ARG1")" ;;
  identity-record) load_map; require_confirm "$ARG1"; identity_record "$ARG1" ;;
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
