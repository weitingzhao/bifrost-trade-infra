#!/usr/bin/env bash
# Weekly roll-up of the SSD backups onto the RAID5 HDDs (TD-444 step 5 runbook §5.1, §5.3, §5.4).
#
# Runs on the NAS as root from bifrost-backup-rollup.timer (Sunday 12:30 UTC), or by hand:
#   sudo /volume1/@bifrost/backup-rollup/rollup.sh [--conf FILE] [--dest DIR] [--now]
# Config (rollup.conf, template rollup.conf.example): one source per line
#   <name> <kind> <source dir> <snapshot root (a btrfs subvolume)> <prune on|off>
#
# One run, under flock, produces one generation stamped <UTC>:
#   1. for each source, a read-only snapshot of its subvolume (never an online copy); a
#      nested subvolume under the source rejects the source;
#   2. completion is judged from the data in the snapshot, by kind; a backup still in
#      progress (partial/lock markers) waits 15 minutes and tries again until --deadline-utc,
#      then the source fails;
#   3. rsync -aHAX -c --link-dest=<previous generation> into <dest>/<name>/.partial-<stamp>,
#      then a full check (rsync -c -n --delete --itemize-changes: exit 0 and an empty list),
#      which also covers the files reused through --link-dest;
#   4. only when every source passed: GENERATION.json written, every .partial renamed into
#      place, then every source's last-success time moves together;
#   5. after publishing, and only for sources whose prune switch is on: keep the newest 8
#      published generations (the newest is never deleted). A failed run deletes nothing published;
#   6. cleanup of what this run created (run.state): snapshots always; on failure one
#      .partial and one snapshot are kept for diagnosis, at most 7 days;
#   7. metrics through the node-exporter textfile collector, written atomically.
set -euo pipefail
umask 077

CONF=/volume1/@bifrost/backup-rollup/rollup.conf
DEST=/volume1/backup-weekly
STATE=/volume1/@bifrost/backup-rollup/state
TEXTFILE=/volume1/@bifrost/textfile/backup-rollup.prom
KEEP=8
DEADLINE_UTC=16:30      # 10:30 CST
RETRY=900
NOW=0

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "FAIL: $*"; exit 1; }
while (($#)); do
  case $1 in
    --conf) CONF=$2; shift 2 ;;
    --dest) DEST=$2; shift 2 ;;
    --state) STATE=$2; shift 2 ;;
    --textfile) TEXTFILE=$2; shift 2 ;;
    --keep) KEEP=$2; shift 2 ;;
    --deadline-utc) DEADLINE_UTC=$2; shift 2 ;;
    --retry) RETRY=$2; shift 2 ;;
    --now) NOW=1; shift ;;   # no waiting for in-progress backups: fail at once
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done
((EUID == 0)) || die "run as root"
[[ $KEEP =~ ^[1-9][0-9]*$ && $RETRY =~ ^[0-9]+$ && $DEADLINE_UTC =~ ^[0-2][0-9]:[0-5][0-9]$ ]] || die "bad --keep/--retry/--deadline-utc"
mkdir -p "$STATE" "$DEST" "$(dirname "$TEXTFILE")"
chmod 700 "$STATE"
exec 9> "$STATE/lock"
flock -n 9 || die "another roll-up is running"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUNSTATE="$STATE/run.state"
LOGF="$STATE/run-$STAMP.log"
exec 2> >(tee -a "$LOGF" >&2)
DEADLINE=$(date -u -d "$(date -u +%Y-%m-%d) $DEADLINE_UTC" +%s)

