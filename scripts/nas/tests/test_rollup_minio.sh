#!/usr/bin/env bash
# backup-rollup/rollup.sh with a MinIO source (runbook §3.8 item 2, option A): the objects are
# read back through a throwaway MinIO (the docker and mc doubles of lib.sh). A generation
# publishes only when everything due reads back; the throwaway container and its scratch copy
# are gone after success and after failure; the live MinIO is never touched; the credentials
# reach no log. Also the fix review's R3 counterexamples and round 4's M1, S1, S2.
# Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
K=/volume2/k3s-fast
mkdir -p "$K" /volume2/minio-backup /volume1 /rconf
printf '%s\n' "$K" /volume2/minio-backup > /tmp/fake/subvols

# ---- fixtures: a small logical source (prune on) and the MinIO data directory (two servers)
B1=$K/rs-b1
mkdir -p "$B1/daily/2026-11-01T043000Z"
(cd "$B1/daily/2026-11-01T043000Z" && echo dump > a.dump && sha256sum a.dump > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"
MIN=/volume2/minio-backup/data; P=bifrost-postgres-backup/bifrost-postgres; Q=bifrost-postgres-backup/other; W=$MIN/$P
obj() { mkdir -p "$MIN/$1" && printf '%s' "${2:-x}" > "$MIN/$1/xl.meta"; }   # fixture xl.meta = the object's plain content
objtar() { # objtar <object> <member>...: the object is a gzip tar of these members, in this order
  local st; st=$(mktemp -d)
  (cd "$st" && for m in "${@:2}"; do mkdir -p "$(dirname "$m")"; echo "$m" > "$m"; done && tar -czf "$st.tgz" "${@:2}")
  mkdir -p "$MIN/$1" && cp "$st.tgz" "$MIN/$1/xl.meta"; rm -rf "$st" "$st.tgz"
}
info() { printf "backup_label=%s\nbegin_wal=%s\nend_wal=%s\nstatus=%s\ntablespaces=None\n" "${4:-'START WAL LOCATION: 5/FE000028'}" "$1" "$2" "$3"; }
obj "$P/base/20261031T210000/backup.info" "$(info 0000000100000005000000F0 0000000100000005000000F0 DONE)"
objtar "$P/base/20261031T210000/data.tar.gz" global/pg_control backup_label
obj "$P/base/20261101T210000/backup.info" "$(info 0000000100000005000000FE 0000000100000005000000FE DONE)"
objtar "$P/base/20261101T210000/data.tar.gz" PG_VERSION global/pg_control
objtar "$P/base/20261101T210000/data_0001.tar.gz" backup_label
obj "$P/base/20261102T210000/backup.info" "$(info 000000010000000600000000 000000010000000600000000 FAILED)"
objtar "$P/base/20261103T210000/data.tar.gz" PG_VERSION          # unfinished: no backup.info
for s in 0000000100000005000000FE 0000000100000005000000FF 000000010000000600000000; do obj "$P/wals/${s:0:16}/$s.gz"; done
obj "$Q/base/20261101T200000/backup.info" "$(info 000000010000000300000010 000000010000000300000010 DONE)"
objtar "$Q/base/20261101T200000/data.tar.gz" global/pg_control backup_label
obj "$Q/wals/0000000100000003/000000010000000300000010.gz"
obj ".minio.sys/config/config.json"
touch -d '2 days ago' "$MIN"/*/*/base/*
# the live MinIO (td444 record of the docker double): it must stay running and unnamed
mkdir -p /tmp/fake/dk && echo 1 > /tmp/fake/dk/exists && echo true > /tmp/fake/dk/running && echo cid-live > /tmp/fake/dk/id
SECRET=Pw-9f3c-SECRET-77
creds() { printf 'MINIO_ROOT_USER=rollup-admin\nMINIO_ROOT_PASSWORD=%s\n' "${1:-$SECRET}" > /rconf/minio.env; chmod "${2:-600}" /rconf/minio.env; }
creds
IMG=sha256:$(printf 'b%.0s' {1..64})
conf() { printf '%s\n' "MINIO_IMAGE=${1:-$IMG}" "MINIO_CREDENTIALS=/rconf/minio.env" \
  "logical-backup-hot logical $B1 $K on" "minio minio $MIN /volume2/minio-backup off" > /rconf/rollup.conf; }
conf
R=(--conf /rconf/rollup.conf --dest /volume1/backup-weekly --dest-mount / --src-mount / --state /rstate
   --textfile /tf/backup-rollup.prom --keep 1 --now --minio-start-timeout 4)
committed() { local g; for g in /volume1/backup-weekly/"$1"/*T*Z; do [[ -e $g && -f /volume1/backup-weekly/.committed/${g##*/} ]] && echo "${g##*/}"; done; return 0; }
gens() { committed "$1" | wc -l | tr -d ' '; }
succ() { cat "/rstate/last_success.$1" 2> /dev/null || echo none; }
gname() { committed "$1" | tr '\n' ' '; }
markers() { find /volume1/backup-weekly/.committed -type f 2> /dev/null | wc -l | tr -d ' '; }
runs() { grep -c '^docker run ' /tmp/fake/dk/log || true; }
foreign() { # a container of another run, under the given name; it must never be touched
  local d; d=/tmp/fake/run/$(printf 'foreign %s' "$1" | sha256sum | cut -c1-64)
  mkdir -p "$d/fs"; echo "$1" > "$d/name"; echo true > "$d/running"; echo "bifrost.rollup.run=someone-else" > "$d/labels"
  echo / > "$d/mount"; echo /dev/null > "$d/envfile"; touch "$d/foreign"
}
foreign_ok() { local d n=0; for d in /tmp/fake/run/*/; do [[ -e $d/foreign && $(cat "$d/running") == true ]] && n=$((n + 1)); done; [[ $n == "$1" ]]; }
gone() { # the throwaway container and the scratch copy are gone, nothing is pending
  check "$1 — no throwaway container is left" bash -c 'for d in /tmp/fake/run/*/; do [[ -d $d && ! -e $d/foreign ]] && exit 1; done; exit 0'
  check "$1 — no scratch snapshot is left" bash -c '! compgen -G "/@bifrost/rollup-snap/minio-rw-*" > /dev/null'
  check "$1 — nothing is pending" test ! -s /rstate/pending-cleanup.list
}
untouched() { # the live MinIO and the credentials
  check "$1 — the live MinIO still runs" test "$(cat /tmp/fake/dk/running)" = true
  check "$1 — no docker command named the live container or compose" bash -c "! grep -Eq '(^| )(minio-backup|compose)( |\$)' /tmp/fake/dk/log"
  check "$1 — the credentials appear in no log" bash -c "! grep -rqF '$SECRET' /rstate /tf /tmp/out /tmp/fake/dk/log"
}

