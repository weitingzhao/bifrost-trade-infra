# shellcheck shell=bash
# TD-444 step 5 runbook §4 group 6: the MinIO stages of td444-move.sh (M0–M4b, the single
# fallback-eligibility table, A, and the M6 object checks). Sourced by td444-move.sh, never
# run alone; it uses that script's options, logging and phase files.
# shellcheck disable=SC2154  # globals come from td444-move.sh

# ---------------------------------------------------------------- MinIO (§4 group 6)
mphase() { phase "minio-$RUN_ID" "$@"; }
mhas() { has_phase "minio-$RUN_ID" "$@"; }
need_run() { [[ -n $RUN_ID ]] || die "--run-id is required"; [[ -f $(phase_file "minio-$RUN_ID") ]] || die "no run $RUN_ID (minio-m0 starts one)"; }
compose() { docker compose --project-directory "$COMPOSE_DIR" "$@"; }
running() { [[ $(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null) == true ]]; }
health_loop() { # health_loop exec|<url>
  local i
  for i in $(seq 1 24); do
    if [[ $1 == exec ]]; then
      if docker exec "$CONTAINER" curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null http://127.0.0.1:9000/minio/health/cluster; then return 0; fi
    elif curl --connect-timeout 3 --max-time 5 -fsS -o /dev/null "$1"; then
      return 0
    fi
    sleep 5
  done
  return 1
}
isolation_now() { # prints NetworkMode|PortBindings|networks of the container
  docker inspect "$CONTAINER" --format '{{.HostConfig.NetworkMode}}|{{json .HostConfig.PortBindings}}|{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
}
isolated_ok() { [[ $1 =~ ^none\|(\{\}|null)\|none\ $ ]]; }
lan_health_url() {
  local ip
  ip=$(docker inspect "$CONTAINER" --format '{{(index (index .HostConfig.PortBindings "9000/tcp") 0).HostIp}}')
  [[ -n $ip ]] || die "no host address bound for 9000/tcp"
  printf 'http://%s:9000/minio/health/cluster' "$ip"
}
eligibility() { # prints A or NO-A with the reason (one table, all branches, §4 group 6)
  if ! mhas attempt m4a; then echo "A no attempt m4a"; return; fi
  if mhas attempt m4b; then echo "NO-A m4b was attempted"; return; fi
  if mhas "done" isolation_proven_pre && mhas "done" isolation_reconfirmed; then echo "A isolation proven before start and reconfirmed after stop"; return; fi
  echo "NO-A m4a attempted without both isolation proofs"
}
objects_of() { # business objects (dirs holding xl.meta) under the bucket, relative to the data root
  find "$1/$BUCKET" -type f -name xl.meta -printf '%h\n' | sed "s#^$1/##" | LC_ALL=C sort
}

