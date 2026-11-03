#!/usr/bin/env bash
# Functional tests of td444-move.sh and backup-rollup/rollup.sh (TD-444 step 5 runbook §3.3, §4, §5.1).
#
# Run from the repository root (needs docker; nothing touches the host):
#   bash scripts/nas/test_nas_scripts.sh
# It starts debian:12 (the NAS runs UGOS on Debian 12), installs rsync, acl, attr and
# util-linux, replaces btrfs (snapshot = copy) and exportfs with shims, fakes the SSD
# hwmon tree, builds /volume1 and /volume2 inside the container and drives both scripts.
set -euo pipefail
if [[ ${1:-} != --inside ]]; then
  root=$(cd "$(dirname "$0")/../.." && pwd)
  exec docker run --rm -v "$root/scripts/nas:/src:ro" debian:12 bash /src/test_nas_scripts.sh --inside
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq > /dev/null && apt-get install -y -qq rsync acl attr util-linux bsdutils > /dev/null
pass=0 fail=0
ok() { pass=$((pass + 1)); echo "PASS: $*"; }
bad() { fail=$((fail + 1)); echo "FAIL: $*"; }
expect_ok() { local d=$1; shift; if "$@" > /tmp/out 2>&1; then ok "$d"; else bad "$d"; tail -20 /tmp/out; fi; }
expect_fail() { local d=$1; shift; if "$@" > /tmp/out 2>&1; then bad "$d (succeeded)"; tail -20 /tmp/out; else ok "$d"; fi; }

# ---- shims
mkdir -p /shim
cat > /shim/btrfs <<'EOF'
#!/bin/bash
case "$1 $2" in
  "subvolume show") [[ -d $3 ]] ;;
  "subvolume snapshot") shift 2; [[ $1 == -r ]] && shift; cp -a "$1" "$2" ;;
  "subvolume delete") rm -rf "$3" ;;
  "inspect-internal rootid") echo 5 ;;
  *) echo "shim btrfs: $*" >&2; exit 1 ;;