# ---- control: everything due reads back
expect_ok "A control: everything due reads back, the generation publishes" bash "$ROLL" "${R[@]}"
check "A control: one committed generation of minio" test "$(gens minio)" = 1
check "A control: last-success of minio is set" test "$(succ minio)" != none
check "A control: the newest DONE base backup, both data parts and its WAL were read back" \
  grep -q "$P: base backup 20261101T210000 (2 data parts, ends with backup_label) and 3 WAL segments 0000000100000005000000FE..000000010000000600000000 read back" /tmp/out
check "A control: the second server too" grep -q "$Q: base backup 20261101T200000 (1 data parts, ends with backup_label) and 1 WAL segments" /tmp/out
check "A control: the newer FAILED base backup was passed over" grep -q 'base backup 20261102T210000 is FAILED, not DONE' /tmp/out
check "A control: the unfinished base backup was skipped" grep -q 'base backup 20261103T210000 has no backup.info (unfinished), skipped' /tmp/out
check "A control: the newest WAL of each server is kept for the next run" bash -c \
  "grep -qx '$P 000000010000000600000000' /rstate/minio-wal.minio && grep -qx '$Q 000000010000000300000010' /rstate/minio-wal.minio"
grep '^docker run ' /tmp/fake/dk/log | tail -1 > /tmp/runline
check "A control: the throwaway container has no network" grep -qF -- '--network none' /tmp/runline
check "A control: it publishes no port" bash -c "! grep -Eq -- ' (-p|--publish|-P) ' /tmp/runline"
check "A control: it runs the pinned image, never pulls" grep -qF -- "--pull never" /tmp/runline
check "A control: the image is the configured one" grep -qF -- " $IMG server /data" /tmp/runline
check "A control: it mounts one volume, the scratch copy" bash -c "[[ \$(grep -o ' -v ' /tmp/runline | wc -l) == 1 ]] && grep -q ' -v /@bifrost/rollup-snap/minio-rw-[^ ]*/data:/data ' /tmp/runline"
check "A control: its name and label carry its own run token" grep -Eq -- '--name bifrost-rollup-minio-([^ ]+) --label bifrost.rollup.run=\1 ' /tmp/runline
check "A control: the credentials go in as a file" grep -qF -- '--env-file /rconf/minio.env' /tmp/runline
check "A control: metrics report minio as passed" grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="minio"} 1' /tf/backup-rollup.prom
gone "A control"; untouched "A control"

