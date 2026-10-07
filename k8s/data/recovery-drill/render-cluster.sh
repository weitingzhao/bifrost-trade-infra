#!/bin/bash
# Print the scratch Cluster manifest with targetTime set to one hour ago (UTC).
# Does not talk to the API server. Owner applies the printed YAML.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
when="$(date -u -v-1H '+%Y-%m-%dT%H:%M:%SZ')"
echo "# targetTime=${when} (one hour before render)" >&2
sed "s/__TARGET_TIME__/${when}/" "${here}/cluster.yaml"
