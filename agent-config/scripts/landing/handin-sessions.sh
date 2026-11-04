# shellcheck shell=bash
# handin-sessions.sh — sourced by handin.sh (R5:5.5-12 §5, S1-5): at hand-in,
# say for each Claude session that wrote the work whether it was registered.
#
# Only in collector mode (PLATFORM_COLLECTOR_TOKEN, else the first line of
# ~/.config/bifrost/collector.token). Without a collector token nothing here
# runs: no request, no file, no output.
#
# squash reads the first Claude-Session trailer of every commit in BASE..HEAD
# (the sidebar id, or the CLI id without a desktop), de-duplicated, and asks
# GET /api/v1/agent/threads?sidebar=<v>, then ?session=<v> when nothing
# matched (the collector reads its own host only, never titles). Per value:
#   any row linked                        → registered
#   no linked, any unsupported or unknown → uncertain
#   rows, all unlinked or refused         → unregistered
#   no row, a failed read                 → unknown
# A commit without the trailer is unknown: that includes every commit squash
# itself wrote, so re-squashing squashed work says unknown. One stderr line
# per value; the result is kept as sessions.json in the squash state
# directory. run says the same lines again from it and writes them to
# unregistered_sessions.json beside its own state. Neither ever refuses a
# hand-in (refusing is S4), and nothing is written to the platform.

SESSIONS_RE='^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
SESSIONS_URL="${BASE_URL%/agentrt}/agent/threads"

sessions_token() {
  local t="${PLATFORM_COLLECTOR_TOKEN:-}" file="${BIFROST_HOME_OVERRIDE:-$HOME}/.config/bifrost/collector.token"
  t=$(printf '%s' "$t" | tr -d '[:space:]')
  if [ -z "$t" ] && [ -f "$file" ] && [ -r "$file" ]; then
    t=$(head -n 1 "$file" | tr -d '[:space:]')
  fi
  printf '%s' "$t"
}

# The binding state of every row that matches, one per line; exit 1 on a failed read.
sessions_get() {
  local field="$1" value="$2" header out code
  header=$(mktemp "$TMP/sessions-header.XXXXXX")
  out=$(mktemp "$TMP/sessions-body.XXXXXX")
  printf 'Authorization: Bearer %s\n' "$(sessions_token)" >"$header"
  code=$(curl -sS -o "$out" -w '%{http_code}' -X GET --max-time 10 -H "@$header" "$SESSIONS_URL?$field=$value" 2>/dev/null) || code=000
  rm -f "$header"
  case "$code" in 2??) ;; *) rm -f "$out"; return 1 ;; esac
  jq -r 'if (.threads | type) == "array" then .threads[] | (.binding.state // "unknown") else error("no threads") end' "$out" 2>/dev/null || { rm -f "$out"; return 1; }
  rm -f "$out"
}

sessions_conclude() {
  local value="$1" states
  [[ "$value" =~ $SESSIONS_RE ]] || { echo unknown; return; }
  states=$(sessions_get sidebar "$value") || { echo unknown; return; }
  if [ -z "$states" ]; then
    states=$(sessions_get session "$value") || { echo unknown; return; }
  fi
  if [ -z "$states" ]; then echo unknown
  elif grep -qx linked <<<"$states"; then echo registered
  elif ! grep -qvxE 'unlinked|refused' <<<"$states"; then echo unregistered
  else echo uncertain
  fi
}

# squash: BASE HEAD STATE_DIR RESULT
sessions_check() {
  [ -n "$(sessions_token)" ] || return 0
  local base="$1" head="$2" dir="$3" result="$4" c value word values="" bare="[]" found="[]"
  # squash run again for the same result (an idempotent retry) says what it said, not unknown.
  if [ -f "$dir/sessions.json" ] && [ "$(jq -r .commit "$dir/sessions.json" 2>/dev/null)" = "$result" ]; then
    sessions_say "$(cat "$dir/sessions.json")"
    return 0
  fi
  while read -r c; do
    [ -n "$c" ] || continue
    value=$(git show -s --format='%(trailers:key=Claude-Session,valueonly,separator=%x0A)' "$c" | sed -n 1p | tr -d '[:space:]')
    if [ -z "$value" ]; then
      printf 'handin: commit %s: unknown (no Claude-Session trailer)\n' "${c:0:9}" >&2
      bare=$(jq -c --arg c "$c" '. + [$c]' <<<"$bare")
    elif ! grep -qxF -- "$value" <<<"$values"; then
      values="${values}${values:+$'\n'}$value"
    fi
  done < <(git rev-list --reverse "$base..$head")
  while read -r value; do
    [ -n "$value" ] || continue
    word=$(sessions_conclude "$value")
    printf 'handin: session %s: %s\n' "$value" "$word" >&2
    found=$(jq -c --arg s "$value" --arg w "$word" '. + [{session:$s,conclusion:$w}]' <<<"$found")
  done <<<"$values"
  mkdir -p "$dir"
  jq -n --arg c "$result" --arg r "$base..$head" --argjson s "$found" --argjson b "$bare" \
    '{commit:$c,range:$r,sessions:$s,commits_without_trailer:$b}' >"$dir/sessions.json.tmp"
  mv "$dir/sessions.json.tmp" "$dir/sessions.json"
}

sessions_say() {
  jq -r '.commits_without_trailer[] | "handin: commit \(.[0:9]): unknown (no Claude-Session trailer)"' <<<"$1" >&2
  jq -r '.sessions[] | "handin: session \(.session): \(.conclusion)"' <<<"$1" >&2
}

# run: TASK COMMIT OUT — replay the squash result for this commit; unknown without one.
sessions_replay() {
  [ -n "$(sessions_token)" ] || return 0
  local task="$1" commit="$2" out="$3" root f doc=""
  root=$(git rev-parse --git-path "handin/squash/$task")
  for f in "$root/sessions.json" "$root"/attempts/*/sessions.json; do
    [ -f "$f" ] && [ "$(jq -r .commit "$f" 2>/dev/null)" = "$commit" ] && { doc=$(cat "$f"); break; }
  done
  if [ -z "$doc" ]; then
    printf 'handin: sessions: unknown (no squash record for %s)\n' "${commit:0:9}" >&2
    doc=$(jq -n --arg c "$commit" '{commit:$c,sessions:[],commits_without_trailer:[],unknown:"no squash record"}')
  else
    sessions_say "$doc"
  fi
  printf '%s\n' "$doc" >"$out.tmp"
  mv "$out.tmp" "$out"
}
