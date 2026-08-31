#!/usr/bin/env bash
# Code-health ratchet — mechanical guards against structural rot.
#
# Companion to bifrost-trade-frontend/scripts/check-legacy-css.sh, which proved
# the pattern on frontend CSS. Same contract: a metric may never exceed its
# baseline, and a metric that drops below its baseline must have the baseline
# lowered so the ground it gained cannot be given back.
#
# Scans only git-tracked files (git ls-files), so gitignored vendor trees
# (node_modules, .venv*, dist) are excluded by construction rather than by an
# exclusion list that silently rots.
#
# Usage:
#   scan.sh                       human summary; exit 1 if any metric is over baseline
#   scan.sh --repo <a,b>          only scan the named repos (CI gates one repo)
#   scan.sh --json <path>         additionally write the machine-readable report
#   scan.sh --root <path>         workspace root holding the repos (CI: the Tekton
#                                 workspace, which has no walk-up markers)
#   scan.sh --report              POST the report to platform-api so the Console
#                                 can show it (needs PLATFORM_OPERATOR_TOKEN;
#                                 PLATFORM_API_URL defaults to 127.0.0.1:8780)
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: scan.sh [--repo <name[,name...]>] [--json <path>]
  --repo <names>  restrict scanning to these repos (default: all)
  --root <path>   workspace root holding the repos (default: detected upwards)
  --json <path>   write the machine-readable report to <path> ("-" for stdout)
  --report        POST the report to platform-api (PLATFORM_OPERATOR_TOKEN)
  --source <s>    label the reading "local" (default) or "ci"
USAGE
}

