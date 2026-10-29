#!/usr/bin/env bash
# handin.sh — the coordinator hands one commit in to the agent runtime as an
# attempt of a task pinned to its Mac (W-31 round 4, core block C-2;
# agent-config/work/multi-agent/DESIGN-coordinator-landing-v3-2026-10-29.md
# §2.1, §2.5, §2.6, §12.3).
#
#   handin.sh propose --mission M-n --title T --repo R --base SHA [--key K] [--core]
#       Propose the pinned task as the proposer seat (seat:coordinator); its
#       spec is the platform's, the providers declared [anthropic]. Prints the
#       task id.
#   handin.sh squash --task t_… --base SHA --commit SHA [--commit SHA…] [--title T]
#       Make the explicitly selected isolated branch history one commit on BASE whose message lists the commits it replaces, with one
#       Agentrt-Task trailer and one Change-Id. Never amend it afterwards.
#   handin.sh run --task t_… --report FILE --remote REMOTE [--key K] [--commit SHA]
#       claim/pinned, upload the report, start, computed, push the commit to
#       the branch the platform gave, persist, submit; the lease is renewed
#       every 60 s until it ends. A step whose answer is lost is sent again as
#       it was (every step is idempotent); a lost claim answer comes back with
#       the same key. A lost lease needs a new key: run again with
#       --key <task>:<n+1>, which gets the next attempt and its own branch.
#       After cancellation, keep the key: a remote push may have completed;
#       run reads back the assigned ref before retrying the bound commit.
#   handin.sh status [--attempt a_…] [--task t_…] [--op land:…]
#   handin.sh refresh --task t_… --op land:…
#       Read the attempt/task/landing wait; refresh uses the execution identity.
#       Authorization material and approval subcommands belong to C-5.
#
# Credentials: environment or the current user's mode-600 coordinator token
# files under ~/.config/bifrost (HANDIN_AGENTD_TOKEN_FILE / HANDIN_PROPOSER_TOKEN_FILE).
#   PLATFORM_AGENTRT_URL                platform-api base (default: the PROD VIP NodePort)
#   HANDIN_HOST                         the external host (default: coordinator-mbp)
#   AGENTRT_COORDINATOR_AGENTD_TOKEN    the execution principal agentd:coordinator-mbp
#   AGENTRT_COORDINATOR_PROPOSER_TOKEN  the proposer seat seat:coordinator (propose only)
# Refuse tracing before the first credential expansion, including a separate
# trace descriptor. Never pass a bearer value in curl's process arguments.
case $- in *x*) set +x; echo 'handin: tracing is not supported' >&2; exit 1 ;; esac
set +x
[ -z "${BASH_XTRACEFD:-}" ] || { echo 'handin: tracing is not supported' >&2; exit 1; }
set -euo pipefail
umask 077

