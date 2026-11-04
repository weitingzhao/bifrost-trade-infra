#!/usr/bin/env bash
# td444-move.sh: map guards, identity, pre/final/verify, temperature guard, cancellation,
# exports (runbook §2, §3.3). Run through run.sh. Regression tests of the implementation
# review are named after its items (M1, M6, M9, S2, S6), those of the fix review after
# theirs (R1, R5, S1).
set -euo pipefail
. "$(dirname "$0")/lib.sh"
pkg_setup

mkdir -p /volume1/k3s-hot /volume1/k3s-cold /volume2/k3s-fast /volume2/minio-backup /volume2/market-archive-backup
B1=/volume1/k3s-hot/old-b1
mkdir -p "$B1/daily/2026-11-01T043000Z" "$B1/drills"
(cd "$B1/daily/2026-11-01T043000Z" && echo dump > a.dump && echo m > manifest.tsv && echo e > extensions.tsv && sha256sum a.dump manifest.tsv extensions.tsv > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"
B2=/volume1/k3s-cold/old-b2
mkdir -p "$B2/2026-11-01T031000Z"
(cd "$B2/2026-11-01T031000Z" && echo c1 > data.tar.age && echo c2 > MANIFEST.tsv.age && sha256sum data.tar.age MANIFEST.tsv.age > SHA256SUMS && echo '# plaintext_sha256 data.tar abc' >> SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T031000Z > "$B2/LATEST"
B3=/volume1/k3s-cold/old-b3
cs_fixture() { # cs_fixture <dir> <daily 1|0>
  mkdir -p "$1"
  (cd "$1"
   for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do echo "$f" > "$f"; done
   { echo "timestamp 2026-11-01T05:15:00Z"
     for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do
       echo "file $f ciphertext_bytes $(stat -c %s "$f") ciphertext_sha256 $(sha256sum "$f" | cut -d' ' -f1)"; done; } > MANIFEST
   if [[ $2 == 1 ]]; then echo OK > STATUS; fi)
}
cs_fixture "$B3/daily/2026-11-01" 1
cs_fixture "$B3/monthly/2026-11" 0
cat > /map <<'EOF'
daily B1 logical /volume1/k3s-hot/old-b1 /volume2/k3s-fast/data-logical-backup-hot
daily B2 gitea /volume1/k3s-cold/old-b2 /volume2/k3s-fast/cicd-gitea-backup
daily B3 cluster-state /volume1/k3s-cold/old-b3 /volume2/k3s-fast/kube-system-cluster-state-backup /volume1/k3s-cold
EOF
G=(--state /state --map /map --pkg /pkg --sums /sums)
YES3=$'yes\nyes\nyes\n'

# ---- map guards
printf 'daily B9 plain /etc /volume2/k3s-fast/x\n' > /badmap
expect_fail "a source outside the allowed roots is refused" bash "$PMOVE" --state /state --map /badmap identity-check daily
printf 'daily B9 plain /volume1/k3s-hot/a /volume1/k3s-hot/a/b\n' > /badmap
expect_fail "overlapping source and target on one line are refused" bash "$PMOVE" --state /state --map /badmap identity-check daily
mkdir -p /volume1/k3s-hot/m6a /volume1/k3s-hot/m6b
printf 'daily B1 plain /volume1/k3s-hot/m6a /volume2/k3s-fast/m6-same\ndaily B2 plain /volume1/k3s-hot/m6b /volume2/k3s-fast/m6-same\n' > /badmap
expect_fail "M6: two keys with the same target are refused" bash "$PMOVE" "${G[@]/\/map//badmap}" --confirm daily identity-record daily
check "M6: nothing was created for the refused map" test ! -e /volume2/k3s-fast/m6-same
printf 'daily B1 plain /volume1/k3s-hot/m6a /volume2/k3s-fast/m6-t\ndaily B2 plain /volume1/k3s-hot/m6b /volume2/k3s-fast/m6-t/inner\n' > /badmap
expect_fail "M6: nested targets across lines are refused" bash "$PMOVE" "${G[@]/\/map//badmap}" --confirm daily identity-record daily
printf 'daily B1 plain /volume1/k3s-hot/m6a /volume2/k3s-fast/m6-x\nreg REG plain /volume2/k3s-fast/m6-x/sub /volume2/k3s-fast/m6-y\n' > /badmap
expect_fail "M6: a target that holds another line's source is refused" bash "$PMOVE" "${G[@]/\/map//badmap}" map-check
printf 'daily B1 plain /volume1/k3s-hot/m6a /volume2/k3s-fast/m6-x\ndaily B1 plain /volume1/k3s-hot/m6b /volume2/k3s-fast/m6-z\n' > /badmap
expect_fail "M6: a key used twice is refused" bash "$PMOVE" "${G[@]/\/map//badmap}" map-check
printf 'reg REG registry /volume1/k3s-cold/m6r /volume2/k3s-fast/m6-reg\nreg-recovery REGB registry /volume2/k3s-fast/m6-reg /volume1/k3s-cold/td444-recovery/m6-reg\n' > /goodmap
expect_ok "M6 control: a recovery line may read a normal line's target" bash "$PMOVE" --state /state --map /goodmap map-check
expect_fail "pre without --confirm is refused" bash "$PMOVE" "${G[@]}" pre daily
expect_fail "pre with the wrong --confirm is refused" bash "$PMOVE" "${G[@]}" --confirm reg pre daily

# ---- S6: the entry point must be the package's own copy
expect_fail "S6: a writing command run from outside the package is refused" bash "$MOVE" "${G[@]}" --confirm daily identity-record daily
# ---- S2: pre checks the recorded mount identity before the first write
expect_fail "S2: pre without a recorded identity writes nothing" bash "$PMOVE" "${G[@]}" --confirm daily pre daily
check "S2: no target was created" test ! -e /volume2/k3s-fast/data-logical-backup-hot

# ---- identity, pre, final, verify
expect_ok "identity-record" bash "$PMOVE" "${G[@]}" --confirm daily identity-record daily
expect_ok "identity-check matches" bash "$PMOVE" "${G[@]}" identity-check daily
expect_ok "pre copies (add only)" bash "$PMOVE" "${G[@]}" --confirm daily pre daily
echo extra > /volume2/k3s-fast/data-logical-backup-hot/stale-file
expect_fail "final without a typed yes stops" script -qec "bash $PMOVE ${G[*]} --confirm daily final daily" /dev/null < <(echo no)
expect_ok "final with yes deletes, copies and verifies" script -qec "bash $PMOVE ${G[*]} --confirm daily final daily" /dev/null < <(printf '%s' "$YES3")
check "final removed the file the source does not have" test ! -e /volume2/k3s-fast/data-logical-backup-hot/stale-file
expect_ok "verify passes on identical trees" bash "$PMOVE" "${G[@]}" verify daily
f=/volume2/k3s-fast/data-logical-backup-hot/drills/x
printf 'aaaa\n' > "$B1/drills/x"; cp -p "$B1/drills/x" "$f"
printf 'bbbb\n' > "$f.new"; touch -r "$f" "$f.new"; mv "$f.new" "$f"
expect_fail "verify catches same size, same mtime, other content (-c)" bash "$PMOVE" "${G[@]}" verify daily
cp -p "$B1/drills/x" "$f"
T3=/volume2/k3s-fast/kube-system-cluster-state-backup
sed -i '/^file /d' "$T3/monthly/2026-11/MANIFEST" && sed -i '/^file /d' "$B3/monthly/2026-11/MANIFEST"
touch -r "$B3/monthly/2026-11/MANIFEST" "$T3/monthly/2026-11/MANIFEST"
expect_fail "M5: a monthly MANIFEST without file lines fails verify (own manifests)" bash "$PMOVE" "${G[@]}" verify daily
cs_fixture "$B3/monthly/2026-11" 0; cp -a "$B3/monthly/2026-11/." "$T3/monthly/2026-11/"; touch -r "$B3/monthly/2026-11" "$T3/monthly/2026-11"
expect_ok "verify passes again after repair" bash "$PMOVE" "${G[@]}" verify daily
cp /state/identity/daily.rec /state/identity/daily.rec.keep && sed -i 's/ rw / ro /' /state/identity/daily.rec
expect_fail "identity-check stops when the recorded identity differs" bash "$PMOVE" "${G[@]}" identity-check daily
mv /state/identity/daily.rec.keep /state/identity/daily.rec

# ---- temperature guard (both sensors must be readable)
head -c 3000000 /dev/urandom > "$B1/big.bin"
echo 80000 > /hwmon/hwmon0/temp1_input
( sleep 8; echo 60000 > /hwmon/hwmon0/temp1_input ) &
expect_ok "pre pauses at 72 °C and resumes at 65 °C" bash "$PMOVE" "${G[@]}" --confirm daily --temp-poll 1 --bwlimit 300K pre daily
grep -q 'copy paused' /tmp/out && grep -q 'copy resumed' /tmp/out && ok "pause and resume were logged" || bad "no pause/resume in the log"
head -c 3000000 /dev/urandom > "$B1/big2.bin"
mv /hwmon/hwmon1/temp1_input /hwmon/hwmon1.keep
( sleep 7; mv /hwmon/hwmon1.keep /hwmon/hwmon1/temp1_input ) &
expect_ok "one of two sensors missing pauses after --temp-missing" bash "$PMOVE" "${G[@]}" --confirm daily --temp-poll 1 --temp-missing 3 --bwlimit 300K pre daily
grep -q 'no reading from every SSD' /tmp/out && ok "missing sensor was logged" || bad "missing sensor not logged"
head -c 3000000 /dev/urandom > "$B1/big3.bin"
expect_fail "--timeout stops a long copy" bash "$PMOVE" "${G[@]}" --confirm daily --timeout 2 --bwlimit 10K --temp-poll 1 pre daily
# S1: a known over-temperature pauses at once, even while another sensor gives no reading
head -c 3000000 /dev/urandom > "$B1/big4.bin"
echo 80000 > /hwmon/hwmon0/temp1_input; mv /hwmon/hwmon1/temp1_input /hwmon/hwmon1.keep; rm -f /tmp/paused.sample
( sleep 4; cp /state/copy-paused /tmp/paused.sample 2> /dev/null || true; sleep 2
  echo 60000 > /hwmon/hwmon0/temp1_input; mv /hwmon/hwmon1.keep /hwmon/hwmon1/temp1_input ) &
expect_ok "S1: one sensor at 80 °C and one missing: the copy pauses, then resumes" bash "$PMOVE" "${G[@]}" --confirm daily --temp-poll 1 --temp-missing 100 --bwlimit 300K pre daily
check "S1: the pause is logged as over-temperature at once (no missing-sensor grace)" grep -q 'copy paused: SSD at 80 °C' /tmp/out
check "S1: the pause state names the over-temperature" grep -q 'SSD at 80 °C' /tmp/paused.sample
check "S1: resumed only with every sensor read and cool" grep -q 'copy resumed: all 2 SSD sensors read, highest 60 °C' /tmp/out
check "S1: no pause state is left after the copy" test ! -e /state/copy-paused

# ---- M1: cancelling the script stops the copy it started
target=/volume2/k3s-fast/data-logical-backup-hot
cancel_case() { # cancel_case <name> <how>
  head -c 4000000 /dev/urandom > "$B1/cancel-$1.bin"
  case $2 in
    term) bash "$PMOVE" "${G[@]}" --confirm daily --bwlimit 50K --temp-poll 1 pre daily > /tmp/out 2>&1 & pid=$!; sleep 4; kill -TERM "$pid" ;;
    int) perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' bash "$PMOVE" "${G[@]}" --confirm daily --bwlimit 50K --temp-poll 1 pre daily > /tmp/out 2>&1 & pid=$!; sleep 4; kill -INT "$pid" ;;
    outer) timeout 4 bash "$PMOVE" "${G[@]}" --confirm daily --bwlimit 50K --temp-poll 1 pre daily > /tmp/out 2>&1 & pid=$! ;;
  esac
  wait "$pid" || true
  sleep 1
  local s1 s2
  s1=$(du -sb --apparent-size "$target" | cut -f1); sleep 3; s2=$(du -sb --apparent-size "$target" | cut -f1)
  check "M1: $1 — target stops changing after the script ends" test "$s1" = "$s2"
  check "M1: $1 — no rsync is left running" bash -c '! pgrep -x rsync > /dev/null'
  check "M1: $1 — no active-copy record is left" test ! -e /state/active-copy
  if [[ $2 == term ]]; then check "M1: $1 — the log says the copy stopped" grep -q 'no copy of this run is left running' "$(newest_log)"; fi
  pkill -x rsync || true; rm -f "$B1/cancel-$1.bin"
}
newest_log() { find /state/logs -name '*-pre-daily.log' -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2; }
cancel_case TERM term
cancel_case INT int
cancel_case "outer timeout" outer