cmd_minio() {
  local stage=${CMD#minio-} f
  case $stage in
    eligibility)
      need_run; eligibility; [[ $(eligibility) == A* ]] && return 0 || return 3 ;;
    wal-layout)
      [[ -d $DATA ]] || die "--data <MinIO data dir>"
      log "WAL object directories (first and last 5):"
      find "$DATA/$BUCKET" -mindepth 4 -maxdepth 4 -path '*/wals/*' -type d -name '*' -printf '%P\n' | LC_ALL=C sort > "$STATE/logs/wal-layout.list"
      head -5 "$STATE/logs/wal-layout.list"; echo ...; tail -5 "$STATE/logs/wal-layout.list"
      log "suffixes:"; sed -E 's/.*\/[0-9A-F]{24}//' "$STATE/logs/wal-layout.list" | LC_ALL=C sort | uniq -c
      log "special files (.history .backup .partial):"; grep -E '\.(history|backup|partial)' "$STATE/logs/wal-layout.list" | head -20 || true
      return 0 ;;
    base-check)
      need_run; [[ -d $DATA ]] || die "--data <MinIO data dir>"
      f="$STATE/minio-$RUN_ID.base"; [[ -f $f ]] || die "no minio.base for $RUN_ID"
      if comm -23 <(grep -v '^#' "$f") <(objects_of "$DATA") | tee "$STATE/logs/minio-$RUN_ID.missing" | grep -q .; then
        die "objects of minio.base are missing (see $STATE/logs/minio-$RUN_ID.missing)"
      fi
      log "every object of minio.base is present"; return 0 ;;
    continuity)
      need_run; [[ -r $RANGE && -d $DATA ]] || die "--range <file> and --data <dir>"
      minio_continuity; return 0 ;;
  esac
  require_confirm minio
  case $stage in
    m0)
      [[ -n $RUN_ID ]] || die "--run-id is required"
      [[ ! -e $(phase_file "minio-$RUN_ID") ]] || die "run $RUN_ID exists; a new attempt needs a new run id"
      [[ $EXPECT_COMPOSE_SHA =~ ^[0-9a-f]{64}$ ]] || die "--expect-compose-sha256 <sha256 of the fa7e2e2 compose.yaml>"
      check_pkg
      mphase attempt m0
      { docker version --format '{{.Server.Version}}'; isolation_now; docker inspect "$CONTAINER" --format '{{json .NetworkSettings.Networks}}'
        for n in $(docker inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'); do
          docker network inspect "$n" --format '{{.Name}}: {{range $k, $v := .Containers}}{{$v.Name}} {{end}}'; done
      } > "$STATE/minio-$RUN_ID.m0"
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
      ! running || { mphase fail m1 "still running"; die "container still running"; }
      mphase "done" m1 ;;
    m2)
      need_run; mhas "done" m1 || die "m1 not done"
      [[ ! -e $STATE/minio-$RUN_ID.base ]] || die "minio.base of $RUN_ID exists; never reuse it"
      mphase attempt m2
      CONFIRM=minio cmd_final minio
      local i; i=$(entries minio | head -1)
      { printf '# minio.base %s %s objects at %s\n' "$RUN_ID" "$(objects_of "${M_DST[$i]}" | wc -l)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        objects_of "${M_DST[$i]}"; } > "$STATE/minio-$RUN_ID.base"
      head -1 "$STATE/minio-$RUN_ID.base"
      mphase "done" m2 ;;
    m3)
      need_run; mhas "done" m2 || die "m2 not done"; check_pkg
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
      mphase attempt m4a
      compose -f "$COMPOSE_DIR/compose.isolated.yaml" create minio || { mphase fail m4a "create failed"; die "create failed"; }
      f=$(isolation_now); log "isolation before start: $f"
      isolated_ok "$f" || { mphase fail m4a "not isolated: $f"; die "container is not isolated; do not start it"; }
      mphase "done" isolation_proven_pre
      compose -f "$COMPOSE_DIR/compose.isolated.yaml" start minio || { mphase fail m4a "start failed"; die "start failed"; }
      health_loop exec || { mphase fail m4a "health"; die "isolated MinIO never became healthy"; }
      mphase "done" m4a ;;
    m4a-stop)
      need_run; mhas attempt m4a || die "m4a was never attempted"
      if running; then compose -f "$COMPOSE_DIR/compose.isolated.yaml" stop minio; fi
      ! running || die "isolated container still running"
      f=$(isolation_now); log "isolation after stop: $f"
      isolated_ok "$f" || { mphase fail isolation_reconfirmed "$f"; die "isolation not reconfirmed: no A for this run"; }
      mphase "done" isolation_reconfirmed ;;
    m4b)
      need_run; mhas "done" m4a || die "m4a not done"
      ask_yes "M4b opens MinIO to the LAN; from now on A is impossible for run $RUN_ID."
      mphase attempt m4b
      compose -f "$COMPOSE_DIR/compose.yaml" up -d minio || { mphase fail m4b "up failed"; die "up failed"; }
      health_loop "$(lan_health_url)" || { mphase fail m4b "health"; die "MinIO not healthy on the LAN address"; }
      mphase "done" m4b ;;
    rollback-a)
      need_run
      log "eligibility: $(eligibility)"
      if mhas attempt m4a && ! mhas "done" isolation_reconfirmed; then
        CMD=minio-m4a-stop cmd_minio || true
      fi
      [[ $(eligibility) == A* ]] || die "A is not allowed for run $RUN_ID: $(eligibility). Recovery event (§4 group 6)."
      ! running || die "a MinIO container is running; stop it first"
      mphase attempt rollback-a
      [[ $(sha256sum "$COMPOSE_DIR/compose.yaml.orig-td444" | cut -d' ' -f1) == "$(cat "$STATE/minio-$RUN_ID.orig-sha256")" ]] || die "compose.yaml.orig-td444 changed"
      install -m 0644 "$COMPOSE_DIR/compose.yaml.orig-td444" "$COMPOSE_DIR/compose.yaml"
      compose -f "$COMPOSE_DIR/compose.yaml" up -d minio || { mphase fail rollback-a "up failed"; die "old MinIO did not start"; }
      health_loop "$(lan_health_url)" || { mphase fail rollback-a "health"; die "old MinIO not healthy"; }
      mphase "done" rollback-a
      log "old MinIO is up. Rollback succeeds only once condition R holds (runbook §4 group 6)." ;;
    readback)
      need_run; [[ -f $STATE/minio-$RUN_ID.range-list && -f $STATE/minio-$RUN_ID.base ]] || die "run minio-continuity first"
      minio_readback ;;
    *) die "unknown command $CMD" ;;
  esac
}

