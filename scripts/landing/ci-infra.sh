#!/usr/bin/env bash
# The entry point is from M0 in landing runs; all Python modules are exported
# again from M0 to a private directory before execution with -I.
set -euo pipefail
stage='' cand='' base_sha='' revision='' purpose=landing
args=("$@")
while (($#)); do
  case "$1" in
    --stage) stage="${2:?}" ;;
    --cand) cand="${2:?}" ;;
    --base-sha) base_sha="${2-}" ;;
    --revision) revision="${2:?}" ;;
    --purpose) purpose="${2:?}" ;;
    --base|--platform-revision|--generation|--results-dir) : ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  (($# >= 2)) || exit 2
  shift 2
done
if [[ "$stage" == tools ]]; then
  exec python3 -I "$(dirname "${BASH_SOURCE[0]}")/coverage_infra.py" "${args[@]}"
fi
[[ "$revision" =~ ^[0-9a-f]{40}$ && "$revision" != 0000000000000000000000000000000000000000 ]] || exit 2
[[ "$purpose" == landing || "$purpose" == push ]] || exit 2
if [[ "$purpose" == push && "$base_sha" == 0000000000000000000000000000000000000000 ]]; then base_sha=''; fi
source_sha="$base_sha"
if [[ -z "$source_sha" && "$purpose" == push ]]; then source_sha="$revision"; fi
[[ "$source_sha" =~ ^[0-9a-f]{40}$ && "$source_sha" != 0000000000000000000000000000000000000000 ]] || { echo 'base_missing' >&2; exit 2; }
[[ -n "$cand" ]] || exit 2
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
for name in doc_policy.py doc_consumers.py coverage_infra.py; do
  git -C "$cand/bifrost-trade-infra" show "$source_sha:scripts/landing/$name" > "$temp/$name"
done
python3 -I "$temp/coverage_infra.py" "${args[@]}"
