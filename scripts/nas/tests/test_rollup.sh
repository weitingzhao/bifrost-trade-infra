#!/usr/bin/env bash
# backup-rollup/rollup.sh (runbook §5.1): publish, link-dest, retention, failures.
# Regression tests of the implementation review: M5, S2, S4, S5. Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
K=/volume2/k3s-fast
mkdir -p "$K" /volume2/minio-backup /volume1
printf '%s\n' "$K" /volume2/minio-backup > /tmp/fake/subvols

# ---- fixtures
B1=$K/rs-b1
mkdir -p "$B1/daily/2026-11-01T043000Z"
(cd "$B1/daily/2026-11-01T043000Z" && echo dump > a.dump && sha256sum a.dump > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"
cs_fixture() { # cs_fixture <dir> <daily 1|0>
  mkdir -p "$1"
  (cd "$1"
   for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do echo "$f" > "$f"; done
   { echo "timestamp 2026-11-01T05:15:00Z"
     for f in etcd-snapshot-x.age secrets.yaml.age platform-state.yaml.age server-token.age; do
       echo "file $f ciphertext_bytes $(stat -c %s "$f") ciphertext_sha256 $(sha256sum "$f" | cut -d' ' -f1)"; done; } > MANIFEST
   if [[ $2 == 1 ]]; then echo OK > STATUS; fi)
}
B3=$K/rs-b3; cs_fixture "$B3/daily/2026-11-01" 1; cs_fixture "$B3/monthly/2026-11" 0
blob() { # blob <v2 root> <content>: prints the digest
  local h; h=$(printf '%s' "$2" | sha256sum | cut -d' ' -f1)
  mkdir -p "$1/blobs/sha256/${h:0:2}/$h" && printf '%s' "$2" > "$1/blobs/sha256/${h:0:2}/$h/data"; echo "sha256:$h"
}
REG=$K/rs-reg; V2=$REG/docker/registry/v2
layer=$(blob "$V2" layer-bytes); config=$(blob "$V2" config-bytes)
man=$(blob "$V2" "{\"config\":{\"digest\":\"$config\"},\"layers\":[{\"digest\":\"$layer\"}]}")
mkdir -p "$V2/repositories/app/_manifests/tags/v1/current" "$V2/repositories/app/_manifests/revisions/sha256/${man#sha256:}"
echo -n "$man" > "$V2/repositories/app/_manifests/tags/v1/current/link"
echo -n "$man" > "$V2/repositories/app/_manifests/revisions/sha256/${man#sha256:}/link"
for d in "$layer" "$config"; do mkdir -p "$V2/repositories/app/_layers/sha256/${d#sha256:}"; echo -n "$d" > "$V2/repositories/app/_layers/sha256/${d#sha256:}/link"; done
MIN=/volume2/minio-backup/rs-data; W=$MIN/bifrost-postgres-backup/bifrost-postgres
mkdir -p "$W/base/20261101T030000/backup.info" && printf 'begin_wal=0000000100000005000000FE\nstatus=DONE\n' > "$W/base/20261101T030000/backup.info/xl.meta"
touch -d '2 days ago' "$W/base/20261101T030000"
for s in 0000000100000005000000FE 0000000100000005000000FF 000000010000000600000000; do
  mkdir -p "$W/wals/${s:0:16}/$s.gz" && echo x > "$W/wals/${s:0:16}/$s.gz/xl.meta"
done
conf() { printf '%s\n' "$@" > /rollup.conf; }
conf "logical-backup-hot logical $B1 $K on" "cluster-state-backup cluster-state $B3 $K off" "registry-data registry $REG $K off" \
     "minio minio $MIN /volume2/minio-backup off"
# the container has no separate /volume1 and /volume2 mounts: both sit on /
R=(--conf /rollup.conf --dest /volume1/backup-weekly --dest-mount / --src-mount / --state /rstate --textfile /tf/backup-rollup.prom --keep 1 --now)
committed() { local g; for g in /volume1/backup-weekly/"$1"/*T*Z; do [[ -e $g && -f /volume1/backup-weekly/.committed/${g##*/} ]] && echo "${g##*/}"; done; return 0; }
gens() { committed "$1" | wc -l | tr -d ' '; }
succ() { cat "/rstate/last_success.$1" 2> /dev/null || echo none; }
gname() { committed "$1" | tr '\n' ' '; }

# ---- happy path (controls)
expect_ok "roll-up publishes a generation of four complete sources" bash "$ROLL" "${R[@]}"
check "GENERATION.json written" bash -c 'ls /volume1/backup-weekly/minio/*/GENERATION.json > /dev/null'
check "metrics written" grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="registry-data"} 1' /tf/backup-rollup.prom
check "snapshots of a good run are removed" bash -c '[[ -z $(ls -A /volume2/k3s-fast/@bifrost/rollup-snap 2>/dev/null) ]]'
sleep 1
expect_ok "a second generation" bash "$ROLL" "${R[@]}"
check "prune off keeps both generations" test "$(gens cluster-state-backup)" = 2
mapfile -t c < <(committed cluster-state-backup | sed 's#^#/volume1/backup-weekly/cluster-state-backup/#')
check "unchanged files are hard links (--link-dest)" test "$(stat -c %i "${c[0]}/daily/2026-11-01/MANIFEST")" = "$(stat -c %i "${c[1]}/daily/2026-11-01/MANIFEST")"
check "prune on with --keep 1 keeps only the newest" test "$(gens logical-backup-hot)" = 1

