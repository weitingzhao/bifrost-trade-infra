#!/usr/bin/env bash
# Weekly roll-up of the SSD backups onto the RAID5 HDDs (TD-444 step 5 runbook §5.1, §5.3, §5.4).
#
# Runs on the NAS as root from bifrost-backup-rollup.timer (Sunday 12:30 UTC), or by hand:
#   sudo /volume1/@bifrost/backup-rollup/rollup.sh [--conf FILE] [--dest DIR] [--now]
# minio-readback.sh (the MinIO read-back), backup-checks.sh (the completion checks shared
# with td444-move.sh) and registry-check.py (its registry graph check, needs python3) sit
# next to it.
# Config (rollup.conf, template rollup.conf.example): one source per line
#   <name> <kind> <source dir> <snapshot root (a btrfs subvolume)> <prune on|off>
# A registry source also needs <config dir>/<name>.digests: the digests that must stay
# restorable, one <repository>@sha256:<hex> per line. A minio source needs two settings
# lines, MINIO_IMAGE=<the live MinIO's image ID or digest> and MINIO_CREDENTIALS=<root-only
# file>, and docker: its objects are read back through a throwaway MinIO (minio-readback.sh).
#
# One run, under flock, produces one generation stamped <UTC>:
#   1. config check: absolute real paths, no two sources overlapping, none inside --dest;
#      --dest and every snapshot root sit on their expected mounts; space on both volumes;
#   2. per source a read-only snapshot of its subvolume (never an online copy); a source
#      that is itself a subvolume, or holds one, is rejected;
#   3. completion is judged from the data in the snapshot (backup-checks.sh; MinIO by reading
#      its objects back, minio-readback.sh), positive evidence only; a backup in progress
#      waits 15 minutes until --deadline-utc;
#   4. rsync -aHAX -c --link-dest=<previous generation> into <name>/.partial-<stamp>, then a
#      full check (rsync -c -n --delete --itemize-changes: exit 0 and an empty list);
#   5. only when every source passed: GENERATION.json, every .partial renamed, then the
#      commit marker .committed/<stamp>; a generation without it is not published. Then
#      every source's last-success time moves together;
#   6. after the commit, for sources whose prune switch is on: keep the newest 8 committed
#      generations (the newest never goes). A failed run deletes nothing published;
#   7. cleanup of what this run created (run.state): throwaway containers first, scratch
#      snapshots only once their container is gone; snapshots are deleted only when their
#      UUID and read-only flag match; what cannot be removed stays in pending-cleanup.list;
#      on failure one .partial and one snapshot are kept for diagnosis, at most 7 days;
#   8. metrics through the node-exporter textfile collector, written atomically; every
#      source ever configured stays "expected" until --retire-source, so alerts still fire.
set -euo pipefail
umask 077
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONF=/volume1/@bifrost/backup-rollup/rollup.conf
DEST=/volume1/backup-weekly DEST_MOUNT=/volume1 SRC_MOUNT=/volume2
STATE=/volume1/@bifrost/backup-rollup/state
TEXTFILE=/volume1/@bifrost/textfile/backup-rollup.prom
KEEP=8 DEADLINE_UTC=16:30 RETRY=900 NOW=0 RETIRE="" MINIO_START_TIMEOUT_ARG=120   # 16:30 UTC = 10:30 CST

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "FAIL: $*"; exit 1; }
while (($#)); do
  case $1 in
    --conf) CONF=$2; shift 2 ;;             --dest) DEST=$2; shift 2 ;;
    --dest-mount) DEST_MOUNT=$2; shift 2 ;; --src-mount) SRC_MOUNT=$2; shift 2 ;;
    --state) STATE=$2; shift 2 ;;           --textfile) TEXTFILE=$2; shift 2 ;;
    --keep) KEEP=$2; shift 2 ;;             --deadline-utc) DEADLINE_UTC=$2; shift 2 ;;
    --retry) RETRY=$2; shift 2 ;;           --now) NOW=1; shift ;;
    --retire-source) RETIRE=$2; shift 2 ;;
    --minio-start-timeout) MINIO_START_TIMEOUT_ARG=$2; shift 2 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done
