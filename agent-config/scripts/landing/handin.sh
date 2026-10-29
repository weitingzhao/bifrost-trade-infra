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
#   handin.sh squash --task t_… --base SHA [--title T]
#       Make the work since BASE one commit on BASE (git reset --soft BASE and
#       one commit) whose message lists the commits it replaces, with one
#       Agentrt-Task trailer and one Change-Id. Never amend it afterwards.
#   handin.sh run --task t_… --report FILE --remote REMOTE [--key K] [--commit SHA]
#       claim/pinned, upload the report, start, computed, push the commit to
#       the branch the platform gave, persist, submit; the lease is renewed
#       every 60 s until it ends. A step whose answer is lost is sent again as
#       it was (every step is idempotent); a lost claim answer comes back with
#       the same key. A lost lease needs a new key: run again with
#       --key <task>:<n+1>, which gets the next attempt and its own branch.
#   handin.sh status --attempt a_…
#       Read the attempt back.
#
# Environment (the tokens come only from it; this script reads no token file
# and prints no token):
#   PLATFORM_AGENTRT_URL                platform-api base (default: the PROD VIP NodePort)
#   HANDIN_HOST                         the external host (default: coordinator-mbp)
#   AGENTRT_COORDINATOR_AGENTD_TOKEN    the execution principal agentd:coordinator-mbp
#   AGENTRT_COORDINATOR_PROPOSER_TOKEN  the proposer seat seat:coordinator (propose only)
set -euo pipefail

BASE_URL="${PLATFORM_AGENTRT_URL:-http://192.168.10.100:30876}"
BASE_URL="${BASE_URL%/}/api/v1/agentrt"
HOST="${HANDIN_HOST:-coordinator-mbp}"

die() { echo "handin: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "needs $1"; }
need curl
need jq
need git

# call <proposer|agentd> <method> <path> <json body or ""> [extra curl args…]:
# prints the answer's body; its status goes to CODE. A request that does not
# reach the platform is sent again as it was, three times at most.
CODE=""
call() {
  local kind="$1" method="$2" path="$3" body="$4"
  shift 4
  local var=AGENTRT_COORDINATOR_AGENTD_TOKEN
  [ "$kind" = proposer ] && var=AGENTRT_COORDINATOR_PROPOSER_TOKEN
  [ -n "${!var:-}" ] || die "set $var"
  local out try
  out=$(mktemp)
  for try in 1 2 3; do
    local args=(-sS -o "$out" -w '%{http_code}' -X "$method" --max-time 40 -H "Authorization: Bearer ${!var}")
    [ -n "$body" ] && args+=(-H 'Content-Type: application/json' --data-binary "$body")
    if CODE=$(curl "${args[@]}" "$@" "$BASE_URL$path"); then break; fi
    CODE=000
    sleep $((try * 3))
  done
  cat "$out"
  rm -f "$out"
}

ok() { case "$CODE" in 2??) return 0 ;; *) return 1 ;; esac; }

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
  out=$(call proposer POST "/missions/$mission/tasks" "$body" -H "X-Bifrost-Session: ${BIFROST_SESSION:-}")
  ok || die "propose: HTTP $CODE: $out"
  printf '%s\n' "$out" | jq -r '.tasks[0].task_id'
}

