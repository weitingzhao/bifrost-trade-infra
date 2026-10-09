#!/usr/bin/env bash
# Owner-env helper. Fake values only. Output must not contain them.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SECRET="sekrit-foo-value"
printf 'FOO=%s\n' "$SECRET" >"$TMP/owner.env"
export BIFROST_OWNER_ENV="$TMP/owner.env"
unset FOO
# shellcheck source=owner-env.sh
source "$ROOT/owner-env.sh"
owner_fill FOO >"$TMP/stdout" 2>"$TMP/stderr"
if [ "$FOO" != "$SECRET" ]; then
  echo "FAIL owner_fill did not set the key" >&2
  exit 1
fi
if grep -q "$SECRET" "$TMP/stdout" "$TMP/stderr"; then
  echo "FAIL owner_fill printed a value" >&2
  exit 1
fi
export FOO="kept"
printf 'FOO=other-value\n' >"$TMP/owner.env"
owner_fill FOO >/dev/null
if [ "$FOO" != "kept" ]; then
  echo "FAIL owner_fill overwrote an existing variable" >&2
  exit 1
fi
echo "ok: owner_fill prefers the environment and does not print values"
