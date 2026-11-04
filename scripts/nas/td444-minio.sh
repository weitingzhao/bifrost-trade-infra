# shellcheck shell=bash
# TD-444 step 5 runbook §4 group 6: the MinIO stages of td444-move.sh (M0–M4b, the single
# fallback-eligibility table, A, and the M6 object checks). Sourced by td444-move.sh, never
# run alone; it uses that script's options, logging, phase files and copy guard.
#
# Evidence rules: a container state counts only when docker inspect answered and said so
# (an inspect error is never "stopped"); M4a runs once per run, and its isolation proofs
# name the container they were taken on; a reconfirmation first records its attempt, which
# voids the earlier proof until it ends in done, and any failure of it is recorded (A is
# then void); rollback-a reconfirms the current container before it starts anything; every
# docker call obeys --timeout.
# shellcheck disable=SC2154  # globals come from td444-move.sh

mphase() { phase "minio-$RUN_ID" "$@"; }
mhas() { has_phase "minio-$RUN_ID" "$@"; }
mfile() { phase_file "minio-$RUN_ID"; }
need_run() { [[ -n $RUN_ID ]] || die "--run-id is required"; [[ -f $(mfile) ]] || die "no run $RUN_ID (minio-m0 starts one)"; }
dkr() { if ((TIMEOUT > 0)); then timeout "$TIMEOUT" docker "$@"; else docker "$@"; fi; }
compose() { dkr compose --project-directory "$COMPOSE_DIR" "$@"; }
container_state() { # prints true or false; fails when docker could not tell
  local st
  st=$(dkr inspect -f '{{.State.Running}}' "$CONTAINER" 2> /dev/null) || return 1
  [[ $st == true || $st == false ]] || return 1
  printf '%s' "$st"
}
require_stopped() {
  local st
  st=$(container_state) || die "docker inspect gave no answer: the container is not proven stopped"
  [[ $st == false ]] || die "the container is running"
}
container_id() {
  local id
  id=$(dkr inspect -f '{{.Id}}' "$CONTAINER" 2> /dev/null) || die "docker inspect gave no container id"
  [[ $id =~ ^[A-Za-z0-9-]+$ ]] || die "unexpected container id '$id'"
  printf '%s' "$id"
}
health_loop() { # health_loop exec|<url>
  local i
  for i in $(seq 1 24); do
    if [[ $1 == exec ]]; then
      if dkr exec "$CONTAINER" curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null http://127.0.0.1:9000/minio/health/cluster; then return 0; fi
    elif curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null "$1"; then
      return 0
    fi
    sleep 5
  done
  return 1
}
isolation_now() { # NetworkMode|PortBindings|networks
  dkr inspect "$CONTAINER" --format '{{.HostConfig.NetworkMode}}|{{json .HostConfig.PortBindings}}|{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
}
isolated_ok() { [[ $1 =~ ^none\|(\{\}|null)\|none\ $ ]]; }
lan_health_url() {
  local ip
  ip=$(dkr inspect "$CONTAINER" --format '{{(index (index .HostConfig.PortBindings "9000/tcp") 0).HostIp}}') || die "no host address bound for 9000/tcp"
  [[ -n $ip ]] || die "no host address bound for 9000/tcp"
  printf 'http://%s:9000/minio/health/cluster' "$ip"
}
proof_cid() { { grep -E " done $1 " "$(mfile)" || true; } | tail -1 | awk '{print $NF}'; }
eligibility() { # the one table (runbook §4 group 6): prints A or NO-A with the reason
  local n last
  if grep -Eq ' fail current_container( |$)' "$(mfile)"; then echo "NO-A the current container is not the one this run stopped"; return; fi
  n=$(grep -Ec ' attempt m4a( |$)' "$(mfile)" || true)
  if ((n == 0)); then echo "A no attempt m4a"; return; fi
  if ((n > 1)); then echo "NO-A m4a was attempted $n times in this run"; return; fi
  if mhas attempt m4b; then echo "NO-A m4b was attempted"; return; fi
  if grep -Eq ' fail isolation_' "$(mfile)"; then echo "NO-A an isolation proof failed"; return; fi
  last=$({ grep -E ' (attempt|done|fail) isolation_reconfirmed( |$)' "$(mfile)" || true; } | tail -1)
  if [[ -n $last && $last != *" done isolation_reconfirmed "* ]]; then echo "NO-A the last isolation reconfirmation did not finish"; return; fi
  local a b
  a=$(proof_cid isolation_proven_pre); b=$(proof_cid isolation_reconfirmed)
  if [[ -n $a && $a == "$b" ]]; then echo "A isolation of $a proven before start and reconfirmed after stop"; return; fi
  echo "NO-A m4a attempted without both isolation proofs on the same container"
}
reconfirm() { # stop the isolated container if needed, then prove: stopped, the proven ID, isolated
  local want st cid f
  mphase attempt isolation_reconfirmed   # voids any earlier proof until this one ends in done
  want=$(proof_cid isolation_proven_pre)
  [[ -n $want ]] || { mphase fail isolation_reconfirmed "no proof before start"; die "no isolation proof before start: no A for run $RUN_ID"; }
  st=$(container_state) || st=unknown
  if [[ $st != false ]]; then compose -f "$COMPOSE_DIR/compose.isolated.yaml" stop minio || log "compose stop returned an error"; fi
  st=$(container_state) || { mphase fail isolation_reconfirmed "inspect gave no answer"; die "the container is not proven stopped: no A for run $RUN_ID"; }
  [[ $st == false ]] || { mphase fail isolation_reconfirmed "still running"; die "the container still runs: no A for run $RUN_ID"; }
  cid=$(dkr inspect -f '{{.Id}}' "$CONTAINER" 2> /dev/null) || { mphase fail isolation_reconfirmed "no container id"; die "docker gave no container id: no A for run $RUN_ID"; }
  [[ $cid == "$want" ]] || { mphase fail isolation_reconfirmed "container $cid is not $want"; die "this is not the container proven isolated ($cid): no A for run $RUN_ID"; }
  f=$(isolation_now) || { mphase fail isolation_reconfirmed "inspect failed"; die "inspect failed: no A for run $RUN_ID"; }
  log "isolation after stop of $cid: $f"
  isolated_ok "$f" || { mphase fail isolation_reconfirmed "not isolated: $f"; die "isolation not reconfirmed: no A for run $RUN_ID"; }
  mphase "done" isolation_reconfirmed "1 $cid"
}
current_is_m1() { # without M4a: still the container m1 stopped (same ID = its old config), stopped
  local st cid
  cid=$(dkr inspect -f '{{.Id}}' "$CONTAINER" 2> /dev/null) || { mphase fail current_container "no container id"; die "docker gave no container id: no A for run $RUN_ID"; }
  [[ $cid == "$(proof_cid m1)" ]] || { mphase fail current_container "container $cid is not the one m1 stopped"; die "the container ($cid) is not the one m1 stopped: no A for run $RUN_ID"; }
  st=$(container_state) || { mphase fail current_container "inspect gave no answer"; die "the container is not proven stopped: no A for run $RUN_ID"; }
  [[ $st == false ]] || die "the container m1 stopped runs again (its old config); stop it, then repeat rollback-a"
  mphase "done" current_container "$cid"
}
objects_of() { # business objects (dirs holding xl.meta) under the bucket, relative to the data root
  find "$1/$BUCKET" -type f -name xl.meta -printf '%h\n' | sed "s#^$1/##" | LC_ALL=C sort
}
RANGE_KEYS=(L U SEGMENT_SIZE TIMELINE WAL_PREFIX SUFFIX RP_NAME RP_END U_FROM_RP SWITCH_RETURN PRIMARY TIMELINE_ID STATS_RESET COLLECTED_AT)
range_get() { sed -n "s/^$1=//p" "$RANGE" | head -1; }

