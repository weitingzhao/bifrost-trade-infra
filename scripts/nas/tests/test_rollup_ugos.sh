#!/usr/bin/env bash
# backup-rollup/rollup.sh against an rsync that behaves as UGOS 1.18's (runbook §3.3, §5.1): no
# ACL support, owner and mode left unset on what it writes (inodes it links with --link-dest
# keep theirs), ug.* xattrs set by UGOS on the target. Two generations in a row: both verify,
# owners and modes are the source's, and the second links every unchanged file to the first
# (same inode) instead of copying it again. An extended ACL in a source, or a refused chown,
# fails the run and publishes nothing. Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
K=/volume2/k3s-fast
mkdir -p "$K" /volume1 /rconf
printf '%s\n' "$K" > /tmp/fake/subvols
B1=$K/rs-b1 RUN=daily/2026-11-01T043000Z
mkdir -p "$B1/$RUN" "$B1/drills"
(cd "$B1/$RUN" && echo dump > a.dump && echo key > secret.age && sha256sum a.dump secret.age > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"; echo d > "$B1/drills/note"
chown -R 1000:10 "$B1"; chown 0:0 "$B1/$RUN/secret.age"
find "$B1" -type d -exec chmod 755 {} +; find "$B1" -type f -exec chmod 644 {} +
chmod 777 "$B1"; chmod 1777 "$B1/drills"; chmod 600 "$B1/$RUN/secret.age"
printf '%s\n' "logical-backup-hot logical $B1 $K on" > /rconf/rollup.conf
R=(--conf /rconf/rollup.conf --dest /volume1/backup-weekly --dest-mount / --src-mount / --state /rstate --textfile /tf/backup-rollup.prom --keep 2 --now)
touch /tmp/fake/rsync_no_acls /tmp/fake/rsync_ugos
committed() { local g; for g in /volume1/backup-weekly/"$1"/*T*Z; do [[ -e $g && -f /volume1/backup-weekly/.committed/${g##*/} ]] && echo "${g##*/}"; done; return 0; }
gens() { committed logical-backup-hot | wc -l | tr -d ' '; }
attrs() { (cd "$1" && find . ! -name GENERATION.json -printf '%m %U %G %y %p\n' | LC_ALL=C sort); }
same_attrs() { diff <(attrs "$B1") <(attrs "$1") > /tmp/attrs.diff || { head -5 /tmp/attrs.diff; return 1; }; }
linked() { [[ $1 != "$2" && -f $1 && -f $2 && $(stat -c %i "$1") == "$(stat -c %i "$2")" ]]; }   # two existing names, one inode
gen_dir() { echo "/volume1/backup-weekly/logical-backup-hot/$(committed logical-backup-hot | sed -n "${1}p")"; }

expect_ok "UGOS roll-up: the first generation copies, sets owner and mode, verifies and publishes" bash "$ROLL" "${R[@]}"
check "UGOS roll-up: one generation" test "$(gens)" = 1
check "UGOS roll-up: the rsync double left owner and mode unset (the fix-up set them)" grep -Eq 'owner and mode set on [1-9][0-9]*,' /tmp/out
check "UGOS roll-up: the first generation's owners and modes are the source's" same_attrs "$(gen_dir 1)"
check "UGOS roll-up: every rsync left -A and ug.* out" bash -c "[[ -s /tmp/fake/rsync.log ]] && ! grep -qvF -- '--filter=-x ug.*' /tmp/fake/rsync.log && ! grep -qE -- '-[a-zA-Z]*A' /tmp/fake/rsync.log"
sleep 1
echo changed > "$B1/drills/note"; chown 1000:10 "$B1/drills/note"; chmod 644 "$B1/drills/note"
expect_ok "UGOS roll-up: the second generation verifies and publishes" bash "$ROLL" "${R[@]}"
check "UGOS roll-up: two generations" test "$(gens)" = 2
g1=$(gen_dir 1) g2=$(gen_dir 2)
check "UGOS roll-up: the second generation's owners and modes are the source's" same_attrs "$g2"
for f in "$RUN/a.dump" "$RUN/secret.age" "$RUN/SHA256SUMS" LATEST; do
  check "UGOS roll-up: unchanged $f is a hard link to the first generation (same inode)" linked "$g1/$f" "$g2/$f"
done
check "UGOS roll-up: the changed file is a new copy" bash -c "[[ -f '$g1/drills/note' && -f '$g2/drills/note' && \$(stat -c %i '$g1/drills/note') != \$(stat -c %i '$g2/drills/note') ]]"
check "UGOS roll-up: the first generation's owners and modes were not touched by the second" same_attrs "$g1"
# ---- failures publish nothing
sleep 1; echo '*' > /tmp/fake/extended_acl
expect_fail "UGOS roll-up: an extended ACL in a source stops the run (this rsync cannot copy it)" bash "$ROLL" "${R[@]}"
check "UGOS roll-up: the log says why" grep -q 'extended POSIX ACLs this rsync cannot copy' /tmp/out
check "UGOS roll-up: nothing published" test "$(gens)" = 2
rm -f /tmp/fake/extended_acl
sleep 1; touch /tmp/fake/python_no_chown
expect_fail "UGOS roll-up: a refused chown fails the run" bash "$ROLL" "${R[@]}"
check "UGOS roll-up: the log says setting owner and mode failed" grep -q 'setting owner and mode from the snapshot exited 1' /tmp/out
check "UGOS roll-up: nothing published after the refused chown" test "$(gens)" = 2
rm -f /tmp/fake/python_no_chown
sleep 1
expect_ok "UGOS roll-up control: with chown allowed the next generation publishes" bash "$ROLL" "${R[@]}"
finish