JSON_OUT=""
REPO_FILTER=""
ROOT_OVERRIDE=""
DO_REPORT=0
SOURCE="local"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) shift; [[ $# -gt 0 ]] || { usage; exit 2; }; REPO_FILTER="$1"; shift ;;
    --root) shift; [[ $# -gt 0 ]] || { usage; exit 2; }; ROOT_OVERRIDE="$1"; shift ;;
    --json) shift; [[ $# -gt 0 ]] || { usage; exit 2; }; JSON_OUT="$1"; shift ;;
    --report) DO_REPORT=1; shift ;;
    --source) shift; [[ $# -gt 0 ]] || { usage; exit 2; }; SOURCE="$1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "scan.sh: unknown argument '$1'" >&2; usage; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Walk up to the workspace root (the directory holding the bifrost-* repos).
# Resolved by content, not by relative depth, so invoking through the
# <workspace>/scripts symlink works the same as invoking the real path.
if [[ -n "$ROOT_OVERRIDE" ]]; then
  # CI checks out a subset of repos into a flat workspace, so the marker-dir
  # walk-up below has nothing to find. The caller states the root instead.
  [[ -d "$ROOT_OVERRIDE" ]] || { echo "code-health: --root '$ROOT_OVERRIDE' is not a directory" >&2; exit 2; }
  ROOT="$(cd "$ROOT_OVERRIDE" && pwd -P)"
else
  ROOT="$SCRIPT_DIR"
  while [[ "$ROOT" != "/" ]]; do
    if [[ -d "$ROOT/bifrost-trade-infra" && -d "$ROOT/bifrost-platform" ]]; then break; fi
    ROOT="$(dirname "$ROOT")"
  done
  if [[ "$ROOT" == "/" ]]; then
    echo "code-health: cannot locate workspace root (no dir with bifrost-trade-infra + bifrost-platform above $SCRIPT_DIR); pass --root" >&2
    exit 2
  fi
fi

KNOWN_REPOS="bifrost-platform bifrost-trade-frontend bifrost-research"
if [[ -n "$REPO_FILTER" ]]; then
  for r in $(printf '%s' "$REPO_FILTER" | tr ',' ' '); do
    printf '%s' " $KNOWN_REPOS " | grep -q " $r " || {
      echo "code-health: --repo '$r' is not a scanned repo (known: $KNOWN_REPOS)" >&2
      exit 2
    }
  done
fi

# shellcheck source=baselines.env
source "$SCRIPT_DIR/baselines.env"

fail=0
metrics_json=""
summary_lines=""

not_measured=""

# Should this repo be scanned? Honours --repo, and reports a selected-but-absent
# repo as NOT MEASURED rather than scanning nothing and calling it zero. A CI
# container that clones one repo must never publish "research: 0 duplicates".
want() {
  local repo="$1"
  if [[ -n "$REPO_FILTER" ]] && ! printf '%s' ",$REPO_FILTER," | grep -q ",$repo,"; then
    return 1
  fi
  if [[ ! -e "$ROOT/$repo/.git" ]]; then
    # One entry per repo, not one per metric that wanted it.
    printf '%s' " $not_measured " | grep -q " $repo " || not_measured+="$repo "
    return 1
  fi
  return 0
}

# List git-tracked files matching the given pathspecs, one per line.
# Fails loudly on whitespace in filenames rather than miscounting silently.
tracked() {
  local repo="$1"; shift
  [[ -d "$ROOT/$repo/.git" || -f "$ROOT/$repo/.git" ]] || return 0
  local out
  out="$(cd "$ROOT/$repo" && git ls-files "$@" 2>/dev/null || true)"
  if [[ -n "$out" ]] && printf '%s\n' "$out" | grep -q '[[:space:]]'; then
    echo "code-health: whitespace in a tracked filename under $repo — refusing to guess counts" >&2
    exit 2
  fi
  printf '%s' "$out"
}

# grep -h over a newline-separated list of repo-relative paths. Runs inside the
# repo so the paths resolve. An empty list yields no output (a bare xargs would
# run grep with no operands and block reading stdin).
grep_files() {
  local repo="$1" files="$2" pattern="$3"
  [[ -n "$files" ]] || return 0
  ( cd "$ROOT/$repo" && printf '%s\n' "$files" | tr '\n' '\0' \
    | xargs -0 grep -hoE "$pattern" 2>/dev/null ) || true
}

json_escape() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

# add_metric <id> <label> <domain> <repo> <value> <baseline_var> <detail> [offenders]
#
# On failure the full offender list goes to stderr. The summary line alone tells
# you the count went up but not which item you just added, and a check that
# cannot point at the offending line is one people learn to mute.
add_metric() {
  local id="$1" label="$2" domain="$3" repo="$4" value="$5" baseline_var="$6" detail="$7"
  local offenders="${8:-}"
  local baseline="${!baseline_var}"
  local status mark
  if [[ "$value" -gt "$baseline" ]]; then
    status="over"; mark="OVER "
    fail=1
    if [[ -n "$offenders" ]]; then
      echo "--- $repo: $label ---" >&2
      printf '%s\n' "$offenders" >&2
    fi
    echo "code-health: $label increased ($value > baseline $baseline) in $repo — $detail" >&2
  elif [[ "$value" -lt "$baseline" ]]; then
    status="improved"; mark="BETTER"
    echo "code-health: $label is $value < baseline $baseline — lower $baseline_var in scripts/code-health/baselines.env" >&2
  else
    status="at_baseline"; mark="  ok  "
  fi
  summary_lines+="  [$mark] $(printf '%-34s' "$label") $(printf '%4s' "$value") / $baseline  ($repo)"$'\n'
  [[ -n "$metrics_json" ]] && metrics_json+=","
  metrics_json+=$'\n    {'
  metrics_json+="\"id\":\"$(json_escape "$id")\","
  metrics_json+="\"label\":\"$(json_escape "$label")\","
  metrics_json+="\"domain\":\"$(json_escape "$domain")\","
  metrics_json+="\"repo\":\"$(json_escape "$repo")\","
  metrics_json+="\"value\":$value,\"baseline\":$baseline,"
  metrics_json+="\"baseline_var\":\"$(json_escape "$baseline_var")\","
  metrics_json+="\"status\":\"$status\","
  metrics_json+="\"detail\":\"$(json_escape "$detail")\"}"
}


# ---------------------------------------------------------------- metric 1
# Duplicated function names. Counts distinct names defined more than three
# times, i.e. duplicated *concepts*. Tests are excluded (fakes legitimately
# re-implement cursor/commit/execute) and so are dunders (__init__ per class
# is not duplication).
dup_table() { sort | uniq -c | sort -rn | awk '$1>3' || true; }
dup_detail() { head -3 | awk '{printf "%s(%s) ", $2, $1}' || true; }

if want bifrost-trade-frontend; then
fe_files="$(tracked bifrost-trade-frontend 'src/*.ts' 'src/*.tsx' | grep -vE '\.(test|spec)\.tsx?$' || true)"
fe_dup="$(grep_files bifrost-trade-frontend "$fe_files" '^[[:space:]]*(export )?(async )?function [a-zA-Z_][a-zA-Z0-9_]*' \
  | sed -E 's/.*function //' | dup_table)"
fe_dup_n=$(printf '%s' "$fe_dup" | grep -c . || true)
add_metric code.duplication.satellite "duplicated function names" satellite bifrost-trade-frontend \
  "$fe_dup_n" DUP_FUNCS_FRONTEND_BASELINE \
  "top: $(printf '%s\n' "$fe_dup" | dup_detail)" "$fe_dup"
fi

if want bifrost-research; then
rs_files="$(tracked bifrost-research '*.py' | grep -vE '^tests/' || true)"
rs_dup="$(grep_files bifrost-research "$rs_files" '^[[:space:]]*(async )?def [a-zA-Z_][a-zA-Z0-9_]*' \
  | sed -E 's/.*def //' | grep -vE '^__.*__$' | dup_table)"
rs_dup_n=$(printf '%s' "$rs_dup" | grep -c . || true)
add_metric code.duplication.research "duplicated function names" research bifrost-research \
  "$rs_dup_n" DUP_FUNCS_RESEARCH_BASELINE \
  "top: $(printf '%s\n' "$rs_dup" | dup_detail)" "$rs_dup"
fi

# ---------------------------------------------------------------- metric 2
# Files over 800 lines. A file nobody can hold in their head is where the next
# duplicate gets written, because finding the existing helper costs more than
# retyping it.
oversized() {
  local repo="$1" files
  files="$(tracked "$repo" '*.ts' '*.tsx' '*.py' '*.go')"
  [[ -n "$files" ]] || { echo ""; return 0; }
  ( cd "$ROOT/$repo" && printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 wc -l 2>/dev/null ) \
    | awk '$2!="total" && $1>800 {print $1" "$2}' | sort -rn || true
}
for spec in "bifrost-platform rocket OVERSIZED_PLATFORM_BASELINE code.oversized.rocket" \
            "bifrost-trade-frontend satellite OVERSIZED_FRONTEND_BASELINE code.oversized.satellite" \
            "bifrost-research research OVERSIZED_RESEARCH_BASELINE code.oversized.research"; do
  read -r repo domain var id <<<"$spec"
  want "$repo" || continue
  big="$(oversized "$repo")"
  n=$(printf '%s' "$big" | grep -c . || true)
  add_metric "$id" "files over 800 lines" "$domain" "$repo" "$n" "$var" \
    "largest: $(printf '%s\n' "$big" | head -2 | awk '{printf "%s(%s) ", $2, $1}')" "$big"
done

# ---------------------------------------------------------------- metric 3
# API modules with no runtime contract validation. Research and Satellite ship
# on independent delivery chains, so an unvalidated module is an endpoint whose
# backend can drift with nothing to notice.
if want bifrost-trade-frontend; then
api_all="$(tracked bifrost-trade-frontend 'src/api/*.ts' | grep -vE '\.(test|spec)\.ts$' || true)"
api_total=$(printf '%s' "$api_all" | grep -c . || true)
api_validated=0
api_unvalidated=""
if [[ -n "$api_all" ]]; then
  validated_list=$( (cd "$ROOT/bifrost-trade-frontend" && printf '%s\n' "$api_all" | tr '\n' '\0' \
    | xargs -0 grep -lE 'apiValidation|lib/schemas' 2>/dev/null || true) | sort)
  api_validated=$(printf '%s' "$validated_list" | grep -c . || true)
  api_unvalidated=$(comm -23 <(printf '%s\n' "$api_all" | sort) <(printf '%s\n' "$validated_list") || true)
fi
add_metric code.contract-coverage.satellite "API modules without schema" satellite bifrost-trade-frontend \
  "$(( api_total - api_validated ))" UNVALIDATED_API_BASELINE \
  "$api_validated/$api_total modules validated" "$api_unvalidated"
fi

# ---------------------------------------------------------------- metric 4
# Distinct research image tags pinned across k8s. Each extra tier is a
# component running code that no release actually tracked.
if want bifrost-research; then
rs_k8s="$(tracked bifrost-research 'k8s/*')"
tiers="$(grep_files bifrost-research "$rs_k8s" 'image:[[:space:]]*[^ ]*bifrost-research[^ ]*' \
  | sed -E 's/.*://' | sort -u)"
tiers_n=$(printf '%s' "$tiers" | grep -c . || true)
add_metric code.image-version-spread.research "distinct research image tags" research bifrost-research \
  "$tiers_n" RESEARCH_IMAGE_TIERS_BASELINE \
  "tags: $(printf '%s' "$tiers" | tr '\n' ' ')" "$tiers"
fi

# ---------------------------------------------------------------- report
# HEAD of the governance repo is the freshness anchor: a stored reading whose
# commit is behind the current HEAD is stale, and the UI must say so rather
# than present it as current.
commit="$(cd "$ROOT/bifrost-trade-infra" 2>/dev/null && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# With `--json -` stdout is the machine channel, so the human summary moves to
# stderr; a caller piping the report into a parser must not have to strip it.
if [[ "$JSON_OUT" == "-" ]]; then exec 3>&2; else exec 3>&1; fi
echo >&3
echo "code-health @ $commit" >&3
printf '%s' "$summary_lines" >&3
if [[ -n "$not_measured" ]]; then
  echo "  [NOT MEASURED] repo absent: $not_measured" >&3
fi
echo >&3

if [[ -n "$JSON_OUT" || "$DO_REPORT" -eq 1 ]]; then
  json="{
  \"generated_at\": \"$generated_at\",
  \"source\": \"$(json_escape "$SOURCE")\",
  \"commit\": \"$commit\",
  \"not_measured\": \"$(json_escape "$not_measured")\",
  \"metrics\": [$metrics_json
  ]
}"
  if [[ "$JSON_OUT" == "-" ]]; then
    printf '%s\n' "$json"
  elif [[ -n "$JSON_OUT" ]]; then
    printf '%s\n' "$json" > "$JSON_OUT"
  fi
fi

if [[ "$DO_REPORT" -eq 1 ]]; then
  api="${PLATFORM_API_URL:-http://127.0.0.1:8780}"
  if [[ -z "${PLATFORM_OPERATOR_TOKEN:-}" ]]; then
    echo "code-health: --report needs PLATFORM_OPERATOR_TOKEN" >&2
    exit 2
  fi
  # A failed upload must be loud. A silently dropped report leaves the Console
  # showing an older reading as if it were current.
  http_code="$(printf '%s' "$json" | curl -sS -o /tmp/code-health-report.out -w '%{http_code}' \
    -X POST "$api/api/v1/code-health/report" \
    -H "Authorization: Bearer $PLATFORM_OPERATOR_TOKEN" \
    -H 'Content-Type: application/json' --data-binary @- || echo 000)"
  if [[ "$http_code" != "200" ]]; then
    echo "code-health: report upload failed (HTTP $http_code): $(cat /tmp/code-health-report.out 2>/dev/null)" >&2
    exit 1
  fi
  echo "code-health: reported to $api ($(cat /tmp/code-health-report.out))" >&3
fi

if [[ -z "$metrics_json" ]]; then
  echo "code-health: no metric was produced — treating as failure, not as a pass" >&2
  exit 2
fi

if [[ "$fail" -ne 0 ]]; then
  echo "code-health: FAILED — a metric exceeded its baseline (see above)" >&2
  exit 1
fi

echo "code-health: OK" >&3
