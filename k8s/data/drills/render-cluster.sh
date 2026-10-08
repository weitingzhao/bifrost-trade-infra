#!/bin/bash
# Print the PITR drill manifest with targetTime set.
# Usage: render-cluster.sh [YYYY-MM-DDTHH:MM:SSZ]
# With no argument, targetTime is one hour ago (UTC).
# Does not talk to the API server. The caller applies the printed YAML.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
src="${here}/pitr-drill-cluster.yaml"
stamp='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'

if [[ $# -gt 1 ]]; then
  echo "usage: render-cluster.sh [YYYY-MM-DDTHH:MM:SSZ]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  when="$1"
  if [[ ! "${when}" =~ ${stamp} ]]; then
    echo "targetTime must be YYYY-MM-DDTHH:MM:SSZ" >&2
    exit 2
  fi
else
  when="$(date -u -v-1H '+%Y-%m-%dT%H:%M:%SZ')"
fi

count="$(grep -c '__TARGET_TIME__' "${src}" || true)"
if [[ "${count}" != "1" ]]; then
  echo "expected one targetTime placeholder in ${src}, found ${count}" >&2
  exit 1
fi
rendered="$(sed "s/__TARGET_TIME__/${when}/" "${src}")"
if grep -q '__TARGET_TIME__' <<<"${rendered}"; then
  echo "placeholder survived render" >&2
  exit 1
fi
echo "# targetTime=${when}" >&2
printf '%s\n' "${rendered}"
