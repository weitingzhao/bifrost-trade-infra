# shellcheck shell=bash
# TD-444 step 5 runbook §3.3: the copy guard of td444-move.sh. Sourced, never run alone.
#
# Every long copy runs in its own process group (setsid) under:
#   - the SSD temperature guard: pause at TEMP_PAUSE, resume at or below TEMP_RESUME, and
#     pause when not every one of TEMP_SENSORS sensors gave a reading for TEMP_MISSING s;
#   - --timeout;
#   - the abort traps: INT, TERM and HUP of the script, and its exit, stop the copy group
#     (continue, terminate, kill after 30 s), wait until the group is gone, remove
#     $STATE/active-copy and record the abort. Commands that start, switch or delete refuse
#     while an active copy with a live process group is recorded (no_active_copy).
# shellcheck disable=SC2154  # globals come from td444-move.sh

ACTIVE_PGID="" ABORT_PHASE="" ABORT_STAGE=""

max_temp() { # highest temperature in °C; empty unless all TEMP_SENSORS sensors gave a reading
  local h t best="" n=0
  for h in "$HWMON"/hwmon*; do
    [[ -r $h/name && $(cat "$h/name") == "$TEMP_NAME" ]] || continue
    t=$(cat "$h/temp1_input" 2> /dev/null) || continue
    [[ $t =~ ^[0-9]+$ ]] || continue
    n=$((n + 1)); t=$((t / 1000))
    if [[ -z $best ]] || ((t > best)); then best=$t; fi
  done
  if ((n >= TEMP_SENSORS)); then printf '%s' "$best"; fi
  return 0
}

stop_group() { # stop_group <pgid> <why>: returns only when the group is gone
  local g=$1
  kill -0 -- "-$g" 2> /dev/null || return 0
  log "stopping the copy (process group $g): $2" >&2
  kill -CONT -- "-$g" 2> /dev/null || true
  kill -TERM -- "-$g" 2> /dev/null || true
  for _ in $(seq 1 30); do kill -0 -- "-$g" 2> /dev/null || break; sleep 1; done
  if kill -0 -- "-$g" 2> /dev/null; then kill -KILL -- "-$g" 2> /dev/null || true; sleep 1; fi
  if kill -0 -- "-$g" 2> /dev/null; then log "copy group $g is still alive after KILL" >&2; return 1; fi
  log "copy group $g has exited" >&2
}
on_abort() {
  trap - INT TERM HUP
  # an outer timeout signals the whole process group, tee included: stop writing through
  # the pipe, or the first log line would kill this handler with SIGPIPE
  trap '' PIPE
  exec >> "$LOG" 2>&1
  if [[ -n $ACTIVE_PGID ]]; then stop_group "$ACTIVE_PGID" "signal $1" || true; ACTIVE_PGID=""; fi
  rm -f "$STATE/active-copy"
  if [[ -n $ABORT_PHASE ]]; then phase "$ABORT_PHASE" fail "${ABORT_STAGE:-copy}" "aborted by $1"; fi
  log "aborted by $1; no copy of this run is left running"
  exit 130
}
on_exit_guard() {
  if [[ -n $ACTIVE_PGID ]]; then stop_group "$ACTIVE_PGID" "script exit" || true; rm -f "$STATE/active-copy"; fi
}
trap 'on_abort INT' INT
trap 'on_abort TERM' TERM
trap 'on_abort HUP' HUP
trap on_exit_guard EXIT

no_active_copy() { # refuse while a copy recorded by any run is still alive
  local g
  [[ -f $STATE/active-copy ]] || return 0
  g=$(cut -d' ' -f1 "$STATE/active-copy")
  if [[ $g =~ ^[0-9]+$ ]] && kill -0 -- "-$g" 2> /dev/null; then
    die "a copy (process group $g, $(cut -d' ' -f2- "$STATE/active-copy")) is still running; stop it before $CMD"
  fi
  log "removing a stale active-copy record: $(cat "$STATE/active-copy")"
  rm -f "$STATE/active-copy"
}

guarded() { # guarded <command...>: run it under the guard; returns its exit code (124 on --timeout)
  local pid rc=0 start=$SECONDS paused=0 missing_since="" last_poll=-1000000 t
  setsid "$@" &
  pid=$!
  ACTIVE_PGID=$pid
  printf '%s %s %s\n' "$pid" "$CMD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/active-copy"
  while kill -0 "$pid" 2> /dev/null; do
    if ((TIMEOUT > 0 && SECONDS - start >= TIMEOUT)); then
      stop_group "$pid" "timeout after ${TIMEOUT}s" || true
      wait "$pid" 2> /dev/null || true
      ACTIVE_PGID=""; rm -f "$STATE/active-copy"
      return 124
    fi
    if ((SECONDS - last_poll >= TEMP_POLL)); then
      last_poll=$SECONDS
      t=$(max_temp)
      if [[ -z $t ]]; then
        [[ -n $missing_since ]] || missing_since=$SECONDS
        if ((paused == 0 && SECONDS - missing_since >= TEMP_MISSING)); then
          kill -STOP -- "-$pid"; paused=1; log "no reading from every SSD sensor for ${TEMP_MISSING}s: copy paused" >&2
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
  ACTIVE_PGID=""; rm -f "$STATE/active-copy"
  return "$rc"
}
