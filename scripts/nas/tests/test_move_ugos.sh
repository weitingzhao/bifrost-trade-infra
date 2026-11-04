#!/usr/bin/env bash
# td444-move.sh against an rsync that behaves as UGOS 1.18's did on the NAS (11-04, runbook
# §3.3): no ACL support, owner and mode left unset (what it writes ends up 0:0, mode 000, with
# no error), and ug.* xattrs that UGOS sets itself on the target. pre and final set owner and
# mode from the source (td444-attrs.py) before the verification, which must list nothing; a
# failed fix-up fails the step and records no done; ug.* is no difference, user.* is.
# Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
pkg_setup
mkdir -p /volume1/k3s-cold /volume2/k3s-fast /state
echo /volume1/k3s-cold >> /tmp/fake/subvols
S=/volume1/k3s-cold/old-reg T=/volume2/k3s-fast/cicd-registry-data
B=docker/registry/v2/blobs/sha256/00/abc
# the source: the owners and modes the NAS showed (1000:10, dirs 755 / 777, files 644), and
# a root-owned 600 file with a hard link, a sticky and a setgid directory, a symlink, a user.* xattr
mkdir -p "$S/$B" "$S/drills" "$S/shared"
echo blob > "$S/$B/data"; echo key > "$S/secret"; echo l > "$S/drills/x"; echo s > "$S/shared/f"
ln -s docker/registry "$S/link"; ln "$S/secret" "$S/secret.hard"
chown -R 1000:10 "$S"; chown 0:0 "$S/secret"
find "$S" -type d -exec chmod 755 {} +; find "$S" -type f -exec chmod 644 {} +
chmod 777 "$S"; chmod 1777 "$S/drills"; chmod 2775 "$S/shared"; chmod 600 "$S/secret"
setfattr -n user.td444 -v kept "$S/$B/data"
printf 'reg REG plain %s %s /volume1/k3s-cold\n' "$S" "$T" > /map
G=(--state /state --map /map --pkg /pkg --sums /sums)
touch /tmp/fake/rsync_no_acls /tmp/fake/rsync_ugos
attrs() { (cd "$1" && find . -printf '%m %U %G %y %p\n' | LC_ALL=C sort); }
same_attrs() { diff <(attrs "$S") <(attrs "$T") > /tmp/attrs.diff || { head -5 /tmp/attrs.diff; return 1; }; }
dones() { grep -c " done $1" /state/reg.phase 2> /dev/null || true; }
final_yes() { tty_run $'yes\n' bash "$PMOVE" "${G[@]}" --confirm reg final reg; }

expect_ok "identity-record reg" bash "$PMOVE" "${G[@]}" --confirm reg identity-record reg
# ---- pre --from-snapshot: copy, set owner and mode, verify (the NAS's pre reg listed 16222 pog lines)
expect_ok "UGOS: pre --from-snapshot copies, sets owner and mode, and verifies with an empty list" \
  bash "$PMOVE" "${G[@]}" --confirm reg --from-snapshot pre reg
check "UGOS: the rsync double really left owner and mode unset (the fix-up set them)" grep -Eq 'owner and mode set on [1-9][0-9]*,' /tmp/out
check "UGOS: the hard link was handled once" grep -q '1 hard-link repeats' /tmp/out
check "UGOS: after pre the target's owners and modes are the source's" same_attrs
check "UGOS: the user.* xattr was copied" test "$(getfattr --only-values -n user.td444 "$T/$B/data" 2> /dev/null)" = kept
check "UGOS: every copy and comparison left ug.* out" bash -c "[[ -s /tmp/fake/rsync.log ]] && ! grep -qvF -- '--filter=-x ug.*' /tmp/fake/rsync.log"
expect_ok "UGOS: verify passes (ug.* differs on the target, and is no difference)" bash "$PMOVE" "${G[@]}" verify reg
setfattr -n user.td444 -v changed "$T/$B/data"
expect_fail "UGOS: a differing user.* xattr is still a difference" bash "$PMOVE" "${G[@]}" verify reg
setfattr -n user.td444 -v kept "$T/$B/data"
# ---- final: the --delete pass sets owner and mode the same way
echo new > "$S/$B/new"; chown 1000:10 "$S/$B/new"; chmod 640 "$S/$B/new"; echo stale > "$T/stale"
expect_ok "UGOS: final copies, deletes, sets owner and mode, and verifies" final_yes
check "UGOS: after final the target's owners and modes are the source's" same_attrs
check "UGOS: final deleted what the source does not have" test ! -e "$T/stale"
# ---- a fix-up that fails (chown refused) fails the step and records no done
d=$(dones pre:REG); echo more > "$S/$B/more"; chown 1000:10 "$S/$B/more"; touch /tmp/fake/python_no_chown
expect_fail "UGOS: pre fails when setting an owner is refused" bash "$PMOVE" "${G[@]}" --confirm reg pre reg
check "UGOS: that pre recorded no done" test "$(dones pre:REG)" = "$d"
check "UGOS: and recorded why" grep -q ' fail pre:REG owner/mode fix-up 1' /state/reg.phase
check "UGOS: the log names the refused path" grep -q 'cannot set owner 1000:10 and mode .* Operation not permitted' /tmp/out
d=$(dones final:REG)
expect_fail_with "UGOS: final fails when setting an owner is refused" 1 'FAIL: REG: setting owner and mode on .* exited 1' final_yes
check "UGOS: that final recorded no done" test "$(dones final:REG)" = "$d"
check "UGOS: and recorded why" grep -q ' fail final:REG owner/mode fix-up 1' /state/reg.phase
rm -f /tmp/fake/python_no_chown
expect_ok "UGOS control: with chown allowed again pre sets everything" bash "$PMOVE" "${G[@]}" --confirm reg --from-snapshot pre reg
check "UGOS control: the owners and modes match again" same_attrs
expect_ok "td444-attrs.py unit tests (round 6: no escape from the target tree, hard-link conflicts)" python3 "$SRC/tests/test_td444_attrs.py"
finish
