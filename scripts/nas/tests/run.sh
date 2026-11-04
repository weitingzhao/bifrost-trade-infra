#!/usr/bin/env bash
# Run the NAS script tests (TD-444 step 5) in debian:12; nothing touches the host.
#   bash scripts/nas/tests/run.sh [test_move.sh|test_move_ugos.sh|test_minio.sh|test_rollup.sh|test_rollup_ugos.sh|test_rollup_minio.sh|test_harness.sh]...
# Each test file runs in its own container, with scripts/nas mounted read-only at /src. A file
# that has not finished after TEST_TIMEOUT seconds (default 1800) is stopped and counts as
# failed (the host may lack GNU timeout, so the container is watched and killed by name).
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
files=("$@")
((${#files[@]})) || files=(test_move.sh test_move_ugos.sh test_minio.sh test_rollup.sh test_rollup_ugos.sh test_rollup_minio.sh test_harness.sh)
limit=${TEST_TIMEOUT:-1800}
[[ $limit =~ ^[1-9][0-9]*$ ]] || { echo "TEST_TIMEOUT must be a number of seconds" >&2; exit 2; }
rc=0
for t in "${files[@]}"; do
  echo "== $t"
  name="td444-test-$$-${t%.sh}"
  docker run --rm --name "$name" -e SRC=/src -v "$here:/src:ro" debian:12 bash "/src/tests/$t" &
  pid=$! start=$SECONDS r=0
  while kill -0 "$pid" 2> /dev/null; do
    if ((SECONDS - start >= limit)); then
      echo "== $t: no result after ${limit}s; stopped"
      docker kill "$name" > /dev/null 2>&1 || true
      r=124
      break
    fi
    sleep 2
  done
  w=0; wait "$pid" || w=$?
  if ((r == 0)); then r=$w; fi
  if ((r != 0)); then rc=1; fi
done
exit "$rc"
