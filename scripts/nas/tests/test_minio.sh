#!/usr/bin/env bash
# td444-minio.sh: M0–M4b with a fake docker, the fallback-eligibility table, base-check,
# continuity and the range hand-over (runbook §4 group 6). Run through run.sh.
# Regression tests of the implementation review: M2, M3, M4, S3; of the fix review: R2.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
pkg_setup
D=/volume2/minio-backup/data
CD=/volume1/docker/minio-backup
mkdir -p "$D" "$CD" /volume1/k3s-hot /state
cp /pkg/k8s/data/minio/nas/compose.yaml "$CD/compose.yaml"
cp /pkg/k8s/data/minio/nas/compose.isolated.yaml /pkg/k8s/data/minio/nas/compose.recovery.yaml "$CD/"   # as m3 installs them
ORIG_SHA=$(sha256sum "$CD/compose.yaml" | cut -d' ' -f1)
M=(--state /state --pkg /pkg --sums /sums --compose-dir "$CD")
dk() { mkdir -p /tmp/fake/dk; for kv in "$@"; do printf '%s\n' "${kv#*=}" > "/tmp/fake/dk/${kv%%=*}"; done; }
dk_reset() { rm -rf /tmp/fake/dk; dk exists=1 running=true id=cid-old netmode=minio-backup_default 'ports={"9000/tcp":[{"HostIp":"127.0.0.1"}]}' 'networks=minio-backup_default '; touch /tmp/fake/dk/healthy; }
phase_of() { printf '%s\n' "$@" | sed 's/^/2026-11-03T00:00:00Z /' > "/state/minio-$RUN.phase"; }

# ---- M4: an inspect error is not a stop
dk_reset; RUN=m4a
expect_ok "m0 starts a run" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio --expect-compose-sha256 "$ORIG_SHA" minio-m0
touch /tmp/fake/dk/inspect_fail
expect_fail "M4: m1 fails when docker inspect fails after stop" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m1
grep -q 'done m1' "/state/minio-$RUN.phase" && bad "M4: m1 recorded done without a stop proof" || ok "M4: no 'done m1' without a stop proof"
rm -f /tmp/fake/dk/inspect_fail
expect_ok "M4 control: m1 succeeds when inspect proves the stop" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m1
dk running=true
cat > /mmap <<'EOF'
minio MINIO minio /volume1/k3s-hot/old-minio /volume2/minio-backup/data /volume1/k3s-hot
EOF
mkdir -p /volume1/k3s-hot/old-minio/bifrost-postgres-backup/obj && echo x > /volume1/k3s-hot/old-minio/bifrost-postgres-backup/obj/xl.meta
bash "$PMOVE" --state /state --map /mmap --pkg /pkg --sums /sums --confirm minio identity-record minio > /dev/null 2>&1 || true
expect_fail_with "M4: m2 refuses when the container runs again after m1" 1 'FAIL: the container is running' \
  tty_run $'yes\n' bash "$PMOVE" "${M[@]}" --map /mmap --run-id "$RUN" --confirm minio minio-m2
check "M4: m2 did not write minio.base" test ! -e "/state/minio-$RUN.base"

# ---- M3: one M4a per run; isolation proofs bind to that attempt
dk_reset; RUN=m3a
phase_of "attempt m0" "done m0" "attempt m1" "done m1 cid-old" "attempt m2" "done m2" "attempt m3" "done m3"
dk running=false
expect_ok "M3 control: m4a creates an isolated container and starts it" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a
expect_ok "M3 control: m4a-stop reconfirms the isolation" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a-stop
expect_ok "M3 control: eligibility allows A after one clean m4a" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
expect_fail "M3: a second m4a in the same run is refused" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a
RUN=m3b
phase_of "attempt m4a 1" "done isolation_proven_pre 1 cid-1" "done m4a 1" "done isolation_reconfirmed 1 cid-1" "attempt m4a 2" "fail m4a 2" "fail isolation_reconfirmed 2"
expect_fail "M3: an older proof does not survive a later failed attempt" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
RUN=m3c
phase_of "attempt m4a 1" "done isolation_proven_pre 1 cid-1" "done m4a 1" "done isolation_reconfirmed 1 cid-2"
expect_fail "M3: a reconfirm of another container is not a proof" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
RUN=m3d
dk_reset; phase_of "attempt m3" "done m3"; dk running=false; touch /tmp/fake/dk/force_network
expect_fail "M3: m4a stops before start when the container is not isolated" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a
check "M3: the non-isolated container was never started" test "$(cat /tmp/fake/dk/running)" = false
rm -f /tmp/fake/dk/force_network