((EUID == 0)) || die "run as root"
[[ $KEEP =~ ^[1-9][0-9]*$ && $RETRY =~ ^[0-9]+$ && $DEADLINE_UTC =~ ^[0-2][0-9]:[0-5][0-9]$ && $MINIO_START_TIMEOUT_ARG =~ ^[1-9][0-9]*$ ]] \
  || die "bad --keep/--retry/--deadline-utc/--minio-start-timeout"
if [[ -f $HERE/backup-checks.sh ]]; then CHECKS=$HERE/backup-checks.sh; else CHECKS=$HERE/../backup-checks.sh; fi
# shellcheck source=../backup-checks.sh
. "$CHECKS"
# shellcheck source=minio-readback.sh
. "$HERE/minio-readback.sh"
MINIO_START_TIMEOUT=$MINIO_START_TIMEOUT_ARG
mkdir -p "$STATE" "$DEST/.committed" "$(dirname "$TEXTFILE")"
chmod 700 "$STATE"
exec 9> "$STATE/lock"
flock -n 9 || die "another roll-up is running"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUNSTATE="$STATE/run.state"
exec 2> >(tee -a "$STATE/run-$STAMP.log" >&2)
DEADLINE=$(date -u -d "$(date -u +%Y-%m-%d) $DEADLINE_UTC" +%s)
if [[ -n $RETIRE ]]; then
  grep -Fxv "$RETIRE" "$STATE/expected.list" > "$STATE/expected.list.new" || true
  mv "$STATE/expected.list.new" "$STATE/expected.list"; log "retired $RETIRE from the expected sources"; exit 0
fi
# a leftover run.state belongs to an earlier run: stop before any trap could touch it
[[ ! -e $RUNSTATE ]] || die "$RUNSTATE exists: an earlier run did not clean up; check it by hand"