# ---------------------------------------------------------------- config
N=() K=() SRC=() ROOT=() PRUNE=()
while read -r name kind src root prune extra; do
  [[ -z ${name:-} || $name == \#* ]] && continue
  [[ -z ${extra:-} && $name =~ ^[a-z][a-z0-9-]*$ ]] || die "bad config line for ${name:-?}"
  case $kind in logical|finance|gitea|cluster-state|registry|minio) ;; *) die "$name: unknown kind $kind" ;; esac
  [[ $prune == on || $prune == off ]] || die "$name: prune must be on or off"
  [[ $src == "$root" || $src == "$root"/* ]] || die "$name: source is not inside its snapshot root"
  N+=("$name") K+=("$kind") SRC+=("$src") ROOT+=("$root") PRUNE+=("$prune")
done < "$CONF"
((${#N[@]})) || die "no sources in $CONF"

# ---------------------------------------------------------------- metrics
write_metrics() { # every configured source, from the persisted state
  local i tmp="$TEXTFILE.$$.tmp" ts ok bytes gens
  {
    echo "# HELP bifrost_nas_backup_rollup_last_success_timestamp_seconds Last generation published with this source verified."
    echo "# TYPE bifrost_nas_backup_rollup_last_success_timestamp_seconds gauge"
    echo "# HELP bifrost_nas_backup_rollup_last_run_ok 1 when the last run passed this source and published, else 0."
    echo "# TYPE bifrost_nas_backup_rollup_last_run_ok gauge"
    echo "# HELP bifrost_nas_backup_rollup_source_enabled 1 for every source in rollup.conf."
    echo "# TYPE bifrost_nas_backup_rollup_source_enabled gauge"
    echo "# HELP bifrost_nas_backup_rollup_generation_bytes Apparent bytes of the newest published generation."
    echo "# TYPE bifrost_nas_backup_rollup_generation_bytes gauge"
    echo "# HELP bifrost_nas_backup_rollup_generations Published generations kept for this source."
    echo "# TYPE bifrost_nas_backup_rollup_generations gauge"
    echo "# HELP bifrost_nas_backup_rollup_prune_enabled 1 when old generations of this source may be deleted."
    echo "# TYPE bifrost_nas_backup_rollup_prune_enabled gauge"
    echo "# HELP bifrost_nas_backup_rollup_last_run_timestamp_seconds Last time the roll-up ran."
    echo "# TYPE bifrost_nas_backup_rollup_last_run_timestamp_seconds gauge"
    for i in "${!N[@]}"; do
      ts=$(cat "$STATE/last_success.${N[$i]}" 2>/dev/null || true)
      ok=$(cat "$STATE/last_run_ok.${N[$i]}" 2>/dev/null || echo 0)
      bytes=$(cat "$STATE/bytes.${N[$i]}" 2>/dev/null || echo 0)
      gens=$(published "${N[$i]}" | wc -l)
      [[ -n $ts ]] && echo "bifrost_nas_backup_rollup_last_success_timestamp_seconds{source=\"${N[$i]}\"} $ts"
      echo "bifrost_nas_backup_rollup_last_run_ok{source=\"${N[$i]}\"} $ok"
      echo "bifrost_nas_backup_rollup_source_enabled{source=\"${N[$i]}\"} 1"
      echo "bifrost_nas_backup_rollup_generation_bytes{source=\"${N[$i]}\"} $bytes"
      echo "bifrost_nas_backup_rollup_generations{source=\"${N[$i]}\"} $gens"
      echo "bifrost_nas_backup_rollup_prune_enabled{source=\"${N[$i]}\"} $([[ ${PRUNE[$i]} == on ]] && echo 1 || echo 0)"
    done
    echo "bifrost_nas_backup_rollup_last_run_timestamp_seconds $(date +%s)"
  } > "$tmp"
  chmod 644 "$tmp"
  mv "$tmp" "$TEXTFILE"
}
published() { # published generations of a source, oldest first
  local d="$DEST/$1" g
  [[ -d $d ]] || return 0
  for g in $(ls -1 "$d" | { grep -E '^[0-9]{8}T[0-9]{6}Z$' || true; } | LC_ALL=C sort); do
    [[ -f $d/$g/GENERATION.json ]] && echo "$g"
  done
  return 0
}

# ---------------------------------------------------------------- completion by kind (§5.1 table)
in_progress() { # in_progress <kind> <dir>: 0 when a backup is still being written
  local d=$2
  case $1 in
    logical|finance) compgen -G "$d/daily/.partial-*" > /dev/null ;;
    gitea) [[ -e $d/.lock ]] || compgen -G "$d/*.partial" > /dev/null ;;
    cluster-state) compgen -G "$d/daily/.partial-*" > /dev/null || compgen -G "$d/monthly/.partial-*" > /dev/null \
                     || compgen -G "$d/daily/.old-*" > /dev/null || compgen -G "$d/monthly/.old-*" > /dev/null ;;
    registry) return 1 ;;
    minio) # an upload in flight, or a base backup younger than 6 h without its backup.info object
      [[ -n $(find "$d/.minio.sys/multipart" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null) ]] && return 0
      local b
      while IFS= read -r b; do
        [[ -d $b/backup.info ]] || return 0
      done < <(find "$d" -mindepth 4 -maxdepth 4 -type d -path '*/base/*' -mmin -360 2>/dev/null)
      return 1 ;;
  esac
}
complete_ok() { # complete_ok <kind> <dir>: 0 when the data carries a verified completion mark
  local d=$2 l run bad=0
  case $1 in
    logical|finance)
      l=$(cat "$d/LATEST" 2>/dev/null) || { log "no LATEST"; return 1; }
      [[ $(cat "$d/daily/$l/STATUS" 2>/dev/null) == OK ]] || { log "LATEST $l is not STATUS=OK"; return 1; }
      (cd "$d/daily/$l" && sha256sum -c --quiet SHA256SUMS) || return 1 ;;
    gitea)
      l=$(cat "$d/LATEST" 2>/dev/null) || { log "no LATEST"; return 1; }
      [[ $(cat "$d/$l/STATUS" 2>/dev/null) == OK ]] || { log "LATEST $l is not STATUS=OK"; return 1; }
      (cd "$d/$l" && grep -v '^#' SHA256SUMS | sha256sum -c --quiet -) || return 1 ;;
    cluster-state)
      for run in "$d"/daily/????-??-??; do
        [[ -d $run ]] || continue
        [[ $(cat "$run/STATUS" 2>/dev/null) == OK ]] || { log "$run: no STATUS=OK"; bad=1; continue; }
        cs_manifest "$run" || bad=1
      done
      for run in "$d"/monthly/????-??; do
        [[ -d $run ]] || continue
        cs_monthly_files "$run" || bad=1
        cs_manifest "$run" || bad=1
      done
      return "$bad" ;;
    registry)
      local f want
      while IFS= read -r -d '' f; do
        want=$(basename "$(dirname "$f")")
        [[ $(sha256sum "$f" | cut -d' ' -f1) == "$want" ]] || { log "blob $want differs"; bad=1; }
      done < <(find "$d/docker/registry/v2/blobs/sha256" -mindepth 3 -maxdepth 3 -type f -name data -print0)
      return "$bad" ;;
    minio) # at least one base backup with a backup.info that says DONE (inline in xl.meta)
      local info
      while IFS= read -r info; do
        grep -aq 'status=DONE' "$info" && return 0
      done < <(find "$d" -mindepth 6 -maxdepth 6 -type f -path '*/base/*/backup.info/xl.meta' 2>/dev/null)
      log "no base backup with backup.info status=DONE"
      return 1 ;;
  esac
}
cs_manifest() {
  local run=$1 name bytes sum
  [[ -f $run/MANIFEST ]] && grep -q '^timestamp [0-9]' "$run/MANIFEST" || { log "$run: MANIFEST missing or without timestamp"; return 1; }
  while read -r name bytes sum; do
    [[ -f $run/$name && $(stat -c %s "$run/$name") == "$bytes" && $(sha256sum "$run/$name" | cut -d' ' -f1) == "$sum" ]] \
      || { log "$run: $name does not match MANIFEST"; return 1; }
  done < <(awk '$1 == "file" { b = ""; s = ""; for (i = 3; i < NF; i++) { if ($i == "ciphertext_bytes") b = $(i+1); if ($i == "ciphertext_sha256") s = $(i+1) } print $2, b, s }' "$run/MANIFEST")
}
cs_monthly_files() {
  local names
  names=$(cd "$1" && ls -1 | LC_ALL=C sort | tr '\n' ' ')
  [[ $names =~ ^MANIFEST\ etcd-snapshot-[^\ ]+\.age\ platform-state\.yaml\.age\ secrets\.yaml\.age\ server-token\.age\ $ ]] \
    || { log "$1: unexpected file set: $names"; return 1; }
}

# ---------------------------------------------------------------- snapshots and cleanup
SNAPS=()
record() { printf '%s %s\n' "$1" "$2" >> "$RUNSTATE"; }
snapshot_of() { # snapshot_of <i>: prints the snapshot path
  local i=$1 mnt snap
  btrfs subvolume show "${ROOT[$i]}" > /dev/null 2>&1 || { log "${N[$i]}: ${ROOT[$i]} is not a subvolume"; return 1; }
  if [[ -n $(find "${SRC[$i]}" -mindepth 1 -xdev -type d -inum 256 -print -quit 2>/dev/null) ]]; then
    log "${N[$i]}: a nested subvolume under ${SRC[$i]}; no consistent point in time, source rejected"; return 1
  fi
  mnt=$(findmnt -no TARGET -T "${ROOT[$i]}")
  mkdir -p "$mnt/@bifrost/rollup-snap"
  snap="$mnt/@bifrost/rollup-snap/${N[$i]}-$STAMP-$RANDOM"
  btrfs subvolume snapshot -r "${ROOT[$i]}" "$snap" > /dev/null || return 1
  record snapshot "$snap"; SNAPS+=("$snap")
  printf '%s' "$snap"
}
drop_snapshot() { [[ $1 == */@bifrost/rollup-snap/* && -d $1 ]] && btrfs subvolume delete "$1" > /dev/null; return 0; }
cleanup_old_diagnostics() { # leftovers of failed runs: at most 7 days
  local kind path ts
  [[ -f $STATE/diag.list ]] || return 0
  : > "$STATE/diag.list.new"
  while read -r ts kind path; do
    if (( $(date +%s) - ts > 7 * 86400 )); then
      if [[ $kind == snapshot ]]; then drop_snapshot "$path"; elif [[ $path == "$DEST"/*/.partial-* ]]; then rm -rf -- "$path"; fi
      log "removed diagnostic $kind $path"
    else
      echo "$ts $kind $path" >> "$STATE/diag.list.new"
    fi
  done < "$STATE/diag.list"
  mv "$STATE/diag.list.new" "$STATE/diag.list"
}
SUCCESS=0
FAILED_SOURCE=""
on_exit() {
  local keep_snap="" keep_part=""
  if ((SUCCESS == 0)) && [[ -n $FAILED_SOURCE ]]; then
    keep_snap=$(grep -F "/$FAILED_SOURCE-$STAMP-" "$RUNSTATE" 2>/dev/null | awk '$1 == "snapshot" { print $2 }' | head -1)
    keep_part="$DEST/$FAILED_SOURCE/.partial-$STAMP"
    # a new failure replaces the previous diagnostics: at most one partial and one snapshot
    if [[ -f $STATE/diag.list ]]; then
      while read -r _ kind path; do
        if [[ $kind == snapshot ]]; then drop_snapshot "$path"; elif [[ $path == "$DEST"/*/.partial-* ]]; then rm -rf -- "$path"; fi
      done < "$STATE/diag.list"
      rm -f "$STATE/diag.list"
    fi
  fi
  if [[ -f $RUNSTATE ]]; then
    while read -r kind path; do
      if [[ $kind == snapshot && $path != "$keep_snap" ]]; then drop_snapshot "$path"; fi
      if [[ $kind == partial && $path != "$keep_part" && -d $path ]]; then rm -rf -- "$path"; fi
    done < "$RUNSTATE"
    rm -f "$RUNSTATE"
  fi
  [[ -n $keep_snap ]] && echo "$(date +%s) snapshot $keep_snap" >> "$STATE/diag.list"
  [[ -n $keep_part && -d $keep_part ]] && echo "$(date +%s) partial $keep_part" >> "$STATE/diag.list"
  write_metrics || true
}
trap on_exit EXIT

# ---------------------------------------------------------------- run
[[ ! -e $RUNSTATE ]] || die "$RUNSTATE exists: an earlier run did not clean up; check it by hand"
cleanup_old_diagnostics
: > "$RUNSTATE"
for i in "${!N[@]}"; do echo 0 > "$STATE/last_run_ok.${N[$i]}"; done

# free space: the newest generation of each source (or the whole source) times 1.5
need=0
for i in "${!N[@]}"; do
  prev=$(published "${N[$i]}" | tail -1)
  if [[ -n $prev ]]; then
    est=$( { rsync -aHAXn --numeric-ids --stats --link-dest="$DEST/${N[$i]}/$prev" "${SRC[$i]}/" "$STATE/empty-target/" 2>/dev/null || true; } \
          | awk -F': ' '/Total transferred file size/ { gsub(/[^0-9]/, "", $2); print $2 }')
  else
    est=$(du -s -B1 --apparent-size "${SRC[$i]}" | cut -f1)
  fi
  need=$(( need + ${est:-0} ))
done
avail=$(df -B1 --output=avail "$DEST" | tail -1 | tr -d ' ')
(( avail >= need * 3 / 2 )) || die "$DEST has $avail bytes free, needs $((need * 3 / 2)) (1.5x the estimate)"
log "space ok: $avail free for an estimated $need new bytes"

VIEW=()
for i in "${!N[@]}"; do
  while true; do
    snap=$(snapshot_of "$i") || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: no read-only snapshot"; }
    view="$snap${SRC[$i]#"${ROOT[$i]}"}"
    if ! in_progress "${K[$i]}" "$view"; then break; fi
    drop_snapshot "$snap"
    if ((NOW)) || (( $(date +%s) + RETRY > DEADLINE )); then
      FAILED_SOURCE=${N[$i]}; die "${N[$i]}: a backup is still in progress at the deadline (in_progress)"
    fi
    log "${N[$i]}: a backup is in progress; retrying in ${RETRY}s"
    sleep "$RETRY"
  done
  complete_ok "${K[$i]}" "$view" || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: completion mark missing or not verified"; }
  VIEW[$i]=$view
done

for i in "${!N[@]}"; do
  d="$DEST/${N[$i]}"; mkdir -p "$d"
  part="$d/.partial-$STAMP"
  prev=$(published "${N[$i]}" | tail -1)
  record partial "$part"
  rc=0
  rsync -aHAX --numeric-ids -c ${prev:+--link-dest="$d/$prev"} "${VIEW[$i]}/" "$part/" || rc=$?
  ((rc == 0)) || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: copy exited $rc"; }
  list="$STATE/verify-${N[$i]}-$STAMP.list"
  rc=0
  rsync -aHAXc -n --delete --numeric-ids --itemize-changes "${VIEW[$i]}/" "$part/" > "$list" || rc=$?
  ((rc == 0)) || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: verification exited $rc"; }
  [[ ! -s $list ]] || { FAILED_SOURCE=${N[$i]}; die "${N[$i]}: generation differs from the snapshot ($list)"; }
  rm -f "$list"
  log "${N[$i]}: copied and verified (link-dest ${prev:-none})"
done

# publish: all sources passed
for i in "${!N[@]}"; do
  d="$DEST/${N[$i]}"; part="$d/.partial-$STAMP"
  bytes=$(du -s -B1 --apparent-size "$part" | cut -f1)
  files=$(find "$part" -type f | wc -l)
  printf '{"stamp":"%s","source":"%s","kind":"%s","snapshot_root":"%s","files":%s,"apparent_bytes":%s,"verified":"rsync -c, empty list","published_at":"%s"}\n' \
    "$STAMP" "${N[$i]}" "${K[$i]}" "${ROOT[$i]}" "$files" "$bytes" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$part/GENERATION.json"
  mv "$part" "$d/$STAMP"
  echo "$bytes" > "$STATE/bytes.${N[$i]}"
done
now=$(date +%s)
for i in "${!N[@]}"; do echo "$now" > "$STATE/last_success.${N[$i]}"; echo 1 > "$STATE/last_run_ok.${N[$i]}"; done
log "generation $STAMP published for ${#N[@]} sources"

# retention, after publishing, per source, only with the prune switch on
for i in "${!N[@]}"; do
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
