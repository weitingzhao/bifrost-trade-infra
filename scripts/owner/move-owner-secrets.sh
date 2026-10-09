#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Move administrator plaintext out of checkouts the Agent can read, into
# ~/.bifrost-owner/ (mode 700; owner.env mode 600). Idempotent. --undo puts
# the same keys and files back. Values are never printed.
#
#   move-owner-secrets.sh
#   move-owner-secrets.sh --undo
#
# Overrides (tests): BIFROST_WORKSPACE, BIFROST_INFRA_ENV, BIFROST_PLATFORM_ENV,
# BIFROST_SECRETS_SRC, BIFROST_OWNER_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${BIFROST_WORKSPACE:-$(cd "$ROOT/.." && pwd)}"
INFRA_ENV="${BIFROST_INFRA_ENV:-$ROOT/.env}"
PLATFORM_ENV="${BIFROST_PLATFORM_ENV:-$WORKSPACE/bifrost-platform/.env}"
SECRETS_SRC="${BIFROST_SECRETS_SRC:-$ROOT/k8s/base/secrets}"
OWNER_DIR="${BIFROST_OWNER_DIR:-$HOME/.bifrost-owner}"
OWNER_ENV="${OWNER_DIR}/owner.env"
OWNER_SECRETS="${OWNER_DIR}/secrets"
MANIFEST="${OWNER_DIR}/secrets-manifest.txt"

