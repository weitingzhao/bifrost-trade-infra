#!/usr/bin/env bash
# backup-rollup/rollup.sh (runbook §5.1): publish, link-dest, retention, failures.
# Regression tests of the implementation review: M5, S2, S4, S5; of the fix review: R3, R4,
# S2 (the publish failure comes from the mv shim of lib.sh, not from a switch in rollup.sh).
# Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
K=/volume2/k3s-fast
mkdir -p "$K" /volume2/minio-backup /volume1 /rconf
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
# registry: Distribution v2 storage with an image manifest, an OCI index with one child,
# and an untagged image whose digest is on the expected list
REG=$K/rs-reg; V2=$REG/docker/registry/v2
blob() { # blob <content>: prints the digest
  local h; h=$(printf '%s' "$1" | sha256sum | cut -d' ' -f1)
  mkdir -p "$V2/blobs/sha256/${h:0:2}/$h" && printf '%s' "$1" > "$V2/blobs/sha256/${h:0:2}/$h/data"; echo "sha256:$h"
}
bpath() { local h=${1#sha256:}; echo "$V2/blobs/sha256/${h:0:2}/$h"; }
lpath() { # lpath <repo> revision|layer <digest>
  case $2 in revision) echo "$V2/repositories/$1/_manifests/revisions/sha256/${3#sha256:}" ;; layer) echo "$V2/repositories/$1/_layers/sha256/${3#sha256:}" ;; esac
}
link() { local d; d=$(lpath "$@"); mkdir -p "$d" && printf '%s' "$3" > "$d/link"; }
tag() { mkdir -p "$V2/repositories/$1/_manifests/tags/$2/current" && printf '%s' "$3" > "$V2/repositories/$1/_manifests/tags/$2/current/link"; }
desc() { printf '{"mediaType":"%s","digest":"%s","size":%s}' "$1" "$2" "$(stat -c %s "$(bpath "$2")/data")"; }
DM=application/vnd.docker.distribution.manifest.v2+json OM=application/vnd.oci.image.manifest.v1+json OI=application/vnd.oci.image.index.v1+json
image() { # image <repo> <manifest media type> <name>: config + layer blobs and links, manifest + revision link
  local c l m
  c=$(blob "config-$3"); l=$(blob "layer-$3"); link "$1" layer "$c"; link "$1" layer "$l"
  m=$(blob "{\"schemaVersion\":2,\"mediaType\":\"$2\",\"config\":$(desc application/vnd.oci.image.config.v1+json "$c"),\"layers\":[$(desc application/vnd.oci.image.layer.v1.tar+gzip "$l")]}")
  link "$1" revision "$m"; echo "$m"
}
APP=$(image app "$DM" a); tag app v1 "$APP"
CHILD=$(image multi "$OM" m)
IDX=$(blob "{\"schemaVersion\":2,\"mediaType\":\"$OI\",\"manifests\":[$(desc "$OM" "$CHILD")]}"); link multi revision "$IDX"; tag multi latest "$IDX"
KEEP=$(image keep "$DM" k)
printf '%s\n' "# digests that must stay restorable" "app@$APP" "multi@$IDX" "keep@$KEEP" > /rconf/registry-data.digests
dg() { printf 'sha256:%s' "$(printf '%s' "$1" | sha256sum | cut -d' ' -f1)"; }
# MinIO: the fix review's counterexample, DONE text in backup.info and an empty WAL directory
MIN=/volume2/minio-backup/rs-data; W=$MIN/bifrost-postgres-backup/bifrost-postgres
mkdir -p "$W/base/20261101T030000/backup.info" && printf 'begin_wal=0000000100000005000000FE\nstatus=DONE\n' > "$W/base/20261101T030000/backup.info/xl.meta"
touch -d '2 days ago' "$W/base/20261101T030000"
mkdir -p "$W/wals/0000000100000005/0000000100000005000000FE.gz"