cmd_minio() {
  local stage=${CMD#minio-} f tmp cid
  case $stage in
    eligibility)
      need_run; eligibility; [[ $(eligibility) == A* ]] && return 0 || return 3 ;;
    wal-layout)
      [[ -d $DATA ]] || die "--data <MinIO data dir>"
      f="$STATE/logs/wal-layout.list"
      bc_list "$f.raw" "$DATA/$BUCKET" -mindepth 4 -maxdepth 4 -path '*/wals/*' -type d || die "listing failed"
      sed "s#^$DATA/$BUCKET/##" "$f.raw" | LC_ALL=C sort > "$f"
      log "WAL object directories (first and last 5) of $(wc -l < "$f"):"; head -5 "$f"; echo ...; tail -5 "$f"
      log "suffixes:"; sed -E 's/.*\/[0-9A-F]{24}//' "$f" | LC_ALL=C sort | uniq -c
      log "special files (.history .backup .partial):"; grep -E '\.(history|backup|partial)' "$f" | head -20 || true
      return 0 ;;
    base-check)
      need_run; [[ -n $DATA ]] || die "--data <MinIO data dir>"
      f="$STATE/minio-$RUN_ID.base"
      [[ -f $f && $(head -1 "$f") == "# minio.base $RUN_ID "* ]] || die "no minio.base of run $RUN_ID"
      tmp=$(mktemp -d)
      grep -v '^#' "$f" > "$tmp/base" || true
      [[ -s $tmp/base ]] || die "minio.base of $RUN_ID lists no objects"
      objects_of "$DATA" > "$tmp/now" || die "listing the objects of $DATA failed"
      comm -23 "$tmp/base" "$tmp/now" > "$tmp/missing" || die "comparing the object lists failed"
      if [[ -s $tmp/missing ]]; then
        cp "$tmp/missing" "$STATE/logs/minio-$RUN_ID.missing"
        die "$(wc -l < "$tmp/missing") objects of minio.base are missing (see $STATE/logs/minio-$RUN_ID.missing)"
      fi
      log "all $(wc -l < "$tmp/base") objects of minio.base are present"; rm -rf "$tmp"; return 0 ;;
    continuity)
      need_run; [[ -r $RANGE && -d $DATA ]] || die "--range <file> and --data <dir>"
      minio_continuity; return 0 ;;
  esac
  require_confirm minio
  no_active_copy
  case $stage in
    m0)
      [[ -n $RUN_ID ]] || die "--run-id is required"
      [[ ! -e $(mfile) ]] || die "run $RUN_ID exists; a new attempt needs a new run id"
      [[ $EXPECT_COMPOSE_SHA =~ ^[0-9a-f]{64}$ ]] || die "--expect-compose-sha256 <sha256 of the fa7e2e2 compose.yaml>"
      check_pkg
      mphase attempt m0
      { dkr version --format '{{.Server.Version}}'; isolation_now; dkr inspect "$CONTAINER" --format '{{json .NetworkSettings.Networks}}'
        for n in $(dkr inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'); do
          dkr network inspect "$n" --format '{{.Name}}: {{range $k, $v := .Containers}}{{$v.Name}} {{end}}'; done
      } > "$STATE/minio-$RUN_ID.m0" || { mphase fail m0 "docker did not answer"; die "docker inspect failed"; }
      cat "$STATE/minio-$RUN_ID.m0"
      [[ $(sha256sum "$COMPOSE_DIR/compose.yaml" | cut -d' ' -f1) == "$EXPECT_COMPOSE_SHA" ]] || { mphase fail m0 "compose.yaml is not the expected version"; die "compose.yaml differs from the expected version"; }
      if [[ -e $COMPOSE_DIR/compose.yaml.orig-td444 ]]; then
        [[ $(sha256sum "$COMPOSE_DIR/compose.yaml.orig-td444" | cut -d' ' -f1) == "$EXPECT_COMPOSE_SHA" ]] || die "compose.yaml.orig-td444 exists with other content; not overwriting"
      else
        cp -p "$COMPOSE_DIR/compose.yaml" "$COMPOSE_DIR/compose.yaml.orig-td444"; chmod 0444 "$COMPOSE_DIR/compose.yaml.orig-td444"
      fi
      printf '%s\n' "$EXPECT_COMPOSE_SHA" > "$STATE/minio-$RUN_ID.orig-sha256"
      mphase "done" m0 ;;
    m1)
      need_run; mhas "done" m0 || die "m0 not done"
      mphase attempt m1
      compose -f "$COMPOSE_DIR/compose.yaml" stop minio || { mphase fail m1 "stop failed"; die "stop failed"; }
      local st; st=$(container_state) || { mphase fail m1 "inspect gave no answer"; die "the container is not proven stopped"; }
      [[ $st == false ]] || { mphase fail m1 "still running"; die "container still running"; }
      cid=$(container_id)
      mphase "done" m1 "$cid" ;;
    m2)
      need_run; mhas "done" m1 || die "m1 not done"
      require_stopped
      cid=$(container_id)
      [[ $cid == "$(proof_cid m1)" ]] || die "the container is not the one m1 stopped ($cid)"
      [[ ! -e $STATE/minio-$RUN_ID.base ]] || die "minio.base of $RUN_ID exists; never reuse it"
      mphase attempt m2
      CONFIRM=minio cmd_final minio
      require_stopped
      local i; i=$(entries minio | head -1)
      tmp=$(mktemp)
      objects_of "${M_DST[$i]}" > "$tmp" || { mphase fail m2 "listing failed"; die "listing the objects failed"; }
      [[ -s $tmp ]] || { mphase fail m2 "no objects"; die "no objects under ${M_DST[$i]}/$BUCKET"; }
      { printf '# minio.base %s %s objects at %s\n' "$RUN_ID" "$(wc -l < "$tmp")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; cat "$tmp"; } > "$STATE/minio-$RUN_ID.base"
      rm -f "$tmp"; head -1 "$STATE/minio-$RUN_ID.base"
      mphase "done" m2 ;;
    m3)
      need_run; mhas "done" m2 || die "m2 not done"; check_pkg; require_stopped
      mphase attempt m3
      for f in compose.yaml compose.isolated.yaml compose.recovery.yaml; do
        install -m 0644 "$PKG/k8s/data/minio/nas/$f" "$COMPOSE_DIR/$f.td444-new"
      done
      compose -f "$COMPOSE_DIR/compose.yaml.td444-new" config --quiet || { mphase fail m3 "compose.yaml invalid"; die "new compose.yaml does not validate"; }
      compose -f "$COMPOSE_DIR/compose.isolated.yaml.td444-new" config --quiet || { mphase fail m3 "isolated invalid"; die "compose.isolated.yaml does not validate"; }
      for f in compose.yaml compose.isolated.yaml compose.recovery.yaml; do mv "$COMPOSE_DIR/$f.td444-new" "$COMPOSE_DIR/$f"; done
      grep -q '^      - /volume2/minio-backup/data:/data$' "$COMPOSE_DIR/compose.yaml" || die "compose.yaml does not bind /volume2/minio-backup/data"
      mphase "done" m3 ;;
    m4a)
      need_run; mhas "done" m3 || die "m3 not done"
      ! grep -Eq ' attempt m4a( |$)' "$(mfile)" || die "m4a was already attempted in run $RUN_ID; this run's fallback is decided by minio-eligibility"
      require_stopped
      mphase attempt m4a 1
      compose -f "$COMPOSE_DIR/compose.isolated.yaml" create minio || { mphase fail m4a 1; die "create failed"; }
      cid=$(container_id)
      f=$(isolation_now) || { mphase fail isolation_proven_pre 1; die "inspect failed; do not start"; }
      log "isolation before start of $cid: $f"
      isolated_ok "$f" || { mphase fail isolation_proven_pre 1; die "container is not isolated; do not start it"; }
      mphase "done" isolation_proven_pre "1 $cid"
      compose -f "$COMPOSE_DIR/compose.isolated.yaml" start minio || { mphase fail m4a 1; die "start failed"; }
      health_loop exec || { mphase fail m4a 1; die "isolated MinIO never became healthy"; }
      mphase "done" m4a 1 ;;
    m4a-stop)
      need_run; mhas attempt m4a || die "m4a was never attempted"
      reconfirm ;;
    m4b)
      need_run; mhas "done" m4a || die "m4a not done"
      ask_yes "M4b opens MinIO to the LAN; from now on A is impossible for run $RUN_ID."
      mphase attempt m4b
      compose -f "$COMPOSE_DIR/compose.yaml" up -d minio || { mphase fail m4b "up failed"; die "up failed"; }
      health_loop "$(lan_health_url)" || { mphase fail m4b "health"; die "MinIO not healthy on the LAN address"; }
      mphase "done" m4b ;;
    rollback-a)
      need_run
      log "eligibility before the check: $(eligibility)"
      [[ $(eligibility) == A* ]] || die "A is not allowed for run $RUN_ID: $(eligibility). Recovery event (§4 group 6)."
      # the container A restarts from must be the proven one, now: stopped, same ID, isolated
      if mhas attempt m4a; then reconfirm; else mhas "done" m1 || die "m1 not done: nothing to roll back"; current_is_m1; fi
      log "eligibility: $(eligibility)"
      [[ $(eligibility) == A* ]] || die "A is not allowed for run $RUN_ID: $(eligibility). Recovery event (§4 group 6)."
      mphase attempt rollback-a
      [[ $(sha256sum "$COMPOSE_DIR/compose.yaml.orig-td444" | cut -d' ' -f1) == "$(cat "$STATE/minio-$RUN_ID.orig-sha256")" ]] || die "compose.yaml.orig-td444 changed"
      install -m 0644 "$COMPOSE_DIR/compose.yaml.orig-td444" "$COMPOSE_DIR/compose.yaml"
      compose -f "$COMPOSE_DIR/compose.yaml" up -d minio || { mphase fail rollback-a "up failed"; die "old MinIO did not start"; }
      health_loop "$(lan_health_url)" || { mphase fail rollback-a "health"; die "old MinIO not healthy"; }
      mphase "done" rollback-a
      log "old MinIO is up. Rollback succeeds only once condition R holds (runbook §4 group 6)." ;;
    readback)
      need_run; minio_readback ;;
    *) die "unknown command $CMD" ;;
  esac
}