# ---- R1: a copy group that survives KILL keeps its record and blocks the next writer
# (kill double through BASH_ENV: the real rsync keeps running, the script cannot stop it)
stuck_case() { # stuck_case <name> term|timeout
  local t0=$SECONDS rc=0 pid
  head -c 4000000 /dev/urandom > "$B1/stuck-$2.bin"
  case $2 in
    term) BASH_ENV=/tmp/stuck-kill.sh bash "$PMOVE" "${G[@]}" --confirm daily --bwlimit 20K --temp-poll 1 pre daily > /tmp/out 2>&1 & pid=$!; sleep 4; kill -TERM "$pid" ;;
    timeout) BASH_ENV=/tmp/stuck-kill.sh timeout 90 bash "$PMOVE" "${G[@]}" --confirm daily --timeout 3 --bwlimit 20K --temp-poll 1 pre daily > /tmp/out 2>&1 & pid=$! ;;
  esac
  wait "$pid" || rc=$?
  check "R1: $1 — the script fails" test "$rc" -ne 0
  check "R1: $1 — it returns within the stop grace, without waiting for the copy" test $((SECONDS - t0)) -lt 60
  check "R1: $1 — the active-copy record is kept" test -s /state/active-copy
  check "R1: $1 — the record is marked stop-failed" grep -q 'stop-failed' /state/active-copy
  check "R1: $1 — the log says the copy did not stop" grep -q 'did NOT stop' "$(newest_log)"
  check "R1: $1 — the log never claims that no copy is left" bash -c "! grep -q 'no copy of this run is left running' '$(newest_log)'"
  expect_fail "R1: $1 — the next writing command refuses while the group lives" bash "$PMOVE" "${G[@]}" --confirm daily pre daily
  pkill -KILL -x rsync || true
  for _ in 1 2 3 4 5; do pgrep -x rsync > /dev/null || break; sleep 1; done
  expect_ok "R1 control: $1 — once the group is gone the next run clears the record and copies" bash "$PMOVE" "${G[@]}" --confirm daily pre daily
  check "R1 control: $1 — no record is left" test ! -e /state/active-copy
  rm -f "$B1/stuck-$2.bin"
}
stuck_case "abort by TERM" term
stuck_case "--timeout" timeout
rm -f "$B1"/big*.bin