# ---------------------------------------------------------------- config (S2)
N=() K=() SRC=() ROOT=() PRUNE=()
CONFDIR=$(dirname "$CONF")
overlap() { [[ $1 == "$2" || $1 == "$2"/* || $2 == "$1"/* ]]; }
while read -r name kind src root prune extra; do
  [[ -z ${name:-} || $name == \#* ]] && continue
  case $name in   # settings of the MinIO read-back (minio-readback.sh)
    MINIO_IMAGE=*) [[ -z ${kind:-} ]] || die "bad MINIO_IMAGE line"; MINIO_IMAGE=${name#*=}; continue ;;
    MINIO_CREDENTIALS=*) [[ -z ${kind:-} ]] || die "bad MINIO_CREDENTIALS line"; MINIO_CREDENTIALS=${name#*=}; continue ;;
  esac
  [[ -z ${extra:-} && $name =~ ^[a-z][a-z0-9-]*$ ]] || die "bad config line for ${name:-?}"
  case $kind in logical|finance|gitea|cluster-state|registry|minio) ;; *) die "$name: unknown kind $kind" ;; esac
  [[ $prune == on || $prune == off ]] || die "$name: prune must be on or off"
  for p in "$src" "$root"; do
    [[ $p == /* && $p != */ && $p != *..* && -d $p && $(realpath -e "$p") == "$p" ]] || die "$name: $p is not an absolute real directory"
  done
  [[ $src == "$root" || $src == "$root"/* ]] || die "$name: source is not inside its snapshot root"
  ! overlap "$src" "$DEST" || die "$name: source and --dest overlap"
  for i in "${!N[@]}"; do
    [[ ${N[$i]} != "$name" ]] || die "source name $name is used twice"
    ! overlap "${SRC[$i]}" "$src" || die "sources ${N[$i]} and $name overlap"
  done
  [[ $(findmnt -no TARGET -T "$root") == "$SRC_MOUNT" ]] || die "$name: $root is not on $SRC_MOUNT"
  [[ $kind != registry || -s $CONFDIR/$name.digests ]] || die "$name: a registry source needs $CONFDIR/$name.digests (<repository>@sha256:<hex> per line)"
  N+=("$name") K+=("$kind") SRC+=("$src") ROOT+=("$root") PRUNE+=("$prune")
done < "$CONF"
((${#N[@]})) || die "no sources in $CONF"
[[ $(findmnt -no TARGET -T "$DEST") == "$DEST_MOUNT" ]] || die "$DEST is not on $DEST_MOUNT"
for _k in "${K[@]}"; do if [[ $_k == minio ]]; then minio_config_ok; break; fi; done
touch "$STATE/expected.list"
for n in "${N[@]}"; do grep -Fxq "$n" "$STATE/expected.list" || echo "$n" >> "$STATE/expected.list"; done

# ---------------------------------------------------------------- metrics
published() { # committed generations of a source, oldest first
  local d="$DEST/$1" g
  [[ -d $d ]] || return 0
  for g in $(find "$d" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*T*Z' -printf '%f\n' | LC_ALL=C sort); do
    if [[ $g =~ ^[0-9]{8}T[0-9]{6}Z$ && -f $d/$g/GENERATION.json && -f $DEST/.committed/$g ]]; then echo "$g"; fi
  done
  return 0
}
configured() { local i; for i in "${!N[@]}"; do [[ ${N[$i]} == "$1" ]] && { echo "$i"; return 0; }; done; return 1; }
write_metrics() {
  local n i tmp="$TEXTFILE.$$.tmp" ts
  {
    for m in "last_success_timestamp_seconds Last committed generation with this source verified" \
             "last_run_ok 1 when the last run passed this source and committed, else 0" \
             "source_enabled 1 for every source in rollup.conf" \
             "source_expected 1 for every source ever configured and not retired" \
             "generation_bytes Apparent bytes of the newest committed generation" \
             "generations Committed generations kept" "prune_enabled 1 when old generations may be deleted"; do
      echo "# HELP bifrost_nas_backup_rollup_${m%% *} ${m#* }"; echo "# TYPE bifrost_nas_backup_rollup_${m%% *} gauge"
    done
    while read -r n; do
      [[ -n $n ]] || continue
      echo "bifrost_nas_backup_rollup_source_expected{source=\"$n\"} 1"
      i=$(configured "$n") || continue
      ts=$(cat "$STATE/last_success.$n" 2> /dev/null || true)
      [[ -n $ts ]] && echo "bifrost_nas_backup_rollup_last_success_timestamp_seconds{source=\"$n\"} $ts"
      echo "bifrost_nas_backup_rollup_last_run_ok{source=\"$n\"} $(cat "$STATE/last_run_ok.$n" 2> /dev/null || echo 0)"
      echo "bifrost_nas_backup_rollup_source_enabled{source=\"$n\"} 1"
      echo "bifrost_nas_backup_rollup_generation_bytes{source=\"$n\"} $(cat "$STATE/bytes.$n" 2> /dev/null || echo 0)"
      echo "bifrost_nas_backup_rollup_generations{source=\"$n\"} $(published "$n" | wc -l)"
      echo "bifrost_nas_backup_rollup_prune_enabled{source=\"$n\"} $([[ ${PRUNE[$i]} == on ]] && echo 1 || echo 0)"
    done < "$STATE/expected.list"
    echo "bifrost_nas_backup_rollup_last_run_timestamp_seconds $(date +%s)"
  } > "$tmp"
  chmod 644 "$tmp"; mv "$tmp" "$TEXTFILE"
}

in_progress() { # in_progress <kind> <dir>: 0 when a backup is still being written
  local d=$2 b
  case $1 in
    logical|finance) compgen -G "$d/daily/.partial-*" > /dev/null ;;
    gitea) [[ -e $d/.lock ]] || compgen -G "$d/*.partial" > /dev/null ;;
    cluster-state) compgen -G "$d/daily/.partial-*" > /dev/null || compgen -G "$d/monthly/.partial-*" > /dev/null \
                     || compgen -G "$d/daily/.old-*" > /dev/null || compgen -G "$d/monthly/.old-*" > /dev/null ;;
    registry) return 1 ;;
    minio)
      [[ -n $(find "$d/.minio.sys/multipart" -mindepth 1 -maxdepth 1 -print -quit 2> /dev/null) ]] && return 0
      while IFS= read -r b; do [[ -d $b/backup.info ]] || return 0; done < <(find "$d" -mindepth 4 -maxdepth 4 -type d -path '*/base/*' -mmin -360 2> /dev/null)
      return 1 ;;
  esac
}

# ---------------------------------------------------------------- snapshots and cleanup (S5)
record() { printf '%s %s %s\n' "$1" "$2" "${3:--}" >> "$RUNSTATE"; }
snap_uuid() { btrfs subvolume show "$1" 2> /dev/null | awk '$1 == "UUID:" { print $2; exit }'; }
snapshot_of() { # snapshot_of <i>: prints the snapshot path
  local i=$1 mnt snap uuid
  btrfs subvolume show "${ROOT[$i]}" > /dev/null 2>&1 || { log "${N[$i]}: ${ROOT[$i]} is not a subvolume"; return 1; }
  if [[ ${SRC[$i]} != "${ROOT[$i]}" ]] && btrfs subvolume show "${SRC[$i]}" > /dev/null 2>&1; then
    log "${N[$i]}: the source is itself a subvolume, not part of ${ROOT[$i]}'s snapshot; rejected"; return 1
  fi
  if [[ -n $(find "${SRC[$i]}" -mindepth 1 -xdev -type d -inum 256 -print -quit 2> /dev/null) ]]; then
    log "${N[$i]}: a nested subvolume under ${SRC[$i]}; no consistent point in time, rejected"; return 1
  fi
  mnt=$(findmnt -no TARGET -T "${ROOT[$i]}")
  mkdir -p "$mnt/@bifrost/rollup-snap"
  snap="$mnt/@bifrost/rollup-snap/${N[$i]}-$STAMP-$RANDOM"
  btrfs subvolume snapshot -r "${ROOT[$i]}" "$snap" > /dev/null || return 1
  uuid=$(snap_uuid "$snap"); [[ -n $uuid ]] || { log "$snap has no UUID"; return 1; }
  record snapshot "$snap" "$uuid"
  printf '%s' "$snap"
}
pending_add() { grep -Fxq "$1" "$STATE/pending-cleanup.list" 2> /dev/null || echo "$1" >> "$STATE/pending-cleanup.list"; }
drop_snapshot() { # drop_snapshot <path> <uuid> [ro|rw]: verified delete (rw: a scratch snapshot); a failure stays pending
  local s=$1 u=$2 mode=${3:-ro} kind=snapshot want=ro=true
  if [[ $mode == rw ]]; then kind=scratch want=ro=false; fi
  [[ -d $s ]] || return 0
  if [[ $s == */@bifrost/rollup-snap/* && $(snap_uuid "$s") == "$u" && $(btrfs property get -ts "$s" ro 2> /dev/null) == "$want" ]] \
     && btrfs subvolume delete "$s" > /dev/null 2>&1; then return 0; fi
  log "could not delete $kind $s; kept in pending-cleanup.list"
  pending_add "$kind $s $u"
}
retry_pending() { # pending-cleanup.list lines: "container <id> <run token>", "scratch|snapshot <path> <uuid>"
  # and, from the first version, "<path> <uuid>" (a read-only snapshot); any other line is kept
  [[ -s $STATE/pending-cleanup.list ]] || return 0
  local line k t u x busy=0 f=$STATE/pending-cleanup.list.retry
  mv "$STATE/pending-cleanup.list" "$f"
  while read -r k t u x; do if [[ $k == container && -z $x ]]; then drop_container "$t" "$u" || busy=1; fi; done < "$f"
  while IFS= read -r line; do
    read -r k t u x <<< "$line" || true
    [[ -n $k ]] || continue
    case "$k:${x:+extra}" in
      container:) ;;
      snapshot:) drop_snapshot "$t" "$u" ro ;;
      scratch:) if ((busy)); then pending_add "scratch $t $u"; else drop_snapshot "$t" "$u" rw; fi ;;
      /*:) if [[ -n $t && -z $u ]]; then drop_snapshot "$k" "$t" ro; else log "ERROR: unknown pending-cleanup.list line kept: $line"; pending_add "$line"; fi ;;
      *) log "ERROR: unknown pending-cleanup.list line kept: $line"; pending_add "$line" ;;
    esac
  done < "$f"
  rm -f "$f"
}
cleanup_old_diagnostics() { # leftovers of failed runs and uncommitted generations: at most 7 days
  local ts kind path u g d
  for d in "$DEST"/*/; do
    [[ -d $d ]] || continue
    while IFS= read -r g; do
      [[ -f $DEST/.committed/$g ]] && continue
      grep -Fq " $d$g " "$STATE/diag.list" 2> /dev/null || echo "$(date +%s) uncommitted $d$g -" >> "$STATE/diag.list"
    done < <(find "$d" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*T*Z' -printf '%f\n')
  done
  [[ -f $STATE/diag.list ]] || return 0
  : > "$STATE/diag.list.new"
  while read -r ts kind path u; do
    if (( $(date +%s) - ts > 7 * 86400 )); then
      case $kind in snapshot) drop_snapshot "$path" "$u" ;; partial|uncommitted) if [[ $path == "$DEST"/* ]]; then rm -rf -- "$path"; fi ;; esac
      log "removed diagnostic $kind $path"
    else echo "$ts $kind $path $u" >> "$STATE/diag.list.new"; fi
  done < "$STATE/diag.list"
  mv "$STATE/diag.list.new" "$STATE/diag.list"
}
SUCCESS=0 FAILED_SOURCE=""
on_exit() {
  local kind path u keep_snap="" keep_part=""
  if ((SUCCESS == 0)) && [[ -n $FAILED_SOURCE ]]; then
    keep_snap=$(awk -v f="/$FAILED_SOURCE-$STAMP-" '$1 == "snapshot" && index($2, f) { print $2; exit }' "$RUNSTATE" 2> /dev/null || true)
    keep_part="$DEST/$FAILED_SOURCE/.partial-$STAMP"
    if [[ -f $STATE/diag.list ]]; then   # a new failure replaces the earlier diagnostics
      while read -r _ kind path u; do
        case $kind in snapshot) drop_snapshot "$path" "$u" ;; partial) if [[ $path == "$DEST"/* ]]; then rm -rf -- "$path"; fi ;; esac
      done < <(grep -v ' uncommitted ' "$STATE/diag.list" || true)
      { grep ' uncommitted ' "$STATE/diag.list" || true; } > "$STATE/diag.list.new"; mv "$STATE/diag.list.new" "$STATE/diag.list"
    fi
  fi
  if [[ -f $RUNSTATE ]]; then
    local busy=0
    while read -r kind path u; do if [[ $kind == container ]]; then drop_container "$path" "$u" || busy=1; fi; done < "$RUNSTATE"
    while read -r kind path u; do
      if [[ $kind == scratch ]]; then if ((busy)); then pending_add "scratch $path $u"; else drop_snapshot "$path" "$u" rw; fi; fi
      if [[ $kind == snapshot && $path != "$keep_snap" ]]; then drop_snapshot "$path" "$u"; fi
      if [[ $kind == snapshot && $path == "$keep_snap" ]]; then echo "$(date +%s) snapshot $path $u" >> "$STATE/diag.list"; fi
      if [[ $kind == partial && $path != "$keep_part" && -d $path ]]; then rm -rf -- "$path"; fi
    done < "$RUNSTATE"
    rm -f "$RUNSTATE"
  fi
  if [[ -n $keep_part && -d $keep_part ]]; then echo "$(date +%s) partial $keep_part -" >> "$STATE/diag.list"; fi
  write_metrics || true
}
trap on_exit EXIT
: > "$RUNSTATE"
retry_pending
cleanup_old_diagnostics
for n in "${N[@]}"; do echo 0 > "$STATE/last_run_ok.$n"; done

# ---------------------------------------------------------------- space on both volumes (S2)
need=0
for i in "${!N[@]}"; do
  prev=$(published "${N[$i]}" | tail -1)
  if [[ -n $prev ]]; then
    stats=$(rsync -aHAXn --numeric-ids --stats --link-dest="$DEST/${N[$i]}/$prev" "${SRC[$i]}/" "$STATE/empty-target/") \
      || die "${N[$i]}: the size estimate (rsync --stats) failed"
    est=$(printf '%s\n' "$stats" | awk -F': ' '/Total transferred file size/ { gsub(/[^0-9]/, "", $2); print $2 }')
  else
    est=$(du -s -B1 --apparent-size "${SRC[$i]}" | cut -f1)
  fi
  [[ $est =~ ^[0-9]+$ ]] || die "${N[$i]}: no size estimate"
  need=$((need + est))
done
avail=$(df -B1 --output=avail "$DEST" | tail -1 | tr -d ' ')
(( avail >= need * 3 / 2 )) || die "$DEST has $avail bytes free, needs $((need * 3 / 2)) (1.5x the estimate)"
for r in $(printf '%s\n' "${ROOT[@]}" | sort -u); do   # snapshots grow while the sources change
  (( $(df -B1 --output=avail "$r" | tail -1 | tr -d ' ') * 10 >= $(df -B1 --output=size "$r" | tail -1 | tr -d ' ') )) \
    || die "$r has less than 10% free: no room for the snapshots"
done
log "space ok: $avail free on $DEST for an estimated $need new bytes"

VIEW=()
for i in "${!N[@]}"; do
  while true; do
    snap=$(snapshot_of "$i") || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: no read-only snapshot"; }
    view="$snap${SRC[$i]#"${ROOT[$i]}"}"
    if ! in_progress "${K[$i]}" "$view"; then break; fi
    drop_snapshot "$snap" "$(snap_uuid "$snap")"
    if ((NOW)) || (( $(date +%s) + RETRY > DEADLINE )); then
      FAILED_SOURCE=${N[$i]}; die "${N[$i]}: a backup is still in progress at the deadline (in_progress)"
    fi
    log "${N[$i]}: a backup is in progress; retrying in ${RETRY}s"; sleep "$RETRY"
  done
  if [[ ${K[$i]} == minio ]]; then
    minio_readback "$i" "$snap" "$view" || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: not every MinIO object read back"; }
  else
    BC_REG_DIGESTS="$CONFDIR/${N[$i]}.digests"
    check_kind "${K[$i]}" "$view" || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: completion evidence missing or not verified"; }
  fi
  VIEW[i]=$view
done

for i in "${!N[@]}"; do
  d="$DEST/${N[$i]}"; mkdir -p "$d"
  part="$d/.partial-$STAMP"; prev=$(published "${N[$i]}" | tail -1)
  record partial "$part"
  rc=0
  rsync -aHAX --numeric-ids -c ${prev:+--link-dest="$d/$prev"} "${VIEW[$i]}/" "$part/" || rc=$?
  ((rc == 0)) || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: copy exited $rc"; }
  list="$STATE/verify-${N[$i]}-$STAMP.list"; rc=0
  rsync -aHAXc -n --delete --numeric-ids --itemize-changes "${VIEW[$i]}/" "$part/" > "$list" || rc=$?
  ((rc == 0)) || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: verification exited $rc"; }
  [[ ! -s $list ]] || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: generation differs from the snapshot ($list)"; }
  rm -f "$list"; log "${N[$i]}: copied and verified (link-dest ${prev:-none})"
done

# publish: rename every source, then the commit marker makes it one generation
for i in "${!N[@]}"; do
  d="$DEST/${N[$i]}"; part="$d/.partial-$STAMP"
  bytes=$(du -s -B1 --apparent-size "$part" | cut -f1); files=$(find "$part" -type f | wc -l)
  printf '{"stamp":"%s","source":"%s","kind":"%s","snapshot_root":"%s","files":%s,"apparent_bytes":%s,"verified":"rsync -c, empty list","published_at":"%s"}\n' \
    "$STAMP" "${N[$i]}" "${K[$i]}" "${ROOT[$i]}" "$files" "$bytes" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$part/GENERATION.json"
  mv "$part" "$d/$STAMP" || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: publish rename failed"; }
  echo "$bytes" > "$STATE/bytes.${N[$i]}.new"
done
printf '%s %s\n' "$STAMP" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$DEST/.committed/$STAMP.tmp"
mv "$DEST/.committed/$STAMP.tmp" "$DEST/.committed/$STAMP"
now=$(date +%s)
for n in "${N[@]}"; do
  mv "$STATE/bytes.$n.new" "$STATE/bytes.$n"; echo "$now" > "$STATE/last_success.$n"; echo 1 > "$STATE/last_run_ok.$n"
  if [[ -f $STATE/minio-wal.$n.new ]]; then mv "$STATE/minio-wal.$n.new" "$STATE/minio-wal.$n"; fi   # the WAL ratchet
done
log "generation $STAMP committed for ${#N[@]} sources"

for i in "${!N[@]}"; do   # retention, after the commit, per source, only with the prune switch on
  [[ ${PRUNE[$i]} == on ]] || continue
  mapfile -t gens < <(published "${N[$i]}")
  n=${#gens[@]}
  if ((n > KEEP)); then
    for g in "${gens[@]:0:$((n - KEEP))}"; do
      [[ $g != "${gens[$((n - 1))]}" ]] || continue
      rm -rf -- "${DEST:?}/${N[$i]}/$g"
      log "${N[$i]}: removed generation $g (keeping $KEEP)"
    done
  fi
done
SUCCESS=1