# ---- failures: nothing published, no commit marker, no success time, no prune, all cleaned up
negm() {
  local g s l m; g=$(gens minio); s=$(succ minio); l=$(gname logical-backup-hot); m=$(markers); sleep 1
  expect_fail "$1 fails the run" bash "$ROLL" "${R[@]}"
  check "$1 — nothing published" test "$(gens minio)" = "$g"
  check "$1 — no commit marker" test "$(markers)" = "$m"
  check "$1 — last-success unchanged" test "$(succ minio)" = "$s"
  check "$1 — the prune-on source kept its generation" test "$(gname logical-backup-hot)" = "$l"
  check "$1 — metrics report minio as failed and expected" bash -c \
    'grep -q "last_run_ok{source=\"minio\"} 0" /tf/backup-rollup.prom && grep -q "source_expected{source=\"minio\"} 1" /tf/backup-rollup.prom'
  gone "$1"; untouched "$1"
}
D1=$W/base/20261101T210000/data_0001.tar.gz LASTW=$W/wals/0000000100000006/000000010000000600000000.gz
echo "$P/wals/0000000100000005/0000000100000005000000FF.gz" > /tmp/fake/unreadable
negm "A: one WAL segment does not read back (bitrot)"
check "A: the log names the unreadable segment" grep -q 'COULD NOT READ .*0000000100000005000000FF' /tmp/out
echo "$P/base/20261101T210000/data.tar.gz" > /tmp/fake/unreadable
negm "A: the base backup's first data part does not read back"
echo "$P/base/20261102T210000/backup.info" > /tmp/fake/unreadable
negm "A: a backup.info does not read back"
rm -f /tmp/fake/unreadable
# M1: what is due comes from directories, backup.info and the last generation, not from xl.meta
mv "$D1/xl.meta" /tmp/d1.keep
negm "M1: a data part whose xl.meta is gone (its directory kept)"
mv /tmp/d1.keep "$D1/xl.meta"
mv "$D1" /tmp/d1dir.keep
negm "M1: the last data part is gone entirely"
check "M1: the log says the last part is missing" grep -q 'does not end with backup_label' /tmp/out
mv /tmp/d1dir.keep "${D1/data_0001/data_0002}"
negm "M1: a gap in the data parts"
mv "${D1/data_0001/data_0002}" "$D1"
mv "$LASTW/xl.meta" /tmp/lastw.keep
negm "M1: the newest WAL segment's xl.meta is gone (its directory kept)"
mv /tmp/lastw.keep "$LASTW/xl.meta"
mv "$LASTW" /tmp/lastwdir.keep
negm "M1: the newest WAL segment is gone entirely (the last generation read it)"
mv /tmp/lastwdir.keep "$LASTW"
mkdir -p "$W/wals/0000000200000006/000000020000000600000001.gz"
negm "M1: a later-timeline WAL directory without its xl.meta"
rm -rf "$W/wals/0000000200000006"
mv "$MIN/$Q/base/20261101T200000/backup.info/xl.meta" /tmp/qinfo.keep
negm "M1: another server whose only backup.info lost its xl.meta"
mv /tmp/qinfo.keep "$MIN/$Q/base/20261101T200000/backup.info/xl.meta"
mv "$MIN/$Q" /tmp/q.keep
negm "M1: a server the last generation read is gone"
mv /tmp/q.keep "$MIN/$Q"
cp "$W/base/20261101T210000/backup.info/xl.meta" /tmp/info.keep
info 0000000100000005000000FE 0000000100000005000000FE DONE None > "$W/base/20261101T210000/backup.info/xl.meta"
negm "M1: a backup.info without backup_label (the last part cannot be proven)"
info 0000000100000005000000FE 000000010000000600000001 DONE > "$W/base/20261101T210000/backup.info/xl.meta"
negm "A: the WAL ends before the base backup's end_wal"
cp /tmp/info.keep "$W/base/20261101T210000/backup.info/xl.meta"
mv "$W/base/20261101T210000/data.tar.gz" /tmp/tar.keep
negm "R3: a DONE base backup with no first data part"
mv /tmp/tar.keep "$W/base/20261101T210000/data.tar.gz"
touch /tmp/fake/run_unhealthy
negm "A: the throwaway MinIO never becomes healthy"
rm -f /tmp/fake/run_unhealthy
creds '"quoted-secret"'
negm "A: credentials with a quote give no mc alias"
creds