conf() { printf '%s\n' "$@" > /rconf/rollup.conf; }
BASE=("logical-backup-hot logical $B1 $K on" "cluster-state-backup cluster-state $B3 $K off" "registry-data registry $REG $K off")
conf "${BASE[@]}"
# the container has no separate /volume1 and /volume2 mounts: both sit on /
R=(--conf /rconf/rollup.conf --dest /volume1/backup-weekly --dest-mount / --src-mount / --state /rstate --textfile /tf/backup-rollup.prom --keep 1 --now)
committed() { local g; for g in /volume1/backup-weekly/"$1"/*T*Z; do [[ -e $g && -f /volume1/backup-weekly/.committed/${g##*/} ]] && echo "${g##*/}"; done; return 0; }
gens() { committed "$1" | wc -l | tr -d ' '; }
succ() { cat "/rstate/last_success.$1" 2> /dev/null || echo none; }
gname() { committed "$1" | tr '\n' ' '; }
markers() { find /volume1/backup-weekly/.committed -type f | wc -l | tr -d ' '; }

# ---- happy path (controls)
expect_ok "roll-up publishes a generation of three complete sources" bash "$ROLL" "${R[@]}"
check "GENERATION.json written" bash -c 'ls /volume1/backup-weekly/registry-data/*/GENERATION.json > /dev/null'
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
  sleep 1
  expect_fail "$1 fails the run" bash "$ROLL" "${R[@]}"
  check "$1 — nothing published" test "$(gens "$2")" = "$before_g"
  check "$1 — last-success unchanged" test "$(succ "$2")" = "$before_s"
  check "$1 — the prune-on source kept its generation" test "$(gname logical-backup-hot)" = "$before_l"
}
mv "$B3" "$B3.keep"; mkdir -p "$B3"
neg "M5: an empty cluster-state source" cluster-state-backup
rm -rf "$B3"; mv "$B3.keep" "$B3"
cp "$B3/monthly/2026-11/MANIFEST" /tmp/m.keep; sed -i '/^file /d' "$B3/monthly/2026-11/MANIFEST"
neg "M5: a monthly MANIFEST without file lines" cluster-state-backup
cp /tmp/m.keep "$B3/monthly/2026-11/MANIFEST"
sed -i '/secrets.yaml.age/d' "$B3/daily/2026-11-01/MANIFEST"
neg "M5: a daily MANIFEST that leaves one ciphertext out" cluster-state-backup
cs_fixture "$B3/daily/2026-11-01" 1
mv "$REG" "$REG.keep"; mkdir -p "$REG"
neg "M5: an empty registry source" registry-data
rm -rf "$REG"; mv "$REG.keep" "$REG"
rm -rf "$(lpath app layer "$(dg layer-a)")"
neg "M5: a registry tag whose layer link is missing" registry-data
link app layer "$(dg layer-a)"

# ---- R4: the registry graph is read as a pull reads it, from every expected digest and tag
mv "$(lpath multi revision "$CHILD")" /tmp/child-rev; link multi layer "$CHILD"; mv "$(bpath "$(dg config-m)")" /tmp/config-m
neg "R4: an index child with a layer link but no revision link, its config blob missing" registry-data
mv /tmp/child-rev "$(lpath multi revision "$CHILD")"; rm -rf "$(lpath multi layer "$CHILD")"; mv /tmp/config-m "$(bpath "$(dg config-m)")"
mv "$(bpath "$(dg layer-m)")" /tmp/layer-m
neg "R4: a grandchild blob of the index is missing" registry-data
mv /tmp/layer-m "$(bpath "$(dg layer-m)")"
BAD=$(blob "{\"schemaVersion\":2,\"mediaType\":\"$DM\",\"config\":$(desc application/vnd.oci.image.config.v1+json "$(dg config-a)"),\"layers\":[$(desc application/vnd.oci.image.layer.v1.tar+gzip "$(dg layer-a)")]")
link app revision "$BAD"; tag app broken "$BAD"
neg "R4: a tagged manifest that is not valid JSON" registry-data
rm -rf "$V2/repositories/app/_manifests/tags/broken"
rm -rf "$(lpath keep layer "$(dg layer-k)")"
neg "R4: an expected digest that lost its tag and its layer link" registry-data
link keep layer "$(dg layer-k)"
echo "app@sha256:$(printf '0%.0s' {1..64})" >> /rconf/registry-data.digests
neg "R4: an expected digest that is not in the registry" registry-data
sed -i '$d' /rconf/registry-data.digests
mv /rconf/registry-data.digests /tmp/digests.keep
neg "R4: a registry source without its expected digest list" registry-data
mv /tmp/digests.keep /rconf/registry-data.digests
expect_ok "R4 control: the index, its child and the untagged expected image publish" bash "$ROLL" "${R[@]}"

