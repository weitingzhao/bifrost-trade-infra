# shellcheck shell=bash
# Weekly roll-up, MinIO sources (TD-444 step 5 runbook §3.8 item 2: option A). Sourced by
# rollup.sh, never run alone; it uses rollup.sh's globals and helpers (N, ROOT, SRC, DEST,
# STAMP, STATE, log, die, record, snap_uuid, drop_snapshot, pending_add) and bc_list /
# wal_walk from backup-checks.sh.
#
# A MinIO source passes only when its objects read back through MinIO itself, which checks
# each object's bitrot hashes while it serves it:
#   1. a writable scratch snapshot of the source's read-only snapshot (never the live data);
#   2. a throwaway container from the pinned image (MINIO_IMAGE: the image ID or repository
#      digest of the live MinIO, --pull never), --network none, no published port, one
#      volume: the scratch copy at /data. Its name and its label bifrost.rollup.run carry a
#      run token of its own; cleanup acts only on the container ID this run created and only
#      while that ID carries the token, so a container of the same name is never touched;
#   3. credentials only from MINIO_CREDENTIALS, a root-only file (600 or 400) handed to docker
#      with --env-file: never on a command line, never in a log; inside the container a shell
#      builtin writes them into an mc config that disappears with the container;
#   4. what must be read back comes from directories, backup.info and the last committed
#      generation, never from the xl.meta files that happen to be left (an object directory
#      whose xl.meta is gone fails its read-back):
#      - every <bucket>/<server> that has a base directory, and every one the last committed
#        generation read ($STATE/minio-wal.<source>);
#      - the newest base backup whose backup.info, read back, says status=DONE (a base
#        directory without backup.info is unfinished and skipped); every object directory of
#        it; its data tar parts data.tar[.gz|.bz2], data_0001.tar…, gap-free, each read back
#        and listed as an intact tar, global/pg_control among the members and backup_label
#        the last member of the last part (barman-cloud writes it last, so a missing last part
#        shows); anything else in it (tablespaces, a part after a gap) fails;
#      - every WAL segment from begin_wal through end_wal (both from backup.info) and on to
#        the newest segment directory of that timeline; a missing segment, a segment directory
#        on a later timeline, or a newest segment older than the one the last committed
#        generation read fails;
#   5. the container is stopped, confirmed stopped and removed, and only then the scratch
#      snapshot is deleted; what cannot be removed goes to pending-cleanup.list. A read-back
#      that passed still publishes when only this cleanup failed (runbook §3.8 item 2).
# The live MinIO container is never named, inspected or touched.

RB_PREFIX=bifrost-rollup-minio- RB_LABEL=bifrost.rollup.run
RB_READ_TIMEOUT=7200     # seconds for one object (a large base tar)
RB_SEG_SIZE=16777216     # WAL segment size; the cluster runs the default (runbook §0)
MINIO_IMAGE="" MINIO_CREDENTIALS="" MINIO_START_TIMEOUT=120 RB_CID=""
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

rb_gone() { local out; out=$(rb_docker 30 ps -aq --no-trunc --filter "id=$1") || return 1; [[ -z $out ]]; }
drop_container() { # drop_container <id> <run token>: only our container, stopped, confirmed, removed
  local id=$1 token=${2:--} lab st
  if [[ ! $id =~ ^[0-9a-f]{12,64}$ || $token == - ]]; then
    log "container record '$id' has no container ID and run token: ownership unknown, left alone (remove its pending-cleanup.list line by hand)"
    pending_add "container $id $token"; return 1
  fi
  rb_gone "$id" && return 0
  lab=$(rb_docker 30 inspect -f "{{index .Config.Labels \"$RB_LABEL\"}}" "$id" 2> /dev/null) \
    || { log "cannot inspect container $id; kept in pending-cleanup.list"; pending_add "container $id $token"; return 1; }
  [[ $lab == "$token" ]] || { log "container $id does not carry run token $token: not ours, left alone"; return 0; }
  rb_docker 90 stop -t 30 "$id" > /dev/null 2>&1 || true
  st=$(rb_docker 30 inspect -f '{{.State.Running}}' "$id" 2> /dev/null) || st=unknown
  if [[ $st == false ]] && rb_docker 60 rm "$id" > /dev/null 2>&1 && rb_gone "$id"; then
    log "throwaway MinIO $id stopped and removed"; return 0
  fi
  log "could not stop and remove the throwaway MinIO $id (running: $st); kept in pending-cleanup.list"
  pending_add "container $id $token"
  return 1
}