# ---- S1: only the container this run created is ever stopped or removed
t0=$(date -u +%s)
for d in $(seq -1 30); do foreign "bifrost-rollup-minio-$(date -u -d "@$((t0 + d))" +%Y%m%dT%H%M%SZ)"; done
sleep 1
expect_ok "S1: containers of another run under the stamp-only names are around, the run still publishes" bash "$ROLL" "${R[@]}"
check "S1: every one of them still exists and runs" foreign_ok 32
check "S1: none of them was stopped or removed" bash -c "! grep -Eq '^docker (stop|rm) .*bifrost-rollup-minio-[0-9]{8}T[0-9]{6}Z\$' /tmp/fake/dk/log"
touch /tmp/fake/run_conflict
negm "S1: a name clash fails the source"
check "S1: the clash touched no container" foreign_ok 32
rm -f /tmp/fake/run_conflict
touch /tmp/fake/run_fail_after_create
negm "S1: a run that created its container and then failed (found by its run token and removed)"
rm -f /tmp/fake/run_fail_after_create
check "S1: the other containers are still untouched" foreign_ok 32
rm -rf /tmp/fake/run/*

# ---- S2: pending-cleanup.list lines of the first format, and unknown lines
mkdir -p /@bifrost/rollup-snap/legacy-1 && echo uuid-legacy-1 > /@bifrost/rollup-snap/legacy-1/.fake-uuid
echo "/@bifrost/rollup-snap/legacy-1 uuid-legacy-1" > /rstate/pending-cleanup.list
sleep 1
expect_ok "S2: a run with a first-format pending line" bash "$ROLL" "${R[@]}"
check "S2: the snapshot of the first-format line is deleted" test ! -e /@bifrost/rollup-snap/legacy-1
check "S2: and its line is gone" test ! -s /rstate/pending-cleanup.list
echo "mystery line here" > /rstate/pending-cleanup.list
sleep 1
expect_ok "S2: a run with an unknown pending line" bash "$ROLL" "${R[@]}"
check "S2: the unknown line is kept" grep -qx 'mystery line here' /rstate/pending-cleanup.list
check "S2: and reported" grep -q 'ERROR: unknown pending-cleanup.list line kept: mystery line here' /tmp/out
: > /rstate/pending-cleanup.list

# ---- configuration refusals: no container is ever started
refuse() { local n; n=$(runs); expect_fail "$1 is refused" bash "$ROLL" "${R[@]}"; check "$1 — no container was started" test "$(runs)" = "$n"; }
creds "$SECRET" 644
refuse "A: a credentials file readable by others"
creds; printf 'MINIO_ROOT_USER=rollup-admin\n' > /rconf/minio.env; chmod 600 /rconf/minio.env
refuse "A: a credentials file without a password line"
creds; conf minio/minio:RELEASE.2024-12-18T13-15-44Z
refuse "A: an image that is not pinned by ID or digest"
conf; touch /tmp/fake/no_image
refuse "A: a pinned image that is not on the host"
rm -f /tmp/fake/no_image

# ---- a throwaway container that cannot be removed stays pending, and the next run clears it
sleep 1; touch /tmp/fake/run_rm_fail
expect_ok "A: reads pass although the container cannot be removed" bash "$ROLL" "${R[@]}"
check "A: the container is pending with its ID and run token" grep -Eq '^container [0-9a-f]{64} [0-9]{8}T[0-9]{6}Z-' /rstate/pending-cleanup.list
check "A: its scratch copy is pending, not deleted under it" grep -q '^scratch /@bifrost/rollup-snap/minio-rw-' /rstate/pending-cleanup.list
rm -f /tmp/fake/run_rm_fail; sleep 1
expect_ok "A control: the next run clears what was pending and publishes" bash "$ROLL" "${R[@]}"
gone "A control (after pending)"; untouched "A control (after pending)"
check "A control: prune on with --keep 1 kept one logical generation" test "$(gens logical-backup-hot)" = 1
finish