BASE_URL="${PLATFORM_AGENTRT_URL:-http://192.168.10.100:30876}"
BASE_URL="${BASE_URL%/}/api/v1/agentrt"
HOST="${HANDIN_HOST:-coordinator-mbp}"
BEAT_PID=""
CURL_PID=""
WAIT_PID=""
GIT_PID=""
RUN_LOCK=""
TMP=$(mktemp -d)
stop_git() {
  [ -n "$GIT_PID" ] || return 0
  # Job control gives this one Git command its own process group, including
  # transport and credential helpers. Keep its leader until the group is
  # signalled; never target handin's own process group.
  kill -TERM -- "-$GIT_PID" 2>/dev/null || true
  # A helper may ignore TERM. Bound shutdown, then reap our direct child.
  sleep 0.1
  kill -KILL -- "-$GIT_PID" 2>/dev/null || true
  wait "$GIT_PID" 2>/dev/null || true
  GIT_PID=""
}
cleanup() {
  trap '' INT TERM USR1
  stop_git
  for pid in "$CURL_PID" "$WAIT_PID"; do
    [ -z "$pid" ] || { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
  done
  if [ -n "$BEAT_PID" ]; then
    kill "$BEAT_PID" 2>/dev/null || true
    wait "$BEAT_PID" 2>/dev/null || true
    BEAT_PID=""
  fi
  [ -z "$RUN_LOCK" ] || rmdir "$RUN_LOCK" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'echo "handin: heartbeat refused or stop requested; read status before retrying" >&2; exit 1' USR1

die() { echo "handin: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "needs $1"; }
need curl
need jq
need git

# Background + wait lets Bash run its traps immediately during a blocked
# push/readback. Enable job control only for this child, not the heartbeat.
run_git() {
  local rc=0
  set -m
  git "$@" & GIT_PID=$!
  set +m
  wait "$GIT_PID" || rc=$?
  stop_git
  return "$rc"
}

# call runs in the current shell; both CODE and RESPONSE survive the call.
# Transport failures are retried with identical input. Ambiguous attempt writes
# are subsequently read back by cmd_run before any further stage is attempted.
CODE=""
RESPONSE=""
call() {
  local kind="$1" method="$2" path="$3" body="$4"
  shift 4
  local var=AGENTRT_COORDINATOR_AGENTD_TOKEN file token header out try
  file="${HANDIN_AGENTD_TOKEN_FILE:-$HOME/.config/bifrost/coordinator-agentd.token}"
  if [ "$kind" = proposer ]; then
    var=AGENTRT_COORDINATOR_PROPOSER_TOKEN
    file="${HANDIN_PROPOSER_TOKEN_FILE:-$HOME/.config/bifrost/coordinator-proposer.token}"
  fi
  token="${!var:-}"
  if [ -z "$token" ]; then
    [ -f "$file" ] && [ ! -L "$file" ] || die "set $var or supply its 600 token file"
    local mode owner
    if [ "$(uname -s)" = Darwin ]; then
      mode=$(stat -f %Lp "$file"); owner=$(stat -f %u "$file")
    else
      mode=$(stat -c %a "$file"); owner=$(stat -c %u "$file")
    fi
    [ "$mode" = 600 ] && [ "$owner" = "$(id -u)" ] || die "token file must be owned by this user with mode 600"
    token=$(cat "$file")
  fi
  [ -n "$token" ] && [[ "$token" != *$'\n'* && "$token" != *$'\r'* ]] || die 'invalid token'
  header=$(mktemp "$TMP/header.XXXXXX")
  out=$(mktemp "$TMP/body.XXXXXX")
  printf 'Authorization: Bearer %s\n' "$token" >"$header"
  unset token
  for try in 1 2 3; do
    local args=(-sS -o "$out" -w '%{http_code}' -X "$method" --max-time 40 -H "@$header")
    [ -n "$body" ] && args+=(-H 'Content-Type: application/json' --data-binary "$body")
    curl "${args[@]}" "$@" "$BASE_URL$path" >"$out.code" & CURL_PID=$!
    if wait "$CURL_PID"; then
      CURL_PID=""; CODE=$(cat "$out.code"); break
    fi
    CURL_PID=""; CODE=000
    if [ "$try" != 3 ]; then
      sleep "$((try * 3))" & WAIT_PID=$!
      wait "$WAIT_PID"; WAIT_PID=""
    fi
  done
  RESPONSE=$(cat "$out")
  rm -f "$out" "$out.code" "$header"
}
ok() { case "$CODE" in 2??) return 0 ;; *) return 1 ;; esac; }

# The heartbeat owns and reaps its sleep/call child, and the parent owns and
# reaps this process on every exit, including signals and normal completion.
heartbeat() {
  local child="" parent="$1" attempt="$2" fence="$3"
  trap 'for pid in "$child" "$CURL_PID" "$WAIT_PID"; do [ -z "$pid" ] || { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }; done; exit 0' TERM INT
  trap - EXIT USR1
  while true; do
    sleep 60 & child=$!
    wait "$child" || return
    child=""
    call agentd POST "/attempts/$attempt/heartbeat" "$fence"
    if ! ok || ! printf '%s' "$RESPONSE" | jq -e '.stop == false' >/dev/null; then
      kill -USR1 "$parent"
      return
    fi
  done
}

cmd_propose() {
  local mission="" title="" repo="" base="" key="" core=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --mission) mission="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      --repo) repo="$2"; shift 2 ;;
      --base) base="$2"; shift 2 ;;
      --key) key="$2"; shift 2 ;;
      --core) core=true; shift ;;
      *) die "propose: unknown $1" ;;
    esac
  done
  [ -n "$mission" ] && [ -n "$title" ] && [ -n "$repo" ] && [ -n "$base" ] || die "propose: --mission, --title, --repo and --base"
  [ -n "$key" ] || key="handin:$(printf '%s' "$mission $title $base" | shasum -a 256 | cut -c1-16)"
  local body out
  body=$(jq -n --arg key "$key" --arg title "$title" --arg repo "$repo" --arg base "$base" --argjson core "$core" '{
    idempotency_key: $key,
    tasks: [{ref: "handin", off_plan_reason: "handed in by the coordinator", role: "implement", task_class: "handin",
      title: $title, effect_class: "branch", repo: $repo, base_commit: $base, core: $core,
      executor_pin: "external:coordinator", providers: ["anthropic"]}]}')
  call proposer POST "/missions/$mission/tasks" "$body" -H "X-Bifrost-Session: ${BIFROST_SESSION:-}"
  out=$RESPONSE
  ok || die "propose: HTTP $CODE: $out"
  printf '%s\n' "$out" | jq -r '.tasks[0].task_id'
}