# ---- R3: no offline evidence proves MinIO objects complete, so a MinIO source never publishes
conf "${BASE[@]}" "minio minio $MIN /volume2/minio-backup off"
neg "R3: a MinIO source with only DONE text and an empty WAL directory" minio
for s in 0000000100000005000000FE 0000000100000005000000FF; do
  mkdir -p "$W/wals/${s:0:16}/$s.gz" && echo x > "$W/wals/${s:0:16}/$s.gz/xl.meta"
done
neg "R3: a MinIO source with WAL xl.meta files (still no object evidence)" minio
check "R3: the log names the missing object check" grep -q 'cannot be proven complete offline' /tmp/out
check "R3: the failed run kept the MinIO snapshot for diagnosis" grep -q ' snapshot .*/rollup-snap/minio-' /rstate/diag.list
conf "${BASE[@]}"
bash "$ROLL" "${R[@]}" --retire-source minio > /dev/null 2>&1
sleep 1
expect_ok "R3 control: without the MinIO source the others publish" bash "$ROLL" "${R[@]}"

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
# ---- S5: a publish that stops half way is not a generation (S2: injected by the mv shim)
check "S2: rollup.sh carries no test switch" bash -c "! grep -q ROLLUP_TEST '$ROLL'"
sleep 1
before=$(gens logical-backup-hot); before_s=$(succ logical-backup-hot); before_m=$(markers)
echo 2 > /tmp/fake/mv_fail_at; rm -f /tmp/fake/mv_count
expect_fail "S5: a publish whose second rename fails fails the run" bash "$ROLL" "${R[@]}"
rm -f /tmp/fake/mv_fail_at /tmp/fake/mv_count
check "S5: the first source was renamed" bash -c "(( \$(ls -d /volume1/backup-weekly/logical-backup-hot/*T*Z | wc -l) > $before ))"
check "S5: but no generation counts as published" test "$(gens logical-backup-hot)" = "$before"
check "S5: no commit marker was written" test "$(markers)" = "$before_m"
check "S5: last-success unchanged after a half publish" test "$(succ logical-backup-hot)" = "$before_s"
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
conf "logical-backup-hot logical $B1 $K on" "registry-data registry $REG $K off"
sleep 1
bash "$ROLL" "${R[@]}" > /tmp/out 2>&1 || true
check "S4: a source removed from the config is still expected" grep -q 'bifrost_nas_backup_rollup_source_expected{source="cluster-state-backup"} 1' /tf/backup-rollup.prom
check "S4: and has no success time any more" bash -c '! grep -q "last_success_timestamp_seconds{source=\"cluster-state-backup\"}" /tf/backup-rollup.prom'

# ---- S2: config paths
conf "a logical $K/rs-b1 $K off" "b logical $K/rs-b1/daily $K off"
expect_fail "S2: overlapping sources are refused" bash "$ROLL" "${R[@]}"
conf "a logical /volume1/backup-weekly/x /volume1 off"
expect_fail "S2: a source inside the destination is refused" bash "$ROLL" "${R[@]}"
mkdir -p "$K/rs-sub"; cp -a "$B1/." "$K/rs-sub/"; echo "$K/rs-sub" >> /tmp/fake/subvols
conf "a logical $K/rs-sub $K off"
expect_fail "S2: a source that is itself a nested subvolume is refused" bash "$ROLL" "${R[@]}"
finish
