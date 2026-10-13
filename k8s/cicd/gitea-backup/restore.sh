#!/usr/bin/env bash
# Human/off-cluster restore. The identity never enters a cluster Job.
set -euo pipefail
umask 077
[[ $# == 3 ]] || { printf 'Usage: restore.sh <run dir> <identity file> <target dir>\n' >&2; exit 1; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
run=$(cd "$1" && pwd) || die 'run directory unavailable'
identity=$2
target=$3
[[ -r "$identity" ]] || die 'identity file not readable'
[[ -f "$run/STATUS" && $(cat "$run/STATUS") == OK ]] || die 'run STATUS is not OK'
[[ ! -e "$target" ]] || die 'target must not exist'
# Check only known ciphertext filenames; never allow checksum path traversal.
awk '!/^#/ { if (NF!=2 || ($2!="data.tar.age" && $2!="MANIFEST.tsv.age")) exit 1; n++ } END { if (n!=2) exit 1 }' "$run/SHA256SUMS" || die 'ciphertext checksum list invalid'
work=$(mktemp -d "${TMPDIR:-/tmp}/gitea-restore.XXXXXX")
cleanup() { rc=$?; trap - EXIT; rm -rf "$work"; exit "$rc"; }
trap cleanup EXIT
awk '!/^#/ {print}' "$run/SHA256SUMS" > "$work/ciphertext-sums" || die 'ciphertext checksum list unreadable'
(cd "$run"; sha256sum -c "$work/ciphertext-sums") || die 'ciphertext checksum verification failed'
age -d -i "$identity" -o "$work/data.tar" "$run/data.tar.age" || die 'data archive age decryption/authentication failed'
want=$(awk '$1=="#" && $2=="plaintext_sha256" && $3=="data.tar" {print $4}' "$run/SHA256SUMS" || die 'ciphertext checksum list invalid')
[[ "$want" =~ ^[0-9a-f]{64}$ ]] || die 'plaintext archive checksum missing or invalid'
[[ $(sha256sum "$work/data.tar" | awk '{print $1}') == "$want" ]] || die 'plaintext archive sha256 mismatch'
age -d -i "$identity" -o "$work/MANIFEST.tsv" "$run/MANIFEST.tsv.age" || die 'manifest age decryption/authentication failed'
tar -tf "$work/data.tar" > "$work/members" || die 'archive listing failed'
if grep -E '(^/|(^|/)\.\.(/|$))' "$work/members" >/dev/null; then die 'unsafe archive member'; fi
mkdir "$target" || die 'target creation failed'
tar -C "$target" -xf "$work/data.tar" || die 'archive extraction failed'
# Keep the manifest next to, rather than inside, the restored data tree.
cp "$work/MANIFEST.tsv" "$target.MANIFEST.tsv" || die 'manifest copy failed'
printf 'Decrypted, plaintext sha256 checked, extracted to %s\n' "$target"