rb_start() { # rb_start <name> <run token> <scratch data dir>: sets RB_CID (recorded once known)
  local n=$1 token=$2 data=$3 t0=$SECONDS out ok=1
  out=$(rb_docker 120 run -d --pull never --name "$n" --label "$RB_LABEL=$token" --network none --memory 1536m \
    --env-file "$MINIO_CREDENTIALS" -v "$data:/data" "$MINIO_IMAGE" server /data 2> /dev/null) || ok=0
  RB_CID=$(printf '%s\n' "$out" | tail -1)
  if [[ ! $RB_CID =~ ^[0-9a-f]{12,64}$ ]]; then   # failed or timed out, maybe after creating it: the token finds it
    RB_CID=$({ rb_docker 30 ps -aq --no-trunc --filter "label=$RB_LABEL=$token" || true; } | head -1)
  fi
  if [[ -n $RB_CID ]]; then record container "$RB_CID" "$token"; fi
  if ((ok == 0)) || [[ -z $RB_CID ]]; then log "the throwaway MinIO $n did not start; no other container was touched"; return 1; fi
  until rb_docker 15 exec "$RB_CID" curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null http://127.0.0.1:9000/minio/health/cluster > /dev/null 2>&1; do
    ((SECONDS - t0 < MINIO_START_TIMEOUT)) || { log "the throwaway MinIO $n was not healthy within ${MINIO_START_TIMEOUT}s"; return 1; }
    sleep 2
  done
  rb_docker 30 exec "$RB_CID" sh -c "$RB_MC_SETUP" > /dev/null 2>&1 \
    || { log "no mc alias in $n: the credentials file lacks a user or password, or holds a quote or backslash"; return 1; }
  log "throwaway MinIO $n is up: no network, no port, scratch copy $data"
}

rb_err() { grep -v -i -e secret -e password "$1" | head -1; }
rb_read() { # rb_read <object> [<out file>]: one object read back through MinIO
  local rc=0 err
  err=$(mktemp)
  # shellcheck disable=SC2016  # $1 is the object, expanded by the shell inside the container
  if [[ -n ${2:-} ]]; then
    rb_docker 300 exec "$RB_CID" sh -c 'mc --config-dir /tmp/rollup-mc cat "rb/$1"' sh "$1" > "$2" 2> "$err" || rc=$?
  else
    rb_docker "$RB_READ_TIMEOUT" exec "$RB_CID" sh -c 'mc --config-dir /tmp/rollup-mc cat "rb/$1" > /dev/null' sh "$1" 2> "$err" || rc=$?
  fi
  ((rc == 0)) || log "COULD NOT READ $1 (exit $rc): $(rb_err "$err")"
  rm -f "$err"
  return "$rc"
}
rb_tar() { # rb_tar <object> <ext> <members out>: read back, decompress and list one tar part, on the host
  local err dec st
  case $2 in .gz) dec=(gzip -dc) ;; .bz2) dec=(bzip2 -dc) ;; "") dec=(cat) ;; *) log "$1: a $2 tar cannot be listed here"; return 1 ;; esac
  err=$(mktemp)
  # shellcheck disable=SC2016
  rb_docker "$RB_READ_TIMEOUT" exec "$RB_CID" sh -c 'mc --config-dir /tmp/rollup-mc cat "rb/$1"' sh "$1" 2> "$err" \
    | "${dec[@]}" 2>> "$err" | { tar -tf - > "$3" 2>> "$err"; r=$?; cat > /dev/null; exit "$r"; }
  st="${PIPESTATUS[*]}"
  if [[ $st != "0 0 0" ]]; then log "COULD NOT READ $1 as an intact tar (read, decompress, list: $st): $(rb_err "$err")"; rm -f "$err"; return 1; fi
  rm -f "$err"
}

