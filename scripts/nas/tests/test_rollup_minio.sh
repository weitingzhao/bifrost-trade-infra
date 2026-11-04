#!/usr/bin/env bash
# backup-rollup/rollup.sh with a MinIO source (runbook §3.8 item 2, option A): the objects are
# read back through a throwaway MinIO (the docker and mc doubles of lib.sh). A generation
# publishes only when every object reads back; the throwaway container and its scratch copy
# are gone after success and after failure; the live MinIO is never touched; the credentials
# reach no log. Also the fix review's R3 counterexamples. Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
K=/volume2/k3s-fast
mkdir -p "$K" /volume2/minio-backup /volume1 /rconf
printf '%s\n' "$K" /volume2/minio-backup > /tmp/fake/subvols

# ---- fixtures: a small logical source (prune on) and the MinIO data directory
B1=$K/rs-b1
mkdir -p "$B1/daily/2026-11-01T043000Z"
(cd "$B1/daily/2026-11-01T043000Z" && echo dump > a.dump && sha256sum a.dump > SHA256SUMS && echo OK > STATUS)
echo 2026-11-01T043000Z > "$B1/LATEST"
MIN=/volume2/minio-backup/data; P=bifrost-postgres-backup/bifrost-postgres; W=$MIN/$P
obj() { mkdir -p "$MIN/$1" && printf '%s' "${2:-x}" > "$MIN/$1/xl.meta"; }   # fixture xl.meta = the object's plain content
info() { printf 'backup_label=None\nbegin_wal=%s\nend_wal=%s\nstatus=%s\ntablespaces=None\n' "$1" "$2" "$3"; }
obj "$P/base/20261031T210000/backup.info" "$(info 0000000100000005000000F0 0000000100000005000000F0 DONE)"
obj "$P/base/20261031T210000/data.tar.gz"
obj "$P/base/20261101T210000/backup.info" "$(info 0000000100000005000000FE 0000000100000005000000FE DONE)"
obj "$P/base/20261101T210000/data.tar.gz"
obj "$P/base/20261102T210000/backup.info" "$(info 000000010000000600000000 000000010000000600000000 FAILED)"
for s in 0000000100000005000000FE 0000000100000005000000FF 000000010000000600000000; do obj "$P/wals/${s:0:16}/$s.gz"; done
obj ".minio.sys/config/config.json"
touch -d '2 days ago' "$W"/base/*
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
runs() { grep -c '^docker run ' /tmp/fake/dk/log || true; }
gone() { # the throwaway container and the scratch copy are gone, nothing is pending
  check "$1 — no throwaway container is left" bash -c '[[ -z $(ls -A /tmp/fake/run) ]]'
  check "$1 — no scratch snapshot is left" bash -c '! compgen -G "/@bifrost/rollup-snap/minio-rw-*" > /dev/null'
  check "$1 — nothing is pending" test ! -s /rstate/pending-cleanup.list
}
untouched() { # the live MinIO and the credentials
  check "$1 — the live MinIO still runs" test "$(cat /tmp/fake/dk/running)" = true
  check "$1 — no docker command named the live container or compose" bash -c "! grep -Eq '(^| )(minio-backup|compose)( |\$)' /tmp/fake/dk/log"
  check "$1 — the credentials appear in no log" bash -c "! grep -rqF '$SECRET' /rstate /tf /tmp/out /tmp/fake/dk/log"
}

# ---- control: every object reads back
expect_ok "A control: every object reads back, the generation publishes" bash "$ROLL" "${R[@]}"
check "A control: one committed generation of minio" test "$(gens minio)" = 1
check "A control: last-success of minio is set" test "$(succ minio)" != none
check "A control: the newest DONE base backup and its WAL were read back" \
  grep -q 'base backup 20261101T210000 (1 objects) and 3 WAL segments 0000000100000005000000FE..000000010000000600000000 read back' /tmp/out
check "A control: the newer FAILED base backup was passed over" grep -q 'base backup 20261102T210000 is FAILED, not DONE' /tmp/out
grep '^docker run ' /tmp/fake/dk/log | tail -1 > /tmp/runline
check "A control: the throwaway container has no network" grep -qF -- '--network none' /tmp/runline
check "A control: it publishes no port" bash -c "! grep -Eq -- ' (-p|--publish|-P) ' /tmp/runline"
check "A control: it runs the pinned image, never pulls" grep -qF -- "--pull never" /tmp/runline
check "A control: the image is the configured one" grep -qF -- " $IMG server /data" /tmp/runline
check "A control: it mounts one volume, the scratch copy" bash -c "[[ \$(grep -o ' -v ' /tmp/runline | wc -l) == 1 ]] && grep -q ' -v /@bifrost/rollup-snap/minio-rw-[^ ]*/data:/data ' /tmp/runline"
check "A control: its name is its own" grep -qF -- '--name bifrost-rollup-minio-' /tmp/runline
check "A control: the credentials go in as a file" grep -qF -- '--env-file /rconf/minio.env' /tmp/runline
check "A control: metrics report minio as passed" grep -q 'bifrost_nas_backup_rollup_last_run_ok{source="minio"} 1' /tf/backup-rollup.prom
gone "A control"; untouched "A control"