cmd_squash() {
  local task="" base="" title="" selected=() c branch head count msg dir original actual
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --base) base="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      --commit) selected+=("$2"); shift 2 ;;
      *) die "squash: unknown $1" ;;
    esac
  done
  [ -n "$task" ] && [ -n "$base" ] || die "squash: --task and --base"
  [[ "$task" =~ ^t_[0-9A-HJKMNP-TV-Z]{26}$ ]] || die "squash: invalid task id"
  branch=$(git symbolic-ref --quiet --short HEAD) || die 'squash: an isolated branch is required'
  case "$branch" in main|master|prod|stg|dev) die 'squash: shared branch is forbidden' ;; esac
  [ -z "$(git status --porcelain)" ] || die 'squash: the working tree must be clean'
  base=$(git rev-parse --verify "$base^{commit}")
  head=$(git rev-parse HEAD)
  git merge-base --is-ancestor "$base" "$head" || die 'squash: base is not an ancestor'
  count=$(git rev-list --count "$base..$head")
  [ "$count" -gt 0 ] || die 'squash: nothing to hand in'
  # Prepared identities never change, even when the original selection is
  # supplied again after a lost local command response.
  if [ "$count" = 1 ] && [ "$(git rev-list --parents -n1 "$head" | cut -d' ' -f2-)" = "$base" ] && valid_message "$head" "$task"; then
    printf '%s\n' "$head"; return
  fi
  [ "${#selected[@]}" -gt 0 ] || die 'squash: explicitly select this work unit with --commit SHA (repeat in oldest-first order)'
  actual=$(git rev-list --reverse "$base..$head")
  original=""
  for c in "${selected[@]}"; do
    c=$(git rev-parse --verify "$c^{commit}")
    [ "$(git rev-list --parents -n1 "$c" | awk '{print NF}')" = 2 ] || die 'squash: merge history is forbidden'
    local tags
    tags=$(git show -s --format=%B "$c" | sed -n 's/^Agentrt-Task:[[:space:]]*//p')
    [ -z "$tags" ] || [ "$tags" = "$task" ] || die 'squash: selected commit belongs to another task'
    original="${original}${original:+$'\n'}$c"
  done
  [ "$original" = "$actual" ] || die 'squash: selection must exactly match the isolated branch history; extra commits are forbidden'
  printf 'handin: selected commits:\n%s\n' "$actual" >&2
  git diff --stat "$base" "$head" >&2
  git diff --name-only "$base" "$head" >&2
  dir=$(git rev-parse --git-path "handin/squash/$task")
  mkdir -p "$dir"
  msg="$dir/message"
  if [ -f "$dir/source" ]; then
    [ "$(cat "$dir/source")" = "$base $head" ] || die "squash: recovery state differs: $dir"
  else
    printf '%s %s\n' "$base" "$head" >"$dir/source"
  fi
  if [ ! -f "$msg" ]; then
    [ -n "$title" ] || title=$(git log -1 --format=%s "${selected[0]}")
    case "$title" in *$'\n'*|*$'\r'*) die 'squash: title must be one line' ;; esac
    {
      printf '%s\n\nSelected work unit commits:\n' "$title"
      git log --reverse --format='- %h %s' "$base..$head"
      printf '\nAgentrt-Task: %s\nChange-Id: I%s\n' "$task" "$(openssl rand -hex 20)"
    } >"$msg"
  fi
  # Keep the original tip and message if creation fails. Only update the
  # isolated branch after the new object exists, using compare-and-swap.
  git update-ref "refs/handin/backups/$task" "$head"
  local result
  result=$(git commit-tree "$(git rev-parse "$head^{tree}")" -p "$base" -F "$msg") || die "squash: original tip preserved; retry using $msg"
  git update-ref "refs/heads/$branch" "$result" "$head" || die 'squash: branch moved concurrently; original tip is in refs/handin/backups'
  printf '%s\n' "$result"
}

valid_message() {
  local message
  message=$(git show -s --format=%B "$1")
  [ "$(printf '%s\n' "$message" | grep -ciE '^Agentrt-Task:')" = 1 ] &&
    printf '%s\n' "$message" | grep -qiE "^Agentrt-Task:[[:space:]]*$2[[:space:]]*\$" &&
    [ "$(printf '%s\n' "$message" | grep -ciE '^Change-Id:')" = 1 ] &&
    printf '%s\n' "$message" | grep -qiE '^Change-Id:[[:space:]]*I[0-9a-f]{40}[[:space:]]*$'
}

