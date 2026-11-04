# shellcheck shell=bash
# TD-444 step 5 runbook §3.3: the copy guard of td444-move.sh. Sourced, never run alone.
#
# Every long copy runs in its own process group (setsid) under:
#   - the SSD temperature guard: any known reading at or above TEMP_PAUSE pauses at once,
#     whether or not every sensor answered; fewer than TEMP_SENSORS readings for
#     TEMP_MISSING s pause too; the copy resumes only when all TEMP_SENSORS sensors read and
#     the highest is at or below TEMP_RESUME. The reason of a pause is logged and kept in
#     $STATE/copy-paused while it lasts;
#   - --timeout;
#   - the abort traps: INT, TERM and HUP of the script, and its exit, stop the copy group
#     (continue, terminate, kill after 30 s). Only a group that is gone releases
#     $STATE/active-copy. A group still alive after KILL keeps the record, marked
#     stop-failed; the log says the copy did NOT stop and the script exits 131 (a --timeout
#     that cannot stop its copy returns 125 at once, it does not wait for the copy). Every
#     writing command, and every new copy, refuses while a recorded group is alive.
# shellcheck disable=SC2154  # globals come from td444-move.sh

ACTIVE_PGID="" ABORT_PHASE="" ABORT_STAGE="" STOP_FAILED="" TEMP_MAX="" TEMP_N=0

read_temps() { # sets TEMP_MAX (highest known reading in °C, or empty) and TEMP_N (sensors read)
  local h t
  TEMP_MAX="" TEMP_N=0
  for h in "$HWMON"/hwmon*; do
    [[ -r $h/name && $(cat "$h/name") == "$TEMP_NAME" ]] || continue
    t=$(cat "$h/temp1_input" 2> /dev/null) || continue
    [[ $t =~ ^[0-9]+$ ]] || continue
    TEMP_N=$((TEMP_N + 1)); t=$((t / 1000))
    if [[ -z $TEMP_MAX ]] || ((t > TEMP_MAX)); then TEMP_MAX=$t; fi
  done
}

stop_group() { # stop_group <pgid> <why>: 0 only when the group is gone
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
release_or_keep() { # release_or_keep <why>: stop ACTIVE_PGID; 0 = gone and released, 1 = record kept as stop-failed
  local g=$ACTIVE_PGID started
  ACTIVE_PGID=""
  rm -f "$STATE/copy-paused"
  if stop_group "$g" "$1"; then rm -f "$STATE/active-copy"; return 0; fi
  started=$(cut -d' ' -f3 "$STATE/active-copy" 2> /dev/null || true)
  printf '%s %s %s stop-failed after %s (started %s)\n' "$g" "$CMD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${started:-?}" \
    > "$STATE/active-copy.new" && mv "$STATE/active-copy.new" "$STATE/active-copy"
  log "the copy (process group $g) did NOT stop after $1: $STATE/active-copy is kept, and every writing command refuses until the group is gone (runbook §3.8 item 7)" >&2
  STOP_FAILED=$g
  return 1
}
on_abort() {
  trap - INT TERM HUP
  # an outer timeout signals the whole process group, tee included: stop writing through
  # the pipe, or the first log line would kill this handler with SIGPIPE
  trap '' PIPE
  exec >> "$LOG" 2>&1
  if [[ -n $ACTIVE_PGID ]]; then release_or_keep "signal $1" || true; fi
  if [[ -n $STOP_FAILED ]]; then
    if [[ -n $ABORT_PHASE ]]; then phase "$ABORT_PHASE" fail "${ABORT_STAGE:-copy}" "aborted by $1; copy group $STOP_FAILED did not stop"; fi
    log "aborted by $1; the copy (process group $STOP_FAILED) did NOT stop"
    exit 131
  fi
  if [[ -n $ABORT_PHASE ]]; then phase "$ABORT_PHASE" fail "${ABORT_STAGE:-copy}" "aborted by $1"; fi
  log "aborted by $1; no copy of this run is left running"
  exit 130
}
on_exit_guard() {
  if [[ -n $ACTIVE_PGID ]]; then release_or_keep "script exit" || exit 131; fi
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
  log "removing a stale active-copy record (its process group is gone): $(cat "$STATE/active-copy")"
  rm -f "$STATE/active-copy"
}

pause_reason() { # pause_reason <missing since>: why the copy must be held now, or nothing
  if [[ -n $TEMP_MAX ]] && ((TEMP_MAX >= TEMP_PAUSE)); then
    printf 'SSD at %s °C (>= %s)' "$TEMP_MAX" "$TEMP_PAUSE"
    if ((TEMP_N < TEMP_SENSORS)); then printf '; only %s of %s sensors read' "$TEMP_N" "$TEMP_SENSORS"; fi
  elif ((TEMP_N < TEMP_SENSORS)) && [[ -n $1 ]] && ((SECONDS - $1 >= TEMP_MISSING)); then
    printf 'no reading from every SSD sensor for %ss (%s of %s read)' "$TEMP_MISSING" "$TEMP_N" "$TEMP_SENSORS"
  fi
  return 0
}
paused_state() { printf '%s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" > "$STATE/copy-paused"; }
guarded() { # guarded <command...>: its exit code; 124 on --timeout; 125 when the copy could not be stopped
  local pid rc=0 start=$SECONDS paused=0 missing_since="" last_poll=-1000000 why="" now_why
  no_active_copy >&2
  setsid "$@" &
  pid=$!
  ACTIVE_PGID=$pid
  printf '%s %s %s\n' "$pid" "$CMD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/active-copy"
  while kill -0 "$pid" 2> /dev/null; do
    if ((TIMEOUT > 0 && SECONDS - start >= TIMEOUT)); then
      release_or_keep "timeout after ${TIMEOUT}s" || return 125
      wait "$pid" 2> /dev/null || true   # the group is gone: this returns at once
      return 124
    fi
    if ((SECONDS - last_poll >= TEMP_POLL)); then
      last_poll=$SECONDS
      read_temps
      if ((TEMP_N >= TEMP_SENSORS)); then missing_since=""; elif [[ -z $missing_since ]]; then missing_since=$SECONDS; fi
      now_why=$(pause_reason "$missing_since")
      if ((paused == 0)) && [[ -n $now_why ]]; then
        kill -STOP -- "-$pid"; paused=1; why=$now_why
        log "copy paused: $why" >&2; paused_state "$pid" "$why"
      elif ((paused == 1)) && ((TEMP_N >= TEMP_SENSORS && TEMP_MAX <= TEMP_RESUME)); then
        kill -CONT -- "-$pid"; paused=0; why=""
        log "copy resumed: all $TEMP_N SSD sensors read, highest $TEMP_MAX °C (<= $TEMP_RESUME)" >&2; rm -f "$STATE/copy-paused"
      elif ((paused == 1)); then
        [[ -n $now_why ]] || now_why="waiting until all $TEMP_SENSORS sensors read <= $TEMP_RESUME °C ($TEMP_N read, highest ${TEMP_MAX:-none})"
        if [[ $now_why != "$why" ]]; then why=$now_why; log "still paused: $why" >&2; paused_state "$pid" "$why"; fi
      fi
    fi
    sleep 1
  done
  wait "$pid" || rc=$?
  ACTIVE_PGID=""; rm -f "$STATE/active-copy" "$STATE/copy-paused"
  return "$rc"
}