# ---- R2: a failed or unfinished reconfirmation voids A; rollback-a re-checks the container
r2_run() { # r2_run <run id> [m4a]: m0 and m1 for real, m2 and m3 recorded, then m4a + m4a-stop
  RUN=$1; dk_reset
  bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio --expect-compose-sha256 "$ORIG_SHA" minio-m0 > /dev/null 2>&1 || bad "R2 setup: m0 of $RUN"
  bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m1 > /dev/null 2>&1 || bad "R2 setup: m1 of $RUN"
  printf '2026-11-03T00:00:00Z %s\n' "attempt m2" "done m2" "attempt m3" "done m3" >> "/state/minio-$RUN.phase"
  [[ ${2:-} == m4a ]] || return 0
  bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a > /dev/null 2>&1 || bad "R2 setup: m4a of $RUN"
  bash "$PMOVE" "${M[@]}" --run-id "$RUN" --confirm minio minio-m4a-stop > /dev/null 2>&1 || bad "R2 setup: m4a-stop of $RUN"
}
not_started() { ! grep -q ' up -d ' /tmp/fake/dk/log; }
r2_run r2a m4a
expect_ok "R2 control: one clean m4a and m4a-stop allow A" bash "$PMOVE" --state /state --run-id r2a minio-eligibility
touch /tmp/fake/dk/inspect_fail
expect_fail "R2: a later m4a-stop whose inspect fails fails" bash "$PMOVE" "${M[@]}" --run-id r2a --confirm minio minio-m4a-stop
rm -f /tmp/fake/dk/inspect_fail
check "R2: the failed reconfirmation is recorded" grep -q ' fail isolation_reconfirmed' /state/minio-r2a.phase
expect_fail "R2: after a failed reconfirmation eligibility is NO-A" bash "$PMOVE" --state /state --run-id r2a minio-eligibility
RUN=r2b; phase_of "attempt m4a 1" "done isolation_proven_pre 1 cid-1" "done m4a 1" "done isolation_reconfirmed 1 cid-1" "attempt isolation_reconfirmed"
expect_fail "R2: a reconfirmation that never finished voids the earlier proof" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
r2_run r2c m4a
dk id=cid-replaced netmode=minio-backup_default 'ports={"9000/tcp":[{"HostIp":"127.0.0.1"}]}' 'networks=minio-backup_default ' running=false; : > /tmp/fake/dk/log
expect_fail "R2: rollback-a refuses when the container is not the one proven isolated" bash "$PMOVE" "${M[@]}" --run-id r2c --confirm minio minio-rollback-a
check "R2: that rollback-a started nothing" not_started
check "R2: and recorded no done rollback-a" bash -c '! grep -q " done rollback-a" /state/minio-r2c.phase'
expect_fail "R2: the replaced container voids A for the run" bash "$PMOVE" --state /state --run-id r2c minio-eligibility
r2_run r2d m4a
dk netmode=minio-backup_default 'ports={"9000/tcp":[{"HostIp":"127.0.0.1"}]}' 'networks=minio-backup_default '; : > /tmp/fake/dk/log
expect_fail "R2: rollback-a refuses when the proven container is no longer isolated" bash "$PMOVE" "${M[@]}" --run-id r2d --confirm minio minio-rollback-a
check "R2: that rollback-a started nothing" not_started
r2_run r2e
dk id=cid-replaced; : > /tmp/fake/dk/log
expect_fail "R2: without m4a, rollback-a refuses a container other than the one m1 stopped" bash "$PMOVE" "${M[@]}" --run-id r2e --confirm minio minio-rollback-a
check "R2: that rollback-a started nothing" not_started
r2_run r2f m4a; : > /tmp/fake/dk/log
expect_ok "R2 control: rollback-a after a clean m4a starts the old MinIO" bash "$PMOVE" "${M[@]}" --run-id r2f --confirm minio minio-rollback-a
check "R2 control: done rollback-a recorded" grep -q ' done rollback-a' /state/minio-r2f.phase
r2_run r2g; : > /tmp/fake/dk/log
expect_ok "R2 control: rollback-a without m4a starts the old MinIO" bash "$PMOVE" "${M[@]}" --run-id r2g --confirm minio minio-rollback-a

