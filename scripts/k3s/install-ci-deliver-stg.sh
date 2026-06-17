#!/usr/bin/env bash
# Deprecated wrapper — Phase B deliver is install-phase-b-stg.sh
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-phase-b-stg.sh" "$@"