UNDO=0
if [ $# -gt 1 ]; then
  echo "usage: move-owner-secrets.sh [--undo]" >&2
  exit 2
fi
if [ "${1:-}" = "--undo" ]; then
  UNDO=1
elif [ -n "${1:-}" ]; then
  echo "usage: move-owner-secrets.sh [--undo]" >&2
  exit 2
fi

INFRA_KEYS=(OPS_ADMIN_TOKEN REDIS_IB_PASSWORD BIFROST_PG_PASSWORD_PREVIOUS BIFROST_PG_PASSWORD_NEXT)
PLATFORM_KEYS=(UNIFI_HOST UNIFI_USER UNIFI_PASS UNIFI_API_KEY)

ensure_owner_dirs() {
  mkdir -p "$OWNER_DIR" "$OWNER_SECRETS"
  chmod 700 "$OWNER_DIR" "$OWNER_SECRETS"
  if [ ! -f "$OWNER_ENV" ]; then
    (umask 077 && : >"$OWNER_ENV")
  fi
  chmod 600 "$OWNER_ENV"
}

# move_keys SRC DEST KEY...  or, with --undo, the python flag.
# Prints only key names.
apply_keys() {
  local src="$1" dest="$2" direction="$3"
  shift 3
  [ "$#" -gt 0 ] || return 0
  if [ ! -f "$src" ] && [ "$direction" = "to-owner" ]; then
    echo "skip missing $(basename "$src")"
    return 0
  fi
  python3 - "$src" "$dest" "$direction" "$@" <<'PY'
import os, sys
src, dest, direction, *keys = sys.argv[1:]

def lines_of(path):
    try:
        return open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return []

def entries(path):
    found = {}
    for line in lines_of(path):
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        val = raw.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        found[key] = (val, line)
    return found

def rewrite(path, drop):
    kept = []
    for line in lines_of(path):
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in drop:
                continue
        kept.append(line)
    body = "\n".join(kept)
    if body and not body.endswith("\n"):
        body += "\n"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    open(path, "w", encoding="utf-8").write(body)
    os.chmod(path, 0o600)

src_map = entries(src)
dest_map = entries(dest)
wanted = list(keys)
label = "moved" if direction == "to-owner" else "restored"
where = "owner.env" if direction == "to-owner" else "the checkout"

moving = [k for k in wanted if k in src_map]
for key in moving:
    if key in dest_map and dest_map[key][0] != src_map[key][0]:
        sys.stderr.write(f"REFUSED: {key} differs between source and {where}\n")
        sys.exit(1)
if moving:
    rewrite(src, set(moving))
    extra = [src_map[key][1] for key in moving if key not in dest_map]
    if extra:
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        existing = "\n".join(lines_of(dest))
        prefix = ""
        if existing and not existing.endswith("\n"):
            prefix = "\n"
        elif existing:
            prefix = ""
        with open(dest, "a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write("\n".join(extra) + "\n")
        os.chmod(dest, 0o600)
    for key in moving:
        print(f"{label} {key}" if key not in dest_map else f"already {label} {key}")
for key in wanted:
    if key not in src_map:
        if key in dest_map and direction == "to-owner":
            print(f"already moved {key}")
        else:
            print(f"absent {key}")
PY
}

is_secret_file() {
  local base="$1"
  case "$base" in
    *.example|*.example.yaml|*example.yaml) return 1 ;;
  esac
  return 0
}

move_files() {
  local base dest src
  [ -d "$SECRETS_SRC" ] || { echo "skip missing secrets dir"; return 0; }
  : >"$MANIFEST.part"
  if [ -f "$MANIFEST" ]; then
    cat "$MANIFEST" >>"$MANIFEST.part"
  fi
  for src in "$SECRETS_SRC"/*; do
    [ -f "$src" ] || continue
    base="$(basename "$src")"
    is_secret_file "$base" || continue
    dest="$OWNER_SECRETS/$base"
    if [ -f "$dest" ]; then
      if cmp -s "$src" "$dest"; then
        rm -f "$src"
        echo "already moved $base"
      else
        echo "REFUSED: $base exists in both places and differs" >&2
        rm -f "$MANIFEST.part"
        exit 1
      fi
    else
      mv "$src" "$dest"
      chmod 600 "$dest"
      echo "moved $base"
    fi
    grep -qxF "$base" "$MANIFEST.part" || printf '%s\n' "$base" >>"$MANIFEST.part"
  done
  if [ -f "$MANIFEST" ]; then
    while IFS= read -r base; do
      [ -n "$base" ] || continue
      grep -qxF "$base" "$MANIFEST.part" || printf '%s\n' "$base" >>"$MANIFEST.part"
    done <"$MANIFEST"
  fi
  sort -u "$MANIFEST.part" -o "$MANIFEST"
  rm -f "$MANIFEST.part"
  chmod 600 "$MANIFEST"
}

undo_files() {
  local base dest src
  [ -f "$MANIFEST" ] || { echo "no secrets manifest"; return 0; }
  mkdir -p "$SECRETS_SRC"
  while IFS= read -r base; do
    [ -n "$base" ] || continue
    dest="$OWNER_SECRETS/$base"
    src="$SECRETS_SRC/$base"
    if [ -f "$dest" ] && [ -f "$src" ]; then
      if cmp -s "$dest" "$src"; then
        rm -f "$dest"
        echo "already restored $base"
      else
        echo "REFUSED: $base exists in both places and differs" >&2
        exit 1
      fi
    elif [ -f "$dest" ]; then
      mv "$dest" "$src"
      chmod 600 "$src"
      echo "restored $base"
    else
      echo "absent $base"
    fi
  done <"$MANIFEST"
  : >"$MANIFEST"
  chmod 600 "$MANIFEST"
}

if [ "$UNDO" -eq 0 ]; then
  ensure_owner_dirs
  apply_keys "$INFRA_ENV" "$OWNER_ENV" to-owner "${INFRA_KEYS[@]}"
  if [ -f "$PLATFORM_ENV" ]; then
    apply_keys "$PLATFORM_ENV" "$OWNER_ENV" to-owner "${PLATFORM_KEYS[@]}"
  else
    echo "skip missing platform env"
  fi
  chmod 600 "$OWNER_ENV"
  move_files
else
  ensure_owner_dirs
  apply_keys "$OWNER_ENV" "$INFRA_ENV" to-checkout "${INFRA_KEYS[@]}"
  apply_keys "$OWNER_ENV" "$PLATFORM_ENV" to-checkout "${PLATFORM_KEYS[@]}"
  undo_files
fi
