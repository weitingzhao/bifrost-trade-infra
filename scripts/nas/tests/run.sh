#!/usr/bin/env bash
# Run the NAS script tests (TD-444 step 5) in debian:12; nothing touches the host.
#   bash scripts/nas/tests/run.sh [test_move.sh|test_move_ugos.sh|test_minio.sh|test_rollup.sh|test_rollup_minio.sh]...
# Each test file runs in its own container, with scripts/nas mounted read-only at /src.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
files=("$@")
((${#files[@]})) || files=(test_move.sh test_move_ugos.sh test_minio.sh test_rollup.sh test_rollup_minio.sh)
rc=0
for t in "${files[@]}"; do
  echo "== $t"
  docker run --rm -e SRC=/src -v "$here:/src:ro" debian:12 bash "/src/tests/$t" || rc=1
done
exit "$rc"