# ---- failures: nothing published, no success time, no prune, everything cleaned up
negm() {
  local g s l; g=$(gens minio); s=$(succ minio); l=$(gname logical-backup-hot); sleep 1
  expect_fail "$1 fails the run" bash "$ROLL" "${R[@]}"
  check "$1 — nothing published" test "$(gens minio)" = "$g"
  check "$1 — last-success unchanged" test "$(succ minio)" = "$s"
  check "$1 — the prune-on source kept its generation" test "$(gname logical-backup-hot)" = "$l"
  check "$1 — metrics report minio as failed and expected" bash -c \
    'grep -q "last_run_ok{source=\"minio\"} 0" /tf/backup-rollup.prom && grep -q "source_expected{source=\"minio\"} 1" /tf/backup-rollup.prom'
  gone "$1"; untouched "$1"
}
echo "$P/wals/0000000100000005/0000000100000005000000FF.gz" > /tmp/fake/unreadable
negm "A: one WAL segment does not read back (bitrot)"
check "A: the log names the unreadable segment" grep -q 'COULD NOT READ .*0000000100000005000000FF' /tmp/out
echo "$P/base/20261101T210000/data.tar.gz" > /tmp/fake/unreadable
negm "A: the base backup's data tar does not read back"
echo "$P/base/20261102T210000/backup.info" > /tmp/fake/unreadable
negm "A: a backup.info does not read back"
rm -f /tmp/fake/unreadable
mv "$W/wals/0000000100000005/0000000100000005000000FF.gz/xl.meta" /tmp/ff.keep
negm "R3: a WAL directory without its object"
mv /tmp/ff.keep "$W/wals/0000000100000005/0000000100000005000000FF.gz/xl.meta"
mv "$W/base/20261101T210000/data.tar.gz" /tmp/tar.keep
negm "R3: a DONE base backup with no data tar"
mv /tmp/tar.keep "$W/base/20261101T210000/data.tar.gz"
cp "$W/base/20261101T210000/backup.info/xl.meta" /tmp/info.keep
info 0000000100000005000000FE 000000010000000600000001 DONE > "$W/base/20261101T210000/backup.info/xl.meta"
negm "A: the WAL ends before the base backup's end_wal"
cp /tmp/info.keep "$W/base/20261101T210000/backup.info/xl.meta"
touch /tmp/fake/run_unhealthy
negm "A: the throwaway MinIO never becomes healthy"
rm -f /tmp/fake/run_unhealthy
creds '"quoted-secret"'
negm "A: credentials with a quote give no mc alias"
creds

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
check "A: the container is pending" grep -q '^container bifrost-rollup-minio-' /rstate/pending-cleanup.list
check "A: its scratch copy is pending, not deleted under it" grep -q '^scratch /@bifrost/rollup-snap/minio-rw-' /rstate/pending-cleanup.list
rm -f /tmp/fake/run_rm_fail; sleep 1
expect_ok "A control: the next run clears what was pending and publishes" bash "$ROLL" "${R[@]}"
gone "A control (after pending)"; untouched "A control (after pending)"
check "A control: prune on with --keep 1 kept one logical generation" test "$(gens logical-backup-hot)" = 1
finish
