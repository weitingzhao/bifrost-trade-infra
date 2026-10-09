#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Source it. owner_fill KEY [KEY...] exports each key when it is unset or empty.
# An already-set environment variable wins. Otherwise the value is read from
# ~/.bifrost-owner/owner.env (override with BIFROST_OWNER_ENV). Values are
# never printed.
# Sourced, not executed: do not change the caller's shell options.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "source scripts/owner/owner-env.sh; do not execute it" >&2
  exit 2
fi

owner_env_file() {
  printf '%s' "${BIFROST_OWNER_ENV:-${HOME}/.bifrost-owner/owner.env}"
}

owner_fill() {
  local key line val file
  file="$(owner_env_file)"
  for key in "$@"; do
    if [ -n "${!key-}" ]; then
      continue
    fi
    val=""
    if [ -f "$file" ]; then
      line="$(grep -E "^${key}=" "$file" | tail -1 || true)"
      val="${line#*=}"
      val="${val%\"}"
      val="${val#\"}"
      val="${val%\'}"
      val="${val#\'}"
    fi
    if [ -n "$val" ]; then
      printf -v "$key" '%s' "$val"
      export "$key"
    fi
  done
}
