#!/usr/bin/env bash
# Old name of check-governance-consistency.sh (cleanup wave 2, 2026-11-12: the
# workspace-level Cursor side and its parity-id checks were deleted).
# Kept only for callers that still use this path: infra Makefile
# check-agent-parity, and ci-infra's parity-static stage while the base copy of
# coverage_infra.py still names it (that stage runs `<this> --static-tree DIR`).
# Delete once both call check-governance-consistency.sh directly.
exec bash "$(dirname "$0")/check-governance-consistency.sh" "$@"