cmd_squash() {
  local task="" base="" title=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --task) task="$2"; shift 2 ;;
      --base) base="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      *) die "squash: unknown $1" ;;
    esac
  done
  [ -n "$task" ] && [ -n "$base" ] || die "squash: --task and --base"
  [[ "$task" =~ ^t_[0-9A-HJKMNP-TV-Z]{26}$ ]] || die "squash: $task is not a task id"
  git diff --quiet && git diff --cached --quiet || die "squash: the working tree has uncommitted changes"
  git merge-base --is-ancestor "$base" HEAD || die "squash: $base is not an ancestor of HEAD"
  local n titles msg
  n=$(git rev-list --count "$base..HEAD")
  [ "$n" -gt 0 ] || die "squash: nothing since $base"
  titles=$(git log --reverse --format='- %s' "$base..HEAD")
  [ -n "$title" ] || title=$(git log -1 --format=%s "$(git rev-list --reverse "$base..HEAD" | head -n1)")
  msg=$(mktemp)
  {
    printf '%s\n\n' "$title"
    printf 'The %s commits since %s, handed in as one (DESIGN-coordinator-landing-v3 §12.3):\n\n%s\n\n' "$n" "${base:0:12}" "$titles"
    printf 'Agentrt-Task: %s\n' "$task"
    printf 'Change-Id: I%s\n' "$(openssl rand -hex 20)"
  } >"$msg"
  git reset --soft "$base"
  git commit -F "$msg" >/dev/null
  rm -f "$msg"
  git rev-parse HEAD
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
  [ -n "$task" ] && [ -n "$report" ] && [ -n "$remote" ] || die "run: --task, --report and --remote"
  [ -f "$report" ] || die "run: no report $report"
  [ -n "$key" ] || key="$task:1"
  [ -n "$commit" ] || commit=$(git rev-parse HEAD)

  # The commit, checked here as the platform will check it: one parent, the
  # task's base; one Agentrt-Task naming the task; one Change-Id.
  local taskdoc base parents message
  taskdoc=$(call agentd GET "/tasks/$task" "")
  ok || die "run: read task: HTTP $CODE: $taskdoc"
  base=$(printf '%s' "$taskdoc" | jq -r '.base_commit')
  parents=$(git rev-list --parents -n1 "$commit" | cut -d' ' -f2-)
  [ "$parents" = "$base" ] || die "run: $commit is not one commit on the task's base $base (parents: $parents)"
  message=$(git show -s --format=%B "$commit")
  [ "$(printf '%s\n' "$message" | grep -ciE '^Agentrt-Task:')" = 1 ] &&
    printf '%s\n' "$message" | grep -qiE "^Agentrt-Task:[[:space:]]*$task[[:space:]]*\$" ||
    die "run: $commit needs exactly one Agentrt-Task: $task"
  [ "$(printf '%s\n' "$message" | grep -ciE '^Change-Id:')" = 1 ] &&
    printf '%s\n' "$message" | grep -qiE '^Change-Id:[[:space:]]*I[0-9a-f]{40}[[:space:]]*$' ||
    die "run: $commit needs exactly one Change-Id"

  # 1. The claim; its answer, if lost, comes back with the same key.
  local claim attempt epoch ref state
  claim=$(call agentd POST /claim/pinned "$(jq -n --arg h "$HOST" --arg t "$task" --arg k "$key" \
    '{host_id: $h, task_id: $t, idempotency_key: $k, free_slots: 1}')")
  ok || die "run: claim/pinned: HTTP $CODE: $claim"
  attempt=$(printf '%s' "$claim" | jq -r '.attempt_id')
  epoch=$(printf '%s' "$claim" | jq -r '.lease_epoch')
  ref=$(printf '%s' "$claim" | jq -r '.pushed_ref')
  echo "handin: attempt $attempt (key $key), branch $ref" >&2
  state=$(call agentd GET "/attempts/$attempt" "" | jq -r '.state // empty')
  case "$state" in
    leased | running | stale) ;;
    *) die "run: attempt $attempt is $state; run again with a new --key ($task:<n+1>)" ;;
  esac

  # The lease, renewed every 60 s until this ends.
  local fence beat
  fence=$(jq -n --arg h "$HOST" --argjson e "$epoch" '{host_id: $h, lease_epoch: $e}')
  (
    while sleep 60; do
      call agentd POST "/attempts/$attempt/heartbeat" "$fence" >/dev/null || true
    done
  ) &
  beat=$!
  trap 'kill "$beat" 2>/dev/null || true' EXIT

  # 2. The report, then start and computed.
  local sum out
  sum="sha256:$(shasum -a 256 "$report" | cut -d' ' -f1)"
  out=$(call agentd PUT "/artifacts/$sum" "" -H 'X-Artifact-Kind: report' -H 'Content-Type: text/markdown' --data-binary "@$report")
  ok || die "run: upload report: HTTP $CODE: $out"
  out=$(call agentd POST "/attempts/$attempt/start" "$(printf '%s' "$fence" | jq '. + {model_provider: "anthropic"}')")
  ok || die "run: start: HTTP $CODE: $out"
  out=$(call agentd POST "/attempts/$attempt/computed" "$(printf '%s' "$fence" | jq '. + {end_how: "exit", exit_code: 0, conclusion: "done"}')")
  ok || die "run: computed: HTTP $CODE: $out"

  # 3. The commit, to the branch the platform gave; never another.
  git push "$remote" "$commit:$ref" >&2 || die "run: push to $ref failed; run again with the same --key, which reads the attempt back"

  # 4. persist, then submit.
  out=$(call agentd POST "/attempts/$attempt/persist" "$(printf '%s' "$fence" | jq --arg r "$sum" --arg ref "$ref" --arg c "$commit" \
    '. + {report: $r, pushed_ref: $ref, pushed_commit: $c}')")
  ok || die "run: persist: HTTP $CODE: $out"
  out=$(call agentd POST "/attempts/$attempt/submit" "$fence")
  ok || die "run: submit: HTTP $CODE: $out"
  echo "handin: submitted $attempt ($commit on $ref)" >&2
  printf '%s\n' "$attempt"
}

cmd_status() {
  local attempt="" out
  while [ $# -gt 0 ]; do
    case "$1" in
      --attempt) attempt="$2"; shift 2 ;;
      *) die "status: unknown $1" ;;
    esac
  done
  [ -n "$attempt" ] || die "status: --attempt"
  out=$(call agentd GET "/attempts/$attempt" "")
  ok || die "status: HTTP $CODE: $out"
  printf '%s\n' "$out" | jq .
}

case "${1:-}" in
  propose) shift; cmd_propose "$@" ;;
  squash) shift; cmd_squash "$@" ;;
  run) shift; cmd_run "$@" ;;
  status) shift; cmd_status "$@" ;;
  *) sed -n '2,31p' "$0"; exit 2 ;;
esac