# ---- eligibility table (unchanged rows)
RUN=e1; phase_of "attempt m0" "done m0" "attempt m3" "fail m3"
expect_ok "A allowed before any m4a attempt" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
RUN=e2; phase_of "attempt m4a 1" "done isolation_proven_pre 1 cid-1" "fail m4a 1"
expect_fail "no A when the isolation was not reconfirmed" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility
RUN=e3; phase_of "attempt m4a 1" "done isolation_proven_pre 1 cid-1" "done isolation_reconfirmed 1 cid-1" "attempt m4b"
expect_fail "no A once m4b was attempted" bash "$PMOVE" --state /state --run-id "$RUN" minio-eligibility

# ---- M2: base-check with large and failed listings
RUN=b1; phase_of "attempt m0"
mkdir -p "$D/bifrost-postgres-backup"
{ echo "# minio.base b1 30000 objects at 2026-11-03T00:00:00Z"; for i in $(seq 1 30000); do printf 'bifrost-postgres-backup/o%05d\n' "$i"; done; } > /state/minio-b1.base
expect_fail "M2: 30000 missing objects fail base-check" bash "$PMOVE" --state /state --run-id "$RUN" --data "$D" minio-base-check
{ echo "# minio.base b1 1 objects at 2026-11-03T00:00:00Z"; echo bifrost-postgres-backup/o1; } > /state/minio-b1.base
expect_fail "M2: one missing object fails base-check" bash "$PMOVE" --state /state --run-id "$RUN" --data "$D" minio-base-check
mkdir -p "$D/bifrost-postgres-backup/o1" && echo m > "$D/bifrost-postgres-backup/o1/xl.meta"
expect_ok "M2 control: all objects present pass base-check" bash "$PMOVE" --state /state --run-id "$RUN" --data "$D" minio-base-check
expect_fail "M2: a listing that fails (no bucket) fails base-check" bash "$PMOVE" --state /state --run-id "$RUN" --data /volume2/minio-backup/none minio-base-check
printf 'not a base file\n' > /state/minio-b1.base
expect_fail "M2: a base file without its header is refused" bash "$PMOVE" --state /state --run-id "$RUN" --data "$D" minio-base-check

# ---- continuity and the range hand-over (S3)
for s in 0000000100000005000000FE 0000000100000005000000FF 000000010000000600000000 000000010000000600000001; do
  mkdir -p "$D/bifrost-postgres-backup/bifrost-postgres/wals/${s:0:16}/$s.gz" && echo x > "$D/bifrost-postgres-backup/bifrost-postgres/wals/${s:0:16}/$s.gz/xl.meta"
done
RUN=r1; phase_of "attempt m0"
rng() { cat > /range <<EOF
L=${1:-0000000100000005000000FE}
U=${2:-000000010000000600000001}
SEGMENT_SIZE=${3:-16777216}
TIMELINE=00000001
WAL_PREFIX=bifrost-postgres-backup/bifrost-postgres/wals
SUFFIX=.gz
RP_NAME=td444-r1
RP_END=6/1000090
U_FROM_RP=000000010000000600000001
SWITCH_RETURN=6/2000000
PRIMARY=bifrost-postgres-1
TIMELINE_ID=1
STATS_RESET=2026-10-01T00:00:00Z
COLLECTED_AT=2026-11-03T20:00:00Z
EOF
}
rng
expect_ok "continuity across a log boundary (FE, FF, 00, 01)" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
check "S3: a passing check publishes the range list" test -s /state/minio-r1.range-list
sed -i '/^RP_NAME=/d' /range
expect_fail "S3: a range file without the RP evidence is refused" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
rng 0000000100000005000000FE 000000010000000600000001 10000000
expect_fail "S3: a segment size that is not a power of two is refused" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
rng 000000010000000500000100
expect_fail "S3: a segment number past the log is refused" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
rng
rm -rf "$D/bifrost-postgres-backup/bifrost-postgres/wals/0000000100000006/000000010000000600000000.gz"
rm -f /state/minio-r1.range-list
expect_fail "continuity catches a missing segment" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
check "S3: a failed check leaves no range list" test ! -e /state/minio-r1.range-list
{ echo "# minio.base r1 1 objects at 2026-11-03T00:00:00Z"; echo bifrost-postgres-backup/none; } > /state/minio-r1.base
printf 'bifrost-postgres-backup/x\n' > /state/minio-r1.range-list
dk_reset
expect_fail "S3: read-back refuses a range list no passing check produced" bash "$PMOVE" "${M[@]}" --run-id "$RUN" --range /range --confirm minio minio-readback
rng 0000000100000005000000FE 000000020000000600000001
expect_fail "continuity refuses a timeline change" bash "$PMOVE" --state /state --run-id "$RUN" --range /range --data "$D" minio-continuity
finish