cmd_run() {
  local task="" report="" remote="" key="" commit=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --report) report="$2"; shift 2 ;;
      --remote) remote="$2"; shift 2 ;;
      --key) key="$2"; shift 2 ;;
      --commit) commit="$2"; shift 2 ;;
      *) die "run: unknown $1" ;;
    esac
  done
  [ -n "$task" ] && [ -f "$report" ] && [ -n "$remote" ] || die 'run: --task, --report FILE and --remote are required'
  [ -n "$key" ] || key="$task:1"
  local sum binding saved base parents attempt epoch ref fence doc state
  sum="sha256:$(shasum -a 256 "$report" | cut -d' ' -f1)"
  binding=$(printf '%s\n' "$BASE_URL" "$HOST" "$task" "$key" | shasum -a 256 | cut -d' ' -f1)
  saved=$(git rev-parse --git-path "handin/runs/$binding.json")
  mkdir -p "$(dirname "$saved")"
  mkdir "$saved.lock" 2>/dev/null || die 'run: another process holds this key (after a crash, check it has exited before removing its lock)'
  RUN_LOCK="$saved.lock"
  if [ -f "$saved" ]; then
    [ -z "$commit" ] || [ "$(git rev-parse "$commit^{commit}")" = "$(jq -r .commit "$saved")" ] || die 'run: key is bound to a different commit'
    commit=$(jq -r .commit "$saved")
    [ "$sum" = "$(jq -r .report "$saved")" ] || die 'run: key is bound to a different report'
  else
    commit=$(git rev-parse --verify "${commit:-HEAD}^{commit}")
    jq -n --arg c "$commit" --arg r "$sum" '{commit:$c,report:$r}' >"$saved.tmp"
    mv "$saved.tmp" "$saved"
  fi
  # Snapshot the report so the uploaded bytes stay bound to this invocation.
  cp "$report" "$TMP/report"
  [ "sha256:$(shasum -a 256 "$TMP/report" | cut -d' ' -f1)" = "$sum" ] || die 'run: report changed while reading'
  call agentd GET "/tasks/$task" ''
  ok || die "run: read task: HTTP $CODE"
  base=$(printf '%s' "$RESPONSE" | jq -r .base_commit)
  parents=$(git rev-list --parents -n1 "$commit" | cut -d' ' -f2-)
  [ "$parents" = "$base" ] || die 'run: commit must have the task base as its only parent'
  valid_message "$commit" "$task" || die 'run: commit needs one matching Agentrt-Task and one Change-Id'

  call agentd POST /claim/pinned "$(jq -n --arg h "$HOST" --arg t "$task" --arg k "$key" '{host_id:$h,task_id:$t,idempotency_key:$k,free_slots:1}')"
  ok || die "run: claim/pinned: HTTP $CODE; retry with the same key"
  attempt=$(printf '%s' "$RESPONSE" | jq -er .attempt_id)
  epoch=$(printf '%s' "$RESPONSE" | jq -er .lease_epoch)
  ref=$(printf '%s' "$RESPONSE" | jq -er .pushed_ref)
  fence=$(jq -n --arg h "$HOST" --argjson e "$epoch" '{host_id:$h,lease_epoch:$e}')
  read_attempt
  case "$state" in
    submitted|finished) verify_result; printf '%s\n' "$attempt"; return ;;
    leased|running|stale) ;;
    lost|failed|cancelled)
      call agentd GET "/tasks/$task" ''
      if ok && [ "$(printf '%s' "$RESPONSE" | jq -r .state)" = ready ]; then
        die "run: attempt is $state and task is ready; a new --key may claim the next attempt"
      fi
      die "run: attempt is $state; read task status before retrying"
      ;;
    *) die "run: unknown attempt state $state; read status before retrying" ;;
  esac
  heartbeat "$$" "$attempt" "$fence" & BEAT_PID=$!
  call agentd PUT "/artifacts/$sum" '' -H 'X-Artifact-Kind: report' -H 'Content-Type: text/markdown' --data-binary "@$TMP/report"
  ok || die "run: upload report: HTTP $CODE; retry with the same key"
  if ! has_stage started_at; then
    call agentd POST "/attempts/$attempt/start" "$(printf '%s' "$fence" | jq '.+{model_provider:"anthropic"}')"
    read_attempt
    has_stage started_at || die 'run: start not confirmed; retry with the same key'
  fi
  if ! has_stage computed_at; then
    call agentd POST "/attempts/$attempt/computed" "$(printf '%s' "$fence" | jq '.+{end_how:"exit",exit_code:0,conclusion:"done"}')"
    read_attempt
    has_stage computed_at || die 'run: computed not confirmed; retry with the same key'
  fi
  if ! has_stage persisted_at; then
    # Cancellation/lost push output cannot tell us whether the remote wrote
    # the ref. Read it before retrying, always using the locally bound SHA.
    local remote_head
    run_git ls-remote --refs "$remote" "$ref" >"$TMP/remote-ref" || die 'run: remote push outcome unknown; retry with the same key'
    remote_head=$(cat "$TMP/remote-ref")
    if [ -n "$remote_head" ]; then
      [ "$remote_head" = "$commit"$'\t'"$ref" ] || die 'run: remote ref differs from the bound commit; read status before retrying'
    else
      run_git push "$remote" "$commit:$ref" >&2 || die 'run: push outcome unknown; retry with the same key to read it back'
    fi
    call agentd POST "/attempts/$attempt/persist" "$(printf '%s' "$fence" | jq --arg r "$sum" --arg ref "$ref" --arg c "$commit" '.+{report:$r,pushed_ref:$ref,pushed_commit:$c}')"
    read_attempt
    has_stage persisted_at || die 'run: persist not confirmed; retry with the same key'
  fi
  verify_result
  if [ "$state" != submitted ] && [ "$state" != finished ]; then
    call agentd POST "/attempts/$attempt/submit" "$fence"
    read_attempt
  fi
  case "$state" in submitted|finished) verify_result ;; *) die 'run: submit not confirmed; retry with the same key' ;; esac
  kill "$BEAT_PID" 2>/dev/null || true
  wait "$BEAT_PID" 2>/dev/null || true
  BEAT_PID=""
  printf '%s\n' "$attempt"
}