# ---- M5: incomplete sources are never published and never trigger retention
neg() { # neg <name> <source> : run, expect failure, nothing published, success time unchanged, no prune
  local before_g before_s before_l
  before_g=$(gens "$2"); before_s=$(succ "$2"); before_l=$(gname logical-backup-hot)
  expect_fail "M5: $1 fails the run" bash "$ROLL" "${R[@]}"
  check "M5: $1 — nothing published" test "$(gens "$2")" = "$before_g"
  check "M5: $1 — last-success unchanged" test "$(succ "$2")" = "$before_s"
  check "M5: $1 — the prune-on source kept its generation" test "$(gname logical-backup-hot)" = "$before_l"
}
sleep 1
mv "$B3" "$B3.keep"; mkdir -p "$B3"
neg "an empty cluster-state source" cluster-state-backup
rm -rf "$B3"; mv "$B3.keep" "$B3"
cp "$B3/monthly/2026-11/MANIFEST" /tmp/m.keep; sed -i '/^file /d' "$B3/monthly/2026-11/MANIFEST"
neg "a monthly MANIFEST without file lines" cluster-state-backup
cp /tmp/m.keep "$B3/monthly/2026-11/MANIFEST"
sed -i '/secrets.yaml.age/d' "$B3/daily/2026-11-01/MANIFEST"
neg "a daily MANIFEST that leaves one ciphertext out" cluster-state-backup
cs_fixture "$B3/daily/2026-11-01" 1
mv "$REG" "$REG.keep"; mkdir -p "$REG"
neg "an empty registry source" registry-data
rm -rf "$REG"; mv "$REG.keep" "$REG"
rm -rf "$V2/repositories/app/_layers/sha256/${layer#sha256:}"
neg "a registry tag whose layer link is missing" registry-data
mkdir -p "$V2/repositories/app/_layers/sha256/${layer#sha256:}"; echo -n "$layer" > "$V2/repositories/app/_layers/sha256/${layer#sha256:}/link"
mv "$W/wals" /tmp/wals.keep
neg "a DONE base backup without any WAL" minio
mv /tmp/wals.keep "$W/wals"
rm -rf "$W/wals/0000000100000005/0000000100000005000000FF.gz"
neg "a WAL gap after the base backup" minio
mkdir -p "$W/wals/0000000100000005/0000000100000005000000FF.gz" && echo x > "$W/wals/0000000100000005/0000000100000005000000FF.gz/xl.meta"
sleep 1
expect_ok "M5 control: the repaired sources publish again" bash "$ROLL" "${R[@]}"

# ---- in progress / not OK (unchanged rules)
mkdir "$B1/daily/.partial-2026-11-08T043000Z"
neg "a backup in progress (--now)" registry-data
check "failed run reports last_run_ok 0" grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="registry-data"} 0' /tf/backup-rollup.prom
rmdir "$B1/daily/.partial-2026-11-08T043000Z"

# ---- S5: a stale run.state stops the run before anything is cleaned
echo "snapshot /volume2/k3s-fast/@bifrost/rollup-snap/keep-me" > /rstate/run.state
mkdir -p /volume2/k3s-fast/@bifrost/rollup-snap/keep-me
expect_fail "S5: a leftover run.state stops the run" bash "$ROLL" "${R[@]}"
check "S5: the leftover run.state is untouched" grep -q keep-me /rstate/run.state
check "S5: the snapshot it names is untouched" test -d /volume2/k3s-fast/@bifrost/rollup-snap/keep-me
rm -rf /rstate/run.state /volume2/k3s-fast/@bifrost/rollup-snap/keep-me
# ---- S5: a publish that stops half way is not a generation
sleep 1
before=$(gens minio); before_s=$(succ minio)
expect_fail "S5: a publish interrupted after the first source fails" env ROLLUP_TEST_FAIL_PUBLISH_AFTER=1 bash "$ROLL" "${R[@]}"
check "S5: no generation counts as published" test "$(gens minio)" = "$before"
check "S5: last-success unchanged after a half publish" test "$(succ minio)" = "$before_s"
# ---- S5: a snapshot that cannot be deleted is remembered
sleep 1
touch /tmp/fake/btrfs_delete_fail
bash "$ROLL" "${R[@]}" > /tmp/out 2>&1 || true
rm -f /tmp/fake/btrfs_delete_fail
check "S5: a failed snapshot delete is kept for the next run" test -s /rstate/pending-cleanup.list
sleep 1
expect_ok "S5 control: the next run cleans what was left" bash "$ROLL" "${R[@]}"
check "S5 control: nothing is pending any more" test ! -s /rstate/pending-cleanup.list

# ---- S4: a source that leaves rollup.conf keeps alerting
conf "logical-backup-hot logical $B1 $K on" "cluster-state-backup cluster-state $B3 $K off" "registry-data registry $REG $K off"
sleep 1
bash "$ROLL" "${R[@]}" > /tmp/out 2>&1 || true
check "S4: a source removed from the config is still expected" grep -q 'bifrost_nas_backup_rollup_source_expected{source="minio"} 1' /tf/backup-rollup.prom
check "S4: and has no success time any more" bash -c '! grep -q "last_success_timestamp_seconds{source=\"minio\"}" /tf/backup-rollup.prom'

# ---- S2: config paths
conf "a logical $K/rs-b1 $K off" "b logical $K/rs-b1/daily $K off"
expect_fail "S2: overlapping sources are refused" bash "$ROLL" "${R[@]}"
conf "a logical /volume1/backup-weekly/x /volume1 off"
expect_fail "S2: a source inside the destination is refused" bash "$ROLL" "${R[@]}"
mkdir -p "$K/rs-sub"; cp -a "$B1/." "$K/rs-sub/"; echo "$K/rs-sub" >> /tmp/fake/subvols
conf "a logical $K/rs-sub $K off"
expect_fail "S2: a source that is itself a nested subvolume is refused" bash "$ROLL" "${R[@]}"
finish