minio_continuity() { # range file: L= U= SEGMENT_SIZE= TIMELINE= WAL_PREFIX= SUFFIX=
  local L U SEG TLI PREFIX SUFFIX per t log seg name missing=0 count=0 out
  L=$(sed -n 's/^L=//p' "$RANGE"); U=$(sed -n 's/^U=//p' "$RANGE"); SEG=$(sed -n 's/^SEGMENT_SIZE=//p' "$RANGE")
  TLI=$(sed -n 's/^TIMELINE=//p' "$RANGE"); PREFIX=$(sed -n 's/^WAL_PREFIX=//p' "$RANGE"); SUFFIX=$(sed -n 's/^SUFFIX=//p' "$RANGE")
  [[ $L =~ ^[0-9A-F]{24}$ && $U =~ ^[0-9A-F]{24}$ && $TLI =~ ^[0-9A-F]{8}$ && $SEG =~ ^[0-9]+$ ]] || die "range file needs L, U, TIMELINE (hex) and SEGMENT_SIZE"
  [[ $PREFIX =~ ^[A-Za-z0-9._/-]+$ && $PREFIX != *..* && $SUFFIX =~ ^[A-Za-z0-9.]*$ ]] || die "bad WAL_PREFIX or SUFFIX"
  [[ ${L:0:8} == "$TLI" && ${U:0:8} == "$TLI" ]] || die "L and U are not on timeline $TLI: stop the normal check (recovery event)"
  per=$(( 0x100000000 / SEG ))
  log=$(( 16#${L:8:8} )); seg=$(( 16#${L:16:8} ))
  t=$(( 16#${U:8:8} * per + 16#${U:16:8} ))
  (( log * per + seg <= t )) || die "L is after U"
  out="$STATE/minio-$RUN_ID.range-list"; : > "$out"
  while (( log * per + seg <= t )); do
    name=$(printf '%s%08X%08X' "$TLI" "$log" "$seg")
    printf '%s/%s/%s%s\n' "$PREFIX" "${name:0:16}" "$name" "$SUFFIX" >> "$out"
    [[ -f $DATA/$PREFIX/${name:0:16}/$name$SUFFIX/xl.meta ]] || { log "missing segment $name"; missing=$((missing + 1)); }
    count=$((count + 1)); seg=$((seg + 1)); if ((seg == per)); then seg=0; log=$((log + 1)); fi
  done
  ((missing == 0)) || die "$missing of $count segments from $L to $U are missing: M6 not passed"
  log "all $count segments from $L to $U are present (list $out)"
}
minio_readback() {
  local obj bad=0 n=0
  while read -r obj; do
    grep -Fxq "$obj" "$STATE/minio-$RUN_ID.base" && continue
    n=$((n + 1))
    case $METHOD in
      mc) docker exec "$CONTAINER" sh -c 'mc alias set td444 http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && mc cat "td444/$0" > /dev/null' "$obj" ;;
      curl-sigv4) docker exec "$CONTAINER" sh -c 'curl --connect-timeout 3 --max-time 60 -fsS --aws-sigv4 "aws:amz:us-east-1:s3" --user "$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD" -o /dev/null "http://127.0.0.1:9000/$0"' "$obj" ;;
      *) die "--method mc|curl-sigv4" ;;
    esac && log "read back $obj" || { log "COULD NOT READ $obj"; bad=1; }
  done < "$STATE/minio-$RUN_ID.range-list"
  ((bad == 0)) || die "read-back failed: M6 item 3 not passed (pending readability acceptance)"
  log "read back all $n objects archived after M1"
}