# ---- exports (M9: ACL read errors never pass)
cat > /tmp/exports.txt <<'EOF'
/volume1/k3s-hot
		10.0.0.0/24(sync,wdelay,hide,no_subtree_check,anonuid=1000,anongid=100,sec=sys,rw,secure,all_squash)
/volume2/k3s-fast
		10.0.0.0/24(rw,sync,wdelay,hide,no_subtree_check,sec=sys,secure,all_squash,anonuid=1000,anongid=100)
/volume2/market-archive-backup	10.0.0.0/24(sync,wdelay,hide,no_subtree_check,anonuid=1000,anongid=100,sec=sys,rw,secure,all_squash)
EOF
chmod 755 /volume1/k3s-hot /volume2/k3s-fast /volume2/market-archive-backup
expect_ok "exports with the same options in another order match" bash "$PMOVE" --state /state exports
echo '*' > /tmp/fake/getfacl_fail
expect_fail "M9: ACLs unreadable on both sides fail exports" bash "$PMOVE" --state /state exports
echo /volume2/k3s-fast > /tmp/fake/getfacl_fail
expect_fail "M9: ACLs unreadable on one side fail exports" bash "$PMOVE" --state /state exports
rm -f /tmp/fake/getfacl_fail
printf '%s\n' /volume1/k3s-hot /volume2/k3s-fast /volume2/market-archive-backup > /tmp/fake/stat_fail
expect_fail "R5: mode/owner unreadable on both sides fails exports" bash "$PMOVE" --state /state exports
check "R5: no share root is reported as matching" bash -c '! grep -q "mode, owner, ACL and xattrs match" /tmp/out'
echo /volume2/k3s-fast > /tmp/fake/stat_fail
expect_fail "R5: mode/owner unreadable on one side fails exports" bash "$PMOVE" --state /state exports
rm -f /tmp/fake/stat_fail
expect_ok "R5 control: with stat readable again exports pass" bash "$PMOVE" --state /state exports
chmod 000 /volume1/k3s-hot /volume2/k3s-fast /volume2/market-archive-backup
expect_ok "share roots of mode 000 (UGOS: access by ACL; stat %a reads 0) match" bash "$PMOVE" --state /state exports
check "mode 000 share roots are reported as matching" grep -q "share root /volume2/k3s-fast: mode, owner, ACL and xattrs match" /tmp/out
chmod 755 /volume2/k3s-fast
expect_fail "a share root of another mode than the reference is caught" bash "$PMOVE" --state /state exports
chmod 755 /volume1/k3s-hot /volume2/market-archive-backup
sed -i 's/,all_squash)$/,root_squash)/' /tmp/exports.txt
expect_fail "a different squash option is caught" bash "$PMOVE" --state /state exports

