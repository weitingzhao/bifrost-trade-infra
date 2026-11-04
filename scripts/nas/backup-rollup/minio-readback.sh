# shellcheck shell=bash
# Weekly roll-up, MinIO sources (TD-444 step 5 runbook §3.8 item 2: option A). Sourced by
# rollup.sh, never run alone; it uses rollup.sh's globals and helpers (N, ROOT, SRC, DEST,
# STAMP, STATE, log, die, record, snap_uuid, drop_snapshot, pending_add) and bc_list /
# wal_walk from backup-checks.sh.
#
# A MinIO source passes only when its objects read back through MinIO itself, which checks
# each object's bitrot hashes while it serves it:
#   1. a writable scratch snapshot of the source's read-only snapshot (never the live data);
#   2. a throwaway container bifrost-rollup-minio-<stamp> from the pinned image (MINIO_IMAGE:
#      the image ID or repository digest of the live MinIO, --pull never), --network none,
#      no published port, one volume: the scratch copy at /data;
#   3. credentials only from MINIO_CREDENTIALS, a root-only file (600 or 400) handed to docker
#      with --env-file: never on a command line, never in a log; inside the container a shell
#      builtin writes them into an mc config that disappears with the container;
#   4. per <bucket>/<server>: the newest base backup whose backup.info (read back) says
#      status=DONE; every object of that base backup (a data tar at least; tablespaces are
#      not covered and fail); every WAL segment from its begin_wal to the newest one on that
#      timeline (a gap, a later timeline, or WAL ending before end_wal fails);
#   5. the container is stopped, confirmed stopped and removed, and only then the scratch
#      snapshot is deleted; what cannot be removed goes to pending-cleanup.list.
# The live MinIO container is never named, inspected or touched.

RB_PREFIX=bifrost-rollup-minio-
RB_READ_TIMEOUT=7200     # seconds for one object (a large base tar)
RB_SEG_SIZE=16777216     # WAL segment size; the cluster runs the default (runbook §0)
MINIO_IMAGE="" MINIO_CREDENTIALS="" MINIO_START_TIMEOUT=120
# runs inside the throwaway container; $MINIO_ROOT_* come from its --env-file
# shellcheck disable=SC2016
RB_MC_SETUP='umask 077
[ -n "$MINIO_ROOT_USER" ] && [ -n "$MINIO_ROOT_PASSWORD" ] || exit 3
case "$MINIO_ROOT_USER$MINIO_ROOT_PASSWORD" in *\"*|*\\*) exit 3 ;; esac
mkdir -p /tmp/rollup-mc || exit 1
printf "{\"version\":\"10\",\"aliases\":{\"rb\":{\"url\":\"http://127.0.0.1:9000\",\"accessKey\":\"%s\",\"secretKey\":\"%s\",\"api\":\"S3v4\",\"path\":\"auto\"}}}\n" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" > /tmp/rollup-mc/config.json'

rb_docker() { local t=$1; shift; timeout "$t" docker "$@" < /dev/null; }