minio_continuity() { # object presence of every segment L..U; R and the database-side checks stay with the coordinator
  local k L U SEG TLI PREFIX SUFFIX per name missing=0 count=0 out tmp
  for k in "${RANGE_KEYS[@]}"; do [[ -n $(range_get "$k") ]] || die "range file lacks $k (template td444-range.example)"; done
  L=$(range_get L); U=$(range_get U); SEG=$(range_get SEGMENT_SIZE); TLI=$(range_get TIMELINE)
  PREFIX=$(range_get WAL_PREFIX); SUFFIX=$(range_get SUFFIX)
  [[ $L =~ ^[0-9A-F]{24}$ && $U =~ ^[0-9A-F]{24}$ && $TLI =~ ^[0-9A-F]{8}$ && $SEG =~ ^[0-9]+$ ]] || die "range file needs L, U, TIMELINE (hex) and SEGMENT_SIZE"
  (( SEG >= 1048576 && SEG <= 1073741824 && (SEG & (SEG - 1)) == 0 )) || die "SEGMENT_SIZE $SEG is not a power of two between 1 MiB and 1 GiB"
  per=$(( 0x100000000 / SEG ))
  (( 16#${L:16:8} < per && 16#${U:16:8} < per )) || die "a segment number of L or U is past the end of its log ($per segments)"
  [[ $(range_get U_FROM_RP) == "$U" ]] || die "U is not the segment the restore point named (U_FROM_RP)"
  [[ $(range_get RP_NAME) =~ ^td444-[A-Za-z0-9-]+$ ]] || die "RP_NAME must be td444-<run id>"
  for k in RP_END SWITCH_RETURN; do [[ $(range_get "$k") =~ ^[0-9A-F]+/[0-9A-F]+$ ]] || die "$k is not an LSN"; done
  [[ $(range_get TIMELINE_ID) =~ ^[0-9]+$ ]] && (( $(range_get TIMELINE_ID) == 16#$TLI )) || die "TIMELINE_ID does not match TIMELINE"
  [[ $PREFIX =~ ^[A-Za-z0-9._/-]+$ && $PREFIX != *..* && $SUFFIX =~ ^[A-Za-z0-9.]*$ ]] || die "bad WAL_PREFIX or SUFFIX"
  [[ ${L:0:8} == "$TLI" && ${U:0:8} == "$TLI" ]] || die "L and U are not on timeline $TLI: stop the normal check (recovery event)"
  [[ ! $U < $L ]] || die "L is after U"
  out="$STATE/minio-$RUN_ID.range-list"; tmp="$out.tmp"
  rm -f "$out" "$STATE/minio-$RUN_ID.range.ok"
  wal_walk "$L" "$U" "$SEG" > "$tmp.names" || die "cannot walk from $L to $U"
  : > "$tmp"
  while read -r name; do
    printf '%s/%s/%s%s\n' "$PREFIX" "${name:0:16}" "$name" "$SUFFIX" >> "$tmp"
    [[ -f $DATA/$PREFIX/${name:0:16}/$name$SUFFIX/xl.meta ]] || { log "missing segment $name"; missing=$((missing + 1)); }
    count=$((count + 1))
  done < "$tmp.names"
  rm -f "$tmp.names"
  if ((missing > 0)); then rm -f "$tmp"; die "$missing of $count segments from $L to $U are missing: M6 not passed"; fi
  mv "$tmp" "$out"
  printf '%s %s\n' "$(sha256sum "$RANGE" | cut -d' ' -f1)" "$(sha256sum "$out" | cut -d' ' -f1)" > "$STATE/minio-$RUN_ID.range.ok"
  log "all $count segments from $L to $U are present (list $out)"
  log "object presence only: R, primary/timeline/stats_reset identity, U within 15 minutes and new .history stay the coordinator's checks (runbook §4 group 6)"
}
minio_readback() {
  local obj bad=0 n=0 ok start=$SECONDS
  [[ -r $RANGE ]] || die "--range <the range file of the passing continuity check>"
  ok="$STATE/minio-$RUN_ID.range.ok"
  [[ -f $ok && -f $STATE/minio-$RUN_ID.range-list && -f $STATE/minio-$RUN_ID.base ]] || die "no passing minio-continuity for run $RUN_ID"
  [[ $(cat "$ok") == "$(sha256sum "$RANGE" | cut -d' ' -f1) $(sha256sum "$STATE/minio-$RUN_ID.range-list" | cut -d' ' -f1)" ]] \
    || die "the range list does not belong to this range file and a passing check"
  while read -r obj; do
    grep -Fxq "$obj" "$STATE/minio-$RUN_ID.base" && continue
    if ((TIMEOUT > 0 && SECONDS - start >= TIMEOUT)); then die "read-back passed its --timeout after $n objects"; fi
    n=$((n + 1))
    case $METHOD in
      mc) dkr exec "$CONTAINER" sh -c 'mc alias set td444 http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && mc cat "td444/$0" > /dev/null' "$obj" ;;
      curl-sigv4) dkr exec "$CONTAINER" sh -c 'curl --connect-timeout 3 --max-time 60 -fsS --aws-sigv4 "aws:amz:us-east-1:s3" --user "$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD" -o /dev/null "http://127.0.0.1:9000/$0"' "$obj" ;;
      *) die "--method mc|curl-sigv4" ;;
    esac && log "read back $obj" || { log "COULD NOT READ $obj"; bad=1; }
  done < "$STATE/minio-$RUN_ID.range-list"
  ((bad == 0)) || die "read-back failed: M6 item 3 not passed (pending readability acceptance)"
  log "read back all $n objects archived after M1"
}