# ---- S2: snap-clean deletes only recorded, read-only snapshots
mkdir -p /volume2/k3s-fast/@bifrost/td444-snap/REG-x && echo uuid-REG-x > /volume2/k3s-fast/@bifrost/td444-snap/REG-x/.fake-uuid
echo "/volume2/k3s-fast/@bifrost/td444-snap/REG-x uuid-other" > /state/snapshots.list
expect_fail "S2: snap-clean refuses a snapshot whose UUID changed" bash "$PMOVE" "${G[@]}" --confirm snap-clean snap-clean
check "S2: the snapshot is still there" test -d /volume2/k3s-fast/@bifrost/td444-snap/REG-x
echo "/volume2/k3s-fast/@bifrost/td444-snap/REG-x uuid-REG-x" > /state/snapshots.list
touch /tmp/fake/snap_rw
expect_fail "S2: snap-clean refuses a snapshot that is not read-only" bash "$PMOVE" "${G[@]}" --confirm snap-clean snap-clean
rm -f /tmp/fake/snap_rw
expect_ok "S2 control: snap-clean deletes a recorded read-only snapshot" bash "$PMOVE" "${G[@]}" --confirm snap-clean snap-clean
check "S2 control: the snapshot is gone" test ! -e /volume2/k3s-fast/@bifrost/td444-snap/REG-x
finish