# Helpers deliberately share cmd_run's dynamically scoped, immutable binding.
read_attempt() {
  call agentd GET "/attempts/$attempt" ''
  ok || die "run: read attempt: HTTP $CODE; retry with the same key"
  doc=$RESPONSE
  printf '%s' "$doc" | jq -e --arg t "$task" --arg h "$HOST" --argjson e "$epoch" '.task_id==$t and .host_id==$h and .lease_epoch==$e' >/dev/null || die 'run: attempt identity differs'
  state=$(printf '%s' "$doc" | jq -er .state)
}
has_stage() { printf '%s' "$doc" | jq -e --arg s "$1" '.[$s] != null' >/dev/null; }
verify_result() {
  printf '%s' "$doc" | jq -e --arg c "$commit" --arg r "$sum" --arg ref "$ref" '.persisted_at != null and .pushed_commit==$c and .pushed_ref==$ref and .report_artifact_id==$r' >/dev/null || die 'run: stored result differs from the bound commit/report/ref'
}

cmd_status() {
  local attempt="" task="" op=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --attempt) attempt="$2"; shift 2 ;;
      --task) task="$2"; shift 2 ;;
      --op) op="$2"; shift 2 ;;
      *) die "status: unknown $1" ;;
    esac
  done
  [ -n "$attempt$task$op" ] || die 'status: --attempt, --task or --op'
  local path
  for path in "${attempt:+/attempts/$attempt}" "${task:+/tasks/$task}" "${op:+/landing/operations/$op}"; do
    [ -n "$path" ] || continue
    call agentd GET "$path" ''
    ok || die "status: HTTP $CODE"
    printf '%s\n' "$RESPONSE" | jq .
  done
}
cmd_refresh() {
  local task="" op=""
  while [ $# -gt 0 ]; do
    case "$1" in --task) task="$2"; shift 2 ;; --op) op="$2"; shift 2 ;; *) die "refresh: unknown $1" ;; esac
  done
  [ -n "$task" ] && [ -n "$op" ] || die 'refresh: --task and --op'
  case "$op" in "land:$task:"[1-9]*) ;; *) die 'refresh: operation must belong to the task' ;; esac
  call agentd POST /landing/refresh "$(jq -n --arg t "$task" --arg o "$op" '{task:$t,op:$o}')"
  ok || die "refresh: HTTP $CODE"
  printf '%s\n' "$RESPONSE" | jq .
  cmd_status --task "$task" --op "$op"
}

case "${1:-}" in
  propose) shift; cmd_propose "$@" ;;
  squash) shift; cmd_squash "$@" ;;
  run) shift; cmd_run "$@" ;;
  status) shift; cmd_status "$@" ;;
  refresh) shift; cmd_refresh "$@" ;;
  *) sed -n '2,33p' "$0"; exit 2 ;;
esac