minio_config_ok() { # before any snapshot: the pinned image is here, the credentials file is root-only
  local s
  [[ $MINIO_IMAGE =~ ^(sha256:[0-9a-f]{64}|[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64})$ ]] \
    || die "MINIO_IMAGE in rollup.conf must pin the live MinIO image: sha256:<image id> or <repository>@sha256:<digest>"
  [[ $MINIO_CREDENTIALS == /* && -f $MINIO_CREDENTIALS && ! -L $MINIO_CREDENTIALS ]] \
    || die "MINIO_CREDENTIALS in rollup.conf must name a regular file"
  [[ $(stat -c '%u %a' "$MINIO_CREDENTIALS") =~ ^0\ [46]00$ ]] || die "$MINIO_CREDENTIALS must belong to root with mode 600 or 400"
  for s in "${SRC[@]}" "$DEST"; do [[ $MINIO_CREDENTIALS != "$s"/* ]] || die "$MINIO_CREDENTIALS lies inside $s"; done
  [[ $(grep -cE '^MINIO_ROOT_(USER|PASSWORD)=.' "$MINIO_CREDENTIALS") == 2 ]] \
    || die "$MINIO_CREDENTIALS needs exactly one MINIO_ROOT_USER= and one MINIO_ROOT_PASSWORD= line"
  command -v docker > /dev/null || die "docker is needed for the MinIO read-back"
  rb_docker 60 image inspect "$MINIO_IMAGE" > /dev/null 2>&1 || die "the image $MINIO_IMAGE is not on this host (the roll-up never pulls)"
}

container_gone() { local out; out=$(rb_docker 30 ps -a --filter "name=^$1\$" --format '{{.Names}}') || return 1; [[ -z $out ]]; }
drop_container() { # drop_container <name>: stop, confirm stopped, remove, confirm gone; else pending-cleanup.list
  local n=$1 st
  [[ $n == "$RB_PREFIX"* ]] || { log "refusing to touch container $n"; return 1; }
  container_gone "$n" && return 0
  rb_docker 90 stop -t 30 "$n" > /dev/null 2>&1 || true
  st=$(rb_docker 30 inspect -f '{{.State.Running}}' "$n" 2> /dev/null) || st=unknown
  if [[ $st == false ]] && rb_docker 60 rm "$n" > /dev/null 2>&1 && container_gone "$n"; then
    log "throwaway MinIO $n stopped and removed"; return 0
  fi
  log "could not stop and remove the throwaway MinIO $n (running: $st); kept in pending-cleanup.list"
  pending_add "container $n -"
  return 1
}

rb_start() { # rb_start <name> <scratch data dir>
  local n=$1 data=$2 t0=$SECONDS
  rb_docker 120 run -d --pull never --name "$n" --label "bifrost.rollup=$STAMP" --network none --memory 1536m \
    --env-file "$MINIO_CREDENTIALS" -v "$data:/data" "$MINIO_IMAGE" server /data > /dev/null \
    || { log "the throwaway MinIO $n did not start"; return 1; }
  until rb_docker 15 exec "$n" curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null http://127.0.0.1:9000/minio/health/cluster > /dev/null 2>&1; do
    ((SECONDS - t0 < MINIO_START_TIMEOUT)) || { log "the throwaway MinIO $n was not healthy within ${MINIO_START_TIMEOUT}s"; return 1; }
    sleep 2
  done
  rb_docker 30 exec "$n" sh -c "$RB_MC_SETUP" > /dev/null 2>&1 \
    || { log "no mc alias in $n: the credentials file lacks a user or password, or holds a quote or backslash"; return 1; }
  log "throwaway MinIO $n is up: no network, no port, scratch copy $data"
}

rb_read() { # rb_read <name> <object> [<out file>]: one object read back through MinIO
  local rc=0 err
  err=$(mktemp)
  # shellcheck disable=SC2016  # $1 is the object, expanded by the shell inside the container
  if [[ -n ${3:-} ]]; then
    rb_docker 300 exec "$1" sh -c 'mc --config-dir /tmp/rollup-mc cat "rb/$1"' sh "$2" > "$3" 2> "$err" || rc=$?
  else
    rb_docker "$RB_READ_TIMEOUT" exec "$1" sh -c 'mc --config-dir /tmp/rollup-mc cat "rb/$1" > /dev/null' sh "$2" 2> "$err" || rc=$?
  fi
  ((rc == 0)) || log "COULD NOT READ $2 (exit $rc): $(grep -v -i -e secret -e password "$err" | head -1)"
  rm -f "$err"
  return "$rc"
}

rb_prefix() { # rb_prefix <name> <view> <tmp> <bucket/server>
  local n=$1 view=$2 tmp=$3 p=$4 id chosen="" begin end tbs k f b last seg bad=0 nb=0 nw=0
  local -A wal=()
  while read -r id; do
    [[ -f $view/$p/base/$id/backup.info/xl.meta ]] || continue
    rb_read "$n" "$p/base/$id/backup.info" "$tmp/info" || return 1
    if grep -qx 'status=DONE' "$tmp/info"; then chosen=$id; break; fi
    log "$p: base backup $id is $(sed -n 's/^status=//p' "$tmp/info" | head -1), not DONE"
  done < <(find "$view/$p/base" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)
  [[ -n $chosen ]] || { log "$p: no base backup whose backup.info says status=DONE"; return 1; }
  begin=$(sed -n 's/^begin_wal=//p' "$tmp/info" | head -1); end=$(sed -n 's/^end_wal=//p' "$tmp/info" | head -1)
  tbs=$(sed -n 's/^tablespaces=//p' "$tmp/info" | head -1)
  [[ $begin =~ ^[0-9A-F]{24}$ && $end =~ ^[0-9A-F]{24}$ ]] || { log "$p: base backup $chosen lacks begin_wal or end_wal"; return 1; }
  [[ -z $tbs || $tbs == None ]] || { log "$p: base backup $chosen has tablespaces; this check does not cover them"; return 1; }
  # every object of the chosen base backup
  bc_list "$tmp/base.raw" "$view/$p/base/$chosen" -type f -name xl.meta || return 1
  while read -r f; do k=${f#"$view/"}; echo "${k%/xl.meta}"; done < "$tmp/base.raw" | LC_ALL=C sort > "$tmp/base"
  grep -Eq "/base/$chosen/data(_[0-9]+)?\.tar(\.[a-z0-9]+)?$" "$tmp/base" || { log "$p: base backup $chosen has no data tar"; return 1; }
  while read -r k; do
    [[ $k == */backup.info ]] && continue
    rb_read "$n" "$k" || bad=1; nb=$((nb + 1))
  done < "$tmp/base"
  # every WAL segment from begin_wal on, on its timeline
  bc_list "$tmp/wal.raw" "$view/$p/wals" -mindepth 3 -maxdepth 3 -type f -name xl.meta || return 1
  while read -r f; do
    k=${f#"$view/"}; k=${k%/xl.meta}; b=${k##*/}
    [[ $b =~ ^[0-9A-F]{24}(\.(gz|bz2|snappy|xz|lz4|zst))?$ ]] || continue
    if [[ ${b:0:8} > ${begin:0:8} ]]; then log "$p: WAL on a later timeline than ${begin:0:8} after the base backup; check it by hand"; return 1; fi
    [[ ${b:0:8} == "${begin:0:8}" ]] && wal[${b:0:24}]+="$k "
  done < "$tmp/wal.raw"
  last=$(printf '%s\n' "${!wal[@]}" | LC_ALL=C sort | tail -1)
  [[ -n $last && ! $last < $begin ]] || { log "$p: no WAL from $begin on"; return 1; }
  [[ ! $last < $end ]] || { log "$p: WAL ends at $last, before the base backup's end_wal $end"; return 1; }
  wal_walk "$begin" "$last" "$RB_SEG_SIZE" > "$tmp/segs" || { log "$p: WAL names outside the segment range"; return 1; }
  while read -r seg; do
    if [[ -z ${wal[$seg]:-} ]]; then log "$p: WAL $seg missing after base $chosen"; bad=1; continue; fi
    for k in ${wal[$seg]}; do rb_read "$n" "$k" || bad=1; done
    nw=$((nw + 1))
  done < "$tmp/segs"
  ((bad == 0)) || { log "$p: not every object read back"; return 1; }
  log "$p: base backup $chosen ($nb objects) and $nw WAL segments $begin..$last read back through MinIO"
}

minio_readback() { # minio_readback <i> <read-only snapshot> <view>: 0 only when every needed object read back
  local i=$1 snap=$2 view=$3 mnt rw uuid name p rc=0 tmp f
  tmp=$(mktemp -d)
  bc_list "$tmp/infos" "$view" -mindepth 6 -maxdepth 6 -type f -path '*/base/*/backup.info/xl.meta' || { rm -rf "$tmp"; return 1; }
  while read -r f; do p=${f#"$view/"}; [[ $p == .* ]] || echo "${p%%/base/*}"; done < "$tmp/infos" | LC_ALL=C sort -u > "$tmp/prefixes"
  [[ -s $tmp/prefixes ]] || { log "${N[$i]}: no base backup with a backup.info"; rm -rf "$tmp"; return 1; }
  mnt=$(findmnt -no TARGET -T "${ROOT[$i]}")
  rw="${mnt%/}/@bifrost/rollup-snap/${N[$i]}-rw-$STAMP-$RANDOM"
  btrfs subvolume snapshot "$snap" "$rw" > /dev/null || { log "${N[$i]}: no writable scratch snapshot"; rm -rf "$tmp"; return 1; }
  uuid=$(snap_uuid "$rw")
  record scratch "$rw" "${uuid:--}"
  [[ -n $uuid ]] || { log "$rw has no UUID"; rm -rf "$tmp"; return 1; }
  name="$RB_PREFIX$STAMP"
  record container "$name"
  if rb_start "$name" "$rw${SRC[$i]#"${ROOT[$i]}"}"; then
    while read -r p; do rb_prefix "$name" "$view" "$tmp" "$p" || rc=1; done < "$tmp/prefixes"
  else
    rc=1
  fi
  # tear down now, whatever happened: the container first, the scratch copy only once it is gone
  if drop_container "$name"; then drop_snapshot "$rw" "$uuid" rw; else pending_add "scratch $rw $uuid"; fi
  rm -rf "$tmp"
  return "$rc"
}
