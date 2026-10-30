#!/usr/bin/env bash
# S6-7 GET-only probe. Owner credential checks rules; the prompted existing
# reader/lander token checks its own permissions. Never creates probe refs/PRs.
case $- in *x*) { set +x; } 2>/dev/null; echo 'FAIL: xtrace is not allowed' >&2; exit 2 ;; esac
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
[[ $# == 3 && "$1" == --owner ]] || { echo 'usage: probe-infra-access.sh --owner <login> stg|prod|ci|lander' >&2; exit 2; }
case "$3" in stg|prod|ci|lander) ;; *) echo 'FAIL: unsupported identity' >&2; exit 2 ;; esac
failed=0
bash "$HERE/protect-repo.sh" --check --owner "$2" bifrost-trade-infra || failed=1
bash "$HERE/put-reader-token.sh" "$3" --check || failed=1
if [[ "$failed" == 0 ]]; then
  echo "VERDICT PASS S6-7 infra $3: branch rules and identity access verified (GET only)"
else
  echo "VERDICT FAIL S6-7 infra $3: protection or identity check failed; do not open landing"
fi
exit "$failed"