esac
EOF
cat > /shim/exportfs <<'EOF'
#!/bin/bash
cat /tmp/exports.txt
EOF
chmod +x /shim/*
export PATH=/shim:$PATH
mkdir -p /hwmon/hwmon0 && echo nvme > /hwmon/hwmon0/name && echo 50000 > /hwmon/hwmon0/temp1_input
export TD444_HWMON=/hwmon

MOVE=/src/td444-move.sh ROLL=/src/backup-rollup/rollup.sh
mkdir -p /volume1/k3s-hot /volume1/k3s-cold /volume2/k3s-fast /volume2/minio-backup /volume2/market-archive-backup /pkg/k8s/data/minio/nas
echo pkg > /pkg/k8s/data/minio/nas/compose.yaml
(cd /pkg && find . -type f -exec sha256sum {} + > /sums)

# ---- fixtures: a logical backup (B1), a gitea backup (B2), a cluster-state backup (B3)
B1=/volume1/k3s-hot/old-b1
mkdir -p "$B1/daily/2026-11-01T043000Z" "$B1/drills"
(cd "$B1/daily/2026-11-01T043000Z" && echo dump > a.dump && echo m > manifest.tsv && echo e > extensions.tsv && sha256sum a.dump manifest.tsv extensions.tsv > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"
B2=/volume1/k3s-cold/old-b2
mkdir -p "$B2/2026-11-01T031000Z"
(cd "$B2/2026-11-01T031000Z" && echo c1 > data.tar.age && echo c2 > MANIFEST.tsv.age && sha256sum data.tar.age MANIFEST.tsv.age > SHA256SUMS && echo '# plaintext_sha256 data.tar abc' >> SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T031000Z > "$B2/LATEST"
B3=/volume1/k3s-cold/old-b3
cs_run() { # cs_run <dir> <with STATUS 0|1>
  mkdir -p "$1"
  (cd "$1"
   for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do echo "$f" > "$f"; done
   { echo "timestamp 2026-11-01T05:15:00Z"
     for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do
       echo "file $f ciphertext_bytes $(stat -c %s "$f") ciphertext_sha256 $(sha256sum "$f" | cut -d' ' -f1)"; done; } > MANIFEST
   if [[ $2 == 1 ]]; then echo OK > STATUS; fi)
}
cs_run "$B3/daily/2026-11-01" 1
cs_run "$B3/monthly/2026-11" 0

cat > /map <<EOF
daily B1 logical /volume1/k3s-hot/old-b1 /volume2/k3s-fast/data-logical-backup-hot
daily B2 gitea /volume1/k3s-cold/old-b2 /volume2/k3s-fast/cicd-gitea-backup
daily B3 cluster-state /volume1/k3s-cold/old-b3 /volume2/k3s-fast/kube-system-cluster-state-backup /volume1/k3s-cold
EOF
G=(--state /state --map /map --pkg /pkg --sums /sums)

# ---- map and confirm guards
printf 'daily B9 plain /etc /volume2/k3s-fast/x\n' > /badmap
expect_fail "a source outside the allowed roots is refused" bash "$MOVE" --state /state --map /badmap identity-check daily
printf 'daily B9 plain /volume1/k3s-hot/a /volume1/k3s-hot/a/b\n' > /badmap
expect_fail "overlapping source and target are refused" bash "$MOVE" --state /state --map /badmap identity-check daily
expect_fail "pre without --confirm is refused" bash "$MOVE" "${G[@]}" pre daily
expect_fail "pre with the wrong --confirm is refused" bash "$MOVE" "${G[@]}" --confirm reg pre daily

# ---- identity, pre, final, verify
expect_ok "identity-record" bash "$MOVE" "${G[@]}" --confirm daily identity-record daily
expect_ok "identity-check matches" bash "$MOVE" "${G[@]}" identity-check daily
expect_ok "pre copies (add only)" bash "$MOVE" "${G[@]}" --confirm daily pre daily
echo extra > /volume2/k3s-fast/data-logical-backup-hot/stale-file
expect_fail "final without a typed yes stops" script -qec "bash $MOVE ${G[*]} --confirm daily final daily" /dev/null < <(echo no)
expect_ok "final with yes deletes, copies and verifies" script -qec "bash $MOVE ${G[*]} --confirm daily final daily" /dev/null < <(printf 'yes\nyes\nyes\n')
[[ ! -e /volume2/k3s-fast/data-logical-backup-hot/stale-file ]] && ok "final removed the file the source does not have" || bad "stale file survived final"
expect_ok "verify passes on identical trees" bash "$MOVE" "${G[@]}" verify daily
f=/volume2/k3s-fast/data-logical-backup-hot/drills/x; mkdir -p "$(dirname "$f")"
cp -p /volume2/k3s-fast/data-logical-backup-hot/LATEST /volume1/k3s-hot/old-b1/drills/x
cp -p /volume1/k3s-hot/old-b1/drills/x "$f"
printf '2026-11-01T043000X\n' > "$f.new"; touch -r "$f" "$f.new"; mv "$f.new" "$f"
expect_fail "verify catches same size, same mtime, other content (-c)" bash "$MOVE" "${G[@]}" verify daily
cp -p /volume1/k3s-hot/old-b1/drills/x "$f"
echo OK > /volume2/k3s-fast/kube-system-cluster-state-backup/monthly/2026-11/STATUS
expect_fail "a monthly cluster-state run with a STATUS file is an unexpected file set" bash "$MOVE" "${G[@]}" verify daily
rm /volume2/k3s-fast/kube-system-cluster-state-backup/monthly/2026-11/STATUS
touch -r /volume1/k3s-cold/old-b3/monthly/2026-11 /volume2/k3s-fast/kube-system-cluster-state-backup/monthly/2026-11
echo tampered > /volume2/k3s-fast/cicd-gitea-backup/2026-11-01T031000Z/data.tar.age
expect_fail "gitea SHA256SUMS catch a changed ciphertext" bash "$MOVE" "${G[@]}" verify daily
cp -p /volume1/k3s-cold/old-b2/2026-11-01T031000Z/data.tar.age /volume2/k3s-fast/cicd-gitea-backup/2026-11-01T031000Z/
expect_ok "verify passes again after repair" bash "$MOVE" "${G[@]}" verify daily
echo 97 > /tmp/disk && mv /state/identity/daily.rec /state/identity/daily.rec.keep && sed 's/ rw / ro /' /state/identity/daily.rec.keep > /state/identity/daily.rec
expect_fail "identity-check stops when the recorded identity differs" bash "$MOVE" "${G[@]}" identity-check daily
mv /state/identity/daily.rec.keep /state/identity/daily.rec

# ---- temperature guard
head -c 3000000 /dev/urandom > /volume1/k3s-hot/old-b1/big.bin
echo 80000 > /hwmon/hwmon0/temp1_input
( sleep 12; echo 60000 > /hwmon/hwmon0/temp1_input ) &
expect_ok "pre pauses at 72 °C and resumes at 65 °C" bash "$MOVE" "${G[@]}" --confirm daily --temp-poll 2 --bwlimit 200K pre daily
grep -q 'copy paused' /tmp/out && grep -q 'copy resumed' /tmp/out && ok "pause and resume were logged" || { bad "no pause/resume in the log"; tail -20 /tmp/out; }
rm -f /hwmon/hwmon0/temp1_input
head -c 3000000 /dev/urandom > /volume1/k3s-hot/old-b1/big2.bin
expect_ok "a missing temperature pauses after --temp-missing" bash -c "( sleep 9; echo 50000 > /hwmon/hwmon0/temp1_input ) & bash $MOVE ${G[*]} --confirm daily --temp-poll 1 --temp-missing 3 --bwlimit 200K pre daily"
grep -q 'no SSD temperature' /tmp/out && ok "missing temperature was logged" || bad "missing temperature not logged"
head -c 3000000 /dev/urandom > /volume1/k3s-hot/old-b1/big3.bin
expect_fail "--timeout stops a long copy" bash "$MOVE" "${G[@]}" --confirm daily --timeout 2 --bwlimit 10K --temp-poll 1 pre daily
rm -f /volume1/k3s-hot/old-b1/big*.bin

# ---- exports
cat > /tmp/exports.txt <<'EOF'
/volume1/k3s-hot
		10.0.0.0/24(sync,wdelay,hide,no_subtree_check,anonuid=1000,anongid=100,sec=sys,rw,secure,all_squash)
/volume2/k3s-fast
		10.0.0.0/24(rw,sync,wdelay,hide,no_subtree_check,sec=sys,secure,all_squash,anonuid=1000,anongid=100)
/volume2/market-archive-backup	10.0.0.0/24(sync,wdelay,hide,no_subtree_check,anonuid=1000,anongid=100,sec=sys,rw,secure,all_squash)
EOF
chmod 755 /volume1/k3s-hot /volume2/k3s-fast /volume2/market-archive-backup
expect_ok "exports with the same options in another order match" bash "$MOVE" --state /state exports
sed -i 's/anonuid=1000,anongid=100,sec=sys,rw,secure,all_squash)$/anonuid=1000,anongid=100,sec=sys,rw,secure,root_squash)/' /tmp/exports.txt
expect_fail "a different squash option is caught" bash "$MOVE" --state /state exports

# ---- MinIO continuity and eligibility
D=/volume2/minio-backup/data
for s in 0000000100000005000000FE 0000000100000005000000FF 000000010000000600000000 000000010000000600000001; do
  mkdir -p "$D/bifrost-postgres-backup/bifrost-postgres/wals/${s:0:16}/$s.gz" && echo x > "$D/bifrost-postgres-backup/bifrost-postgres/wals/${s:0:16}/$s.gz/xl.meta"
done
mkdir -p /state && printf '%s attempt m0\n' t > /state/minio-r1.phase
printf 'L=0000000100000005000000FE\nU=000000010000000600000001\nSEGMENT_SIZE=16777216\nTIMELINE=00000001\nWAL_PREFIX=bifrost-postgres-backup/bifrost-postgres/wals\nSUFFIX=.gz\n' > /range
expect_ok "continuity across a log boundary (FE, FF, 00, 01)" bash "$MOVE" --state /state --run-id r1 --range /range --data "$D" minio-continuity
rm -rf "$D/bifrost-postgres-backup/bifrost-postgres/wals/0000000100000006/000000010000000600000000.gz"
expect_fail "continuity catches a missing segment" bash "$MOVE" --state /state --run-id r1 --range /range --data "$D" minio-continuity
sed -i 's/^U=00000001/U=00000002/' /range
expect_fail "continuity refuses a timeline change" bash "$MOVE" --state /state --run-id r1 --range /range --data "$D" minio-continuity
elig() { printf '%s\n' "$@" | sed 's/^/t /' > /state/minio-e.phase; bash "$MOVE" --state /state --run-id e minio-eligibility; }
expect_ok "A allowed before any m4a attempt" elig "attempt m0" "done m0" "attempt m3" "fail m3"
expect_ok "A allowed with both isolation proofs and no m4b" elig "attempt m4a" "done isolation_proven_pre" "done m4a" "done isolation_reconfirmed"
expect_fail "no A when the isolation was not reconfirmed" elig "attempt m4a" "done isolation_proven_pre" "fail m4a"
expect_fail "no A once m4b was attempted" elig "attempt m4a" "done isolation_proven_pre" "done isolation_reconfirmed" "attempt m4b"

# ---- weekly roll-up
mkdir -p /volume2/k3s-fast/rollsrc-b1 /volume2/k3s-fast/rollsrc-b3 /volume2/k3s-fast/rollsrc-reg/docker/registry/v2/blobs/sha256/ab
cp -a "$B1/." /volume2/k3s-fast/rollsrc-b1/
cp -a "$B3/." /volume2/k3s-fast/rollsrc-b3/
blob=$(printf 'layer' | sha256sum | cut -d' ' -f1)
mkdir -p "/volume2/k3s-fast/rollsrc-reg/docker/registry/v2/blobs/sha256/${blob:0:2}/$blob" && printf 'layer' > "/volume2/k3s-fast/rollsrc-reg/docker/registry/v2/blobs/sha256/${blob:0:2}/$blob/data"
rm -rf /volume2/k3s-fast/rollsrc-reg/docker/registry/v2/blobs/sha256/ab
cat > /rollup.conf <<'EOF'
logical-backup-hot   logical        /volume2/k3s-fast/rollsrc-b1   /volume2/k3s-fast  on
cluster-state-backup cluster-state  /volume2/k3s-fast/rollsrc-b3   /volume2/k3s-fast  off
registry-data        registry       /volume2/k3s-fast/rollsrc-reg  /volume2/k3s-fast  off
EOF
R=(--conf /rollup.conf --dest /volume1/backup-weekly --state /rstate --textfile /tf/backup-rollup.prom --keep 1 --now)
expect_ok "roll-up publishes a generation" bash "$ROLL" "${R[@]}"
g1=$(ls /volume1/backup-weekly/logical-backup-hot | head -1)
[[ -f /volume1/backup-weekly/logical-backup-hot/$g1/GENERATION.json ]] && ok "GENERATION.json written" || bad "no GENERATION.json"
grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="registry-data"} 1' /tf/backup-rollup.prom && ok "metrics written" || bad "metrics missing"
[[ -z $(ls -A /volume2/k3s-fast/@bifrost/rollup-snap 2>/dev/null) ]] && ok "snapshots of a good run are removed" || bad "snapshots left behind"
sleep 1
expect_ok "a second generation" bash "$ROLL" "${R[@]}"
mapfile -t gens < <(ls /volume1/backup-weekly/cluster-state-backup)
((${#gens[@]} == 2)) && ok "prune off keeps both generations" || bad "prune off removed a generation"
[[ $(stat -c %i "/volume1/backup-weekly/cluster-state-backup/${gens[0]}/daily/2026-11-01/MANIFEST") == $(stat -c %i "/volume1/backup-weekly/cluster-state-backup/${gens[1]}/daily/2026-11-01/MANIFEST") ]] \
  && ok "unchanged files are hard links (--link-dest)" || bad "no hard links between generations"
gl=(/volume1/backup-weekly/logical-backup-hot/*T*Z); ((${#gl[@]} == 1)) && ok "prune on with --keep 1 keeps only the newest" || bad "prune did not remove the older generation"
mkdir /volume2/k3s-fast/rollsrc-b1/daily/.partial-2026-11-08T043000Z
before=$(ls /volume1/backup-weekly/registry-data | wc -l)
expect_fail "a backup in progress fails the run (--now)" bash "$ROLL" "${R[@]}"
gr=(/volume1/backup-weekly/registry-data/*T*Z); ((${#gr[@]} == before)) && ok "a failed run publishes nothing" || bad "a failed run published"
grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="registry-data"} 0' /tf/backup-rollup.prom && ok "failed run reports last_run_ok 0" || bad "last_run_ok not 0"
rmdir /volume2/k3s-fast/rollsrc-b1/daily/.partial-2026-11-08T043000Z
echo PARTIAL > /volume2/k3s-fast/rollsrc-b1/daily/2026-11-01T043000Z/STATUS
expect_fail "a LATEST run that is not STATUS=OK fails the source" bash "$ROLL" "${R[@]}"

echo
echo "passed $pass, failed $fail"
((fail == 0))
