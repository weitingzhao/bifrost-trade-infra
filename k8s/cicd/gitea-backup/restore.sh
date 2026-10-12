#!/usr/bin/env bash
# Human/off-cluster restore. The identity never enters a cluster Job.
set -euo pipefail
umask 077
[[ $# == 3 ]] || { printf 'Usage: restore.sh <run dir> <identity file> <target dir>\n' >&2; exit 1; }
run=$(cd "$1" && pwd)
identity=$2
target=$3
[[ -r "$identity" && $(cat "$run/STATUS") == OK ]] || exit 1
[[ ! -e "$target" ]] || { printf 'Target must not exist.\n' >&2; exit 1; }
# Check only known ciphertext filenames; never allow checksum path traversal.
awk '!/^#/ { if (NF!=2 || ($2!="data.tar.age" && $2!="MANIFEST.tsv.age")) exit 1; n++ } END { if (n!=2) exit 1 }' "$run/SHA256SUMS"
work=$(mktemp -d "${TMPDIR:-/tmp}/gitea-restore.XXXXXX")
cleanup() { rc=$?; trap - EXIT; rm -rf "$work"; exit "$rc"; }
trap cleanup EXIT
awk '!/^#/ {print}' "$run/SHA256SUMS" > "$work/ciphertext-sums"
(cd "$run"; sha256sum -c "$work/ciphertext-sums")
age -d -i "$identity" -o "$work/data.tar" "$run/data.tar.age"
want=$(awk '$1=="#" && $2=="plaintext_sha256" && $3=="data.tar" {print $4}' "$run/SHA256SUMS")
[[ "$want" =~ ^[0-9a-f]{64}$ ]] || exit 1
[[ $(sha256sum "$work/data.tar" | awk '{print $1}') == "$want" ]] || { printf 'Plaintext archive sha256 mismatch.\n' >&2; exit 1; }
age -d -i "$identity" -o "$work/MANIFEST.tsv" "$run/MANIFEST.tsv.age"
tar -tf "$work/data.tar" > "$work/members"
if grep -E '(^/|(^|/)\.\.(/|$))' "$work/members" >/dev/null; then printf 'Unsafe archive member.\n' >&2; exit 1; fi
mkdir "$target"
tar -C "$target" -xf "$work/data.tar"
# Keep the manifest next to, rather than inside, the restored data tree.
cp "$work/MANIFEST.tsv" "$target.MANIFEST.tsv"
printf 'Decrypted, plaintext sha256 checked, extracted to %s\n' "$target"