rb_prefix() { # rb_prefix <view> <tmp> <bucket/server>: appends "<prefix> <newest WAL read>" to <tmp>/newest
  local view=$1 tmp=$2 p=$3 id chosen="" begin end tbs o e ext n k b last seg nw=0 bad=0
  local -a parts=()
  local -A wal=()
  bc_list "$tmp/ids" "$view/$p/base" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' || return 1
  while read -r id; do
    [[ -d $view/$p/base/$id/backup.info ]] || { log "$p: base backup $id has no backup.info (unfinished), skipped"; continue; }
    rb_read "$p/base/$id/backup.info" "$tmp/info" || return 1
    if grep -qx 'status=DONE' "$tmp/info"; then chosen=$id; break; fi
    log "$p: base backup $id is $(sed -n 's/^status=//p' "$tmp/info" | head -1), not DONE"
  done < <(LC_ALL=C sort -r "$tmp/ids")
  [[ -n $chosen ]] || { log "$p: no base backup whose backup.info says status=DONE"; return 1; }
  begin=$(sed -n 's/^begin_wal=//p' "$tmp/info" | head -1); end=$(sed -n 's/^end_wal=//p' "$tmp/info" | head -1)
  tbs=$(sed -n 's/^tablespaces=//p' "$tmp/info" | head -1)
  [[ $begin =~ ^[0-9A-F]{24}$ && $end =~ ^[0-9A-F]{24}$ && ! $end < $begin ]] || { log "$p: base backup $chosen lacks a valid begin_wal and end_wal"; return 1; }
  [[ -z $tbs || $tbs == None ]] || { log "$p: base backup $chosen has tablespaces; this check does not cover them"; return 1; }
  if ! grep -Eq '^backup_label=.+' "$tmp/info" || grep -qx 'backup_label=None' "$tmp/info"; then
    log "$p: base backup $chosen has no backup_label: its last data part cannot be proven"; return 1
  fi
  # the object directories of the base backup, and its data tar parts
  bc_list "$tmp/objs" "$view/$p/base/$chosen" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' || return 1
  n=0; ext=""
  for e in "" .gz .bz2 .snappy; do if grep -Fxq "data.tar$e" "$tmp/objs"; then ext=$e; n=$((n + 1)); fi; done
  ((n == 1)) || { log "$p: base backup $chosen holds $n first data parts (data.tar[.gz|.bz2|.snappy]); needs exactly one"; return 1; }
  parts=("data.tar$ext"); k=1
  while grep -Fxq "$(printf 'data_%04d.tar%s' "$k" "$ext")" "$tmp/objs"; do parts+=("$(printf 'data_%04d.tar%s' "$k" "$ext")"); k=$((k + 1)); done
  while read -r o; do
    [[ $o == backup.info ]] || printf '%s\n' "${parts[@]}" | grep -Fxq "$o" \
      || { log "$p: base backup $chosen holds $o, which is no part of the gap-free data tar sequence"; bad=1; }
  done < "$tmp/objs"
  : > "$tmp/members.all"
  for k in "${!parts[@]}"; do
    rb_tar "$p/base/$chosen/${parts[$k]}" "$ext" "$tmp/members.$k" || { bad=1; continue; }
    cat "$tmp/members.$k" >> "$tmp/members.all"
  done
  ((bad == 0)) || { log "$p: base backup $chosen did not read back complete"; return 1; }
  grep -qx 'global/pg_control' "$tmp/members.all" || { log "$p: base backup $chosen holds no global/pg_control"; return 1; }
  k=$((${#parts[@]} - 1))
  [[ $(tail -1 "$tmp/members.$k") == backup_label ]] \
    || { log "$p: ${parts[$k]} does not end with backup_label: a later data part is missing or the tar is cut"; return 1; }
  # WAL: segment directories (not xl.meta files) from begin_wal on, on its timeline
  bc_list "$tmp/segs.raw" "$view/$p/wals" -mindepth 2 -maxdepth 2 -type d || return 1
  while read -r o; do
    k=${o#"$view/"}; b=${k##*/}
    [[ $b =~ ^[0-9A-F]{24}(\.(gz|bz2|snappy|xz|lz4|zst))?$ ]] || continue
    if [[ ${b:0:8} > ${begin:0:8} ]]; then log "$p: a WAL directory on a later timeline than ${begin:0:8} ($b); check it by hand"; return 1; fi
    [[ ${b:0:8} == "${begin:0:8}" ]] && wal[${b:0:24}]+="$k "
  done < "$tmp/segs.raw"
  last=$(printf '%s\n' "${!wal[@]}" | LC_ALL=C sort | tail -1)
  [[ -n $last && ! $last < $end ]] || last=$end   # end_wal is due even without a directory: its absence fails below
  wal_walk "$begin" "$last" "$RB_SEG_SIZE" > "$tmp/segs" || { log "$p: WAL names outside the segment range"; return 1; }
  while read -r seg; do
    if [[ -z ${wal[$seg]:-} ]]; then log "$p: WAL $seg missing after base $chosen"; bad=1; continue; fi
    for k in ${wal[$seg]}; do rb_read "$k" || bad=1; done
    nw=$((nw + 1))
  done < "$tmp/segs"
  ((bad == 0)) || { log "$p: not every WAL segment read back"; return 1; }
  echo "$p $last" >> "$tmp/newest"
  log "$p: base backup $chosen (${#parts[@]} data parts, ends with backup_label) and $nw WAL segments $begin..$last read back through MinIO"
}

minio_readback() { # minio_readback <i> <read-only snapshot> <view>: 0 only when everything due read back
  local i=$1 snap=$2 view=$3 mnt rw uuid token f p last now rc=0 tmp prev
  prev=$STATE/minio-wal.${N[$i]}
  tmp=$(mktemp -d); rm -f "$prev.new"; : > "$tmp/newest"
  # prefixes from directories, plus every prefix the last committed generation read
  bc_list "$tmp/bases" "$view" -mindepth 3 -maxdepth 3 -type d -name base || { rm -rf "$tmp"; return 1; }
  while read -r f; do p=${f#"$view/"}; p=${p%/base}; [[ $p == .* ]] || echo "$p"; done < "$tmp/bases" | LC_ALL=C sort -u > "$tmp/prefixes"
  if [[ -f $prev ]]; then
    while read -r p last; do
      grep -Fxq "$p" "$tmp/prefixes" || { log "$p: the last committed generation read its WAL up to $last, and it is gone now"; rc=1; }
    done < "$prev"
  fi
  [[ -s $tmp/prefixes ]] || { log "${N[$i]}: no <bucket>/<server>/base directory"; rc=1; }
  if ((rc)); then rm -rf "$tmp"; return 1; fi
  mnt=$(findmnt -no TARGET -T "${ROOT[$i]}")
  rw="${mnt%/}/@bifrost/rollup-snap/${N[$i]}-rw-$STAMP-$RANDOM"
  btrfs subvolume snapshot "$snap" "$rw" > /dev/null || { log "${N[$i]}: no writable scratch snapshot"; rm -rf "$tmp"; return 1; }
  uuid=$(snap_uuid "$rw")
  record scratch "$rw" "${uuid:--}"
  [[ -n $uuid ]] || { log "$rw has no UUID"; rm -rf "$tmp"; return 1; }
  token="$STAMP-$$-$RANDOM"
  if rb_start "$RB_PREFIX$token" "$token" "$rw${SRC[$i]#"${ROOT[$i]}"}"; then
    while read -r p; do rb_prefix "$view" "$tmp" "$p" || rc=1; done < "$tmp/prefixes"
  else
    rc=1
  fi
  if ((rc == 0)) && [[ -f $prev ]]; then   # the newest WAL never goes back
    while read -r p last; do
      now=$(awk -v p="$p" '$1 == p { print $2 }' "$tmp/newest")
      [[ -n $now && ! $now < $last ]] || { log "$p: WAL now ends at ${now:-nothing}, before $last that the last committed generation read; if the archive was reset on purpose, remove that line from $prev"; rc=1; }
    done < "$prev"
  fi
  if ((rc == 0)); then cp "$tmp/newest" "$prev.new"; fi   # rollup.sh keeps it once the generation is committed
  # tear down now, whatever happened: the container first, the scratch copy only once it is gone
  if [[ -z $RB_CID ]] || drop_container "$RB_CID" "$token"; then drop_snapshot "$rw" "$uuid" rw; else pending_add "scratch $rw $uuid"; fi
  rm -rf "$tmp"
  return "$rc"
}
