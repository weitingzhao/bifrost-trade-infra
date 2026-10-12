#!/usr/bin/env bash
# Coordinator only: disposable Docker rehearsal; no cluster or real credentials.
# Only the age fetch container has network. All Gitea/backup/restore runs: none.
set -euo pipefail
export DOCKER_DEFAULT_PLATFORM=linux/amd64
HERE=$(cd "$(dirname "$0")" && pwd)
IMAGE=gitea/gitea:1.21.11
prefix="gitea-r2-$$"
live="$prefix-live"
vol="$prefix-data"
bak="$prefix-backup"
tools="$prefix-tools"
keys="$prefix-keys"
work="$prefix-work"
hooks="$prefix-hooks"
baseline="$prefix-baseline"
job=""
failed=0
cleanup() {
  rc=$?
  trap - EXIT
  for name in "$live" "$prefix-job" "$prefix-full"; do docker rm -f "$name" >/dev/null 2>&1 || true; done
  for v in "$vol" "$bak" "$tools" "$keys" "$work" "$hooks" "$baseline"; do docker volume rm "$v" >/dev/null 2>&1 || true; done
  exit "$rc"
}
trap cleanup EXIT
check() {
  if "$@"; then printf 'PASS %s\n' "$title"; else printf 'FAIL %s\n' "$title"; failed=1; fi
}
for v in "$vol" "$bak" "$tools" "$keys" "$work" "$hooks" "$baseline"; do docker volume create "$v" >/dev/null; done
# Network is allowed only here; verify the exact archive pin before keygen.
docker run --rm --entrypoint sh -v "$tools":/tools -v "$keys":/keys -v "$HERE":/scripts:ro alpine:3.22 -c '
  set -eu
  sh /scripts/fetch-tools.sh
  url=$(sed -n "s/^AGE_URL=//p" /scripts/fetch-tools.sh)
  sum=$(sed -n "s/^AGE_SHA=//p" /scripts/fetch-tools.sh)
  wget -q -O /tools/keygen.tar.gz "$url"
  printf "%s  %s\n" "$sum" /tools/keygen.tar.gz | sha256sum -c -
  tar -C /tools -xzf /tools/keygen.tar.gz age/age-keygen
  /tools/age/age-keygen -o /keys/identity 2>/dev/null
  /tools/age/age-keygen -y /keys/identity > /keys/recipient
  rm -rf /tools/age/age-keygen /tools/keygen.tar.gz
  chown -R 1000:1000 /keys /tools
'
docker run --rm --network none --entrypoint sh -v "$bak":/backup -v "$work":/work -v "$hooks":/hooks -v "$baseline":/baseline "$IMAGE" -c 'chown 1000:1000 /backup /work /hooks /baseline'
start_live() {
  docker run -d --network none --name "$live" -v "$vol":/data \
    -e USER_UID=1000 -e USER_GID=1000 -e GITEA__database__DB_TYPE=sqlite3 \
    -e GITEA__security__INSTALL_LOCK=true -e GITEA__security__SECRET_KEY=rehearsal-only-synthetic-secret \
    -e GITEA__server__ROOT_URL=http://127.0.0.1:3000/ -e GITEA__service__DISABLE_REGISTRATION=true "$IMAGE" >/dev/null
  for _ in $(seq 1 60); do
    if docker exec "$live" curl -sf -o /dev/null http://127.0.0.1:3000/; then return 0; fi
    sleep 1
  done
  return 1
}
start_live
# Seed inside the network-none container; synthetic password only.
docker exec -u git "$live" bash -c '
  set -euo pipefail
  gitea admin user create --config /data/gitea/conf/app.ini --username admin --password Rehearse-pass-1 --email admin@example.com --admin --must-change-password=false >/dev/null
  for repo in alpha beta gamma; do
    curl -sf -u admin:Rehearse-pass-1 -H "Content-Type: application/json" -X POST http://127.0.0.1:3000/api/v1/user/repos -d "{\"name\":\"$repo\"}" >/dev/null
    git init -q -b main /tmp/$repo
    git -C /tmp/$repo config user.email test@example.com
    git -C /tmp/$repo config user.name test
    printf "seed\n" > /tmp/$repo/README
    if [[ $repo == gamma ]]; then dd if=/dev/urandom of=/tmp/$repo/blob bs=1048576 count=24 2>/dev/null; fi
    git -C /tmp/$repo add README
    if [[ $repo == gamma ]]; then git -C /tmp/$repo add blob; fi
    git -C /tmp/$repo commit -qm seed
    git -C /tmp/$repo remote add origin http://admin:Rehearse-pass-1@127.0.0.1:3000/admin/$repo.git
    git -C /tmp/$repo push -q origin main
  done
'
admin_volume() {
  docker run --rm --network none --user 1000:1000 --entrypoint bash -v "$vol":/data -v "$bak":/backup -v "$hooks":/hooks -v "$baseline":/baseline "$IMAGE" -euo pipefail -c "$1"
}
# Stop cleanly for a baseline; keep synthetic password/hash solely in volumes.
docker rm -f "$live" >/dev/null
admin_volume 'tar -C /data --exclude=./ssh -cf /baseline/data.tar .'
start_live
reset_hooks() { admin_volume 'find /hooks -mindepth 1 -delete'; }
wait_ready() {
  for _ in $(seq 1 300); do
    if admin_volume "test -f /hooks/$1.ready"; then return 0; fi
    sleep .1
  done
  return 1
}
release() { admin_volume "touch /hooks/$1.release"; }
recipient=$(docker run --rm --network none --entrypoint cat -v "$keys":/keys:ro "$IMAGE" /keys/recipient)
admin_volume "printf '%s\n' '$recipient' > /backup/recipient"
backup_job() {
  docker run "$@" --name "$prefix-job" --network none --user 1000:1000 --entrypoint bash \
    -v "$vol":/data:ro -v "$bak":/backup -v "$work":/work -v "$hooks":/hooks \
    -v "$tools":/tools:ro -v "$HERE":/scripts:ro \
    -e PATH=/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    -e HOME=/work -e TMPDIR=/work -e RECIPIENT_FILE=/backup/recipient \
    -e GITEA_BACKUP_TEST_HOOK_DIR=/hooks "$IMAGE" /scripts/backup.sh
}
reset_hooks
admin_volume 'touch /hooks/wait-copy-1'
backup_job -d >/dev/null
wait_ready copy-1
# copy producer is live and consumer held. Push completes before releasing it.
docker exec -u git "$live" bash -euo pipefail -c 'printf "during copy\n" >> /tmp/alpha/README; git -C /tmp/alpha add README; git -C /tmp/alpha commit -qm during-copy; git -C /tmp/alpha push -q origin main'
release copy-1
rc=$(docker wait "$prefix-job")
title='normal run with handshake push DURING copy'; check test "$rc" == 0
if [[ $rc != 0 ]]; then docker logs "$prefix-job"; exit 1; fi
docker rm "$prefix-job" >/dev/null
latest=$(admin_volume 'cat /backup/LATEST')
# Human restore, then the SAME HTTP verifier with decrypted manifest.
restore_rc=0
docker run --rm --network none --user 1000:1000 --entrypoint bash -v "$bak":/backup:ro -v "$keys":/keys:ro \
  -v "$tools":/tools:ro -v "$work":/work -v "$HERE":/scripts:ro -e HOME=/work -e TMPDIR=/work \
  -e PATH=/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$IMAGE" -euo pipefail -c \
  'bash /scripts/restore.sh /backup/$(cat /backup/LATEST) /keys/identity /work/restored; bash /scripts/verify-stage.sh /work/restored /work/restored.MANIFEST.tsv /work/restored.VERIFIED' || restore_rc=$?
title='decrypt, restore, HTTP clone EVERY repository and compare refs'; check test "$restore_rc" == 0
assert_failed() {
  local rc=$1
  [[ $rc != 0 ]] && [[ $(admin_volume 'cat /backup/LATEST') == "$latest" ]] && admin_volume 'for s in /backup/*.partial/STATUS; do [[ ! -f $s || $(cat "$s") != OK ]] || exit 1; done'
}
# Repeat mutations on every DB-copy attempt so the set never converges.
set_fault() {
  local kind=$1
  reset_hooks
  for n in 1 2 3; do admin_volume "touch /hooks/wait-after-db-$n"; done
  backup_job -d >/dev/null
  for n in 1 2 3; do
    wait_ready "after-db-$n"
    if [[ "$kind" == create ]]; then
      docker exec -u git "$live" curl -sf -u admin:Rehearse-pass-1 -H 'Content-Type: application/json' -X POST http://127.0.0.1:3000/api/v1/user/repos -d "{\"name\":\"created$n\"}" >/dev/null
    else
      # There are three seed repos; remove one after each database copy.
      repo=$(printf '%s\n' alpha beta gamma | sed -n "${n}p")
      docker exec -u git "$live" curl -sf -u admin:Rehearse-pass-1 -X DELETE "http://127.0.0.1:3000/api/v1/repos/admin/$repo" >/dev/null
    fi
    release "after-db-$n"
  done
  rc=$(docker wait "$prefix-job")
  title="repository $kind after database copy fails after 3 stages, LATEST unchanged"
  set_fault_result() {
    assert_failed "$rc" && docker logs "$prefix-job" 2>&1 | grep -q 'repository sets still differ after 3 stages'
  }
  check set_fault_result
  docker rm "$prefix-job" >/dev/null
}
set_fault create
set_fault delete
# Reset live data to baseline; no volume shared with a running reset operation.
docker rm -f "$live" >/dev/null
admin_volume 'find /data -mindepth 1 -maxdepth 1 ! -name ssh -exec rm -rf {} +; tar -C /data -xf /baseline/data.tar'
# Corrupt a loose object (seed push stays loose on these tiny repositories).
admin_volume 'repo=/data/git/repositories/admin/alpha.git; sha=$(git --git-dir="$repo" rev-parse refs/heads/main); rm "$repo/objects/${sha:0:2}/${sha:2}"; if git --git-dir="$repo" fsck --connectivity-only >/dev/null 2>&1; then exit 1; fi'
reset_hooks
backup_job -d >/dev/null
rc=$(docker wait "$prefix-job")
title='missing object fails fsck, LATEST unchanged'
missing_result() { assert_failed "$rc" && docker logs "$prefix-job" 2>&1 | grep -q 'failed git fsck after 3 copies'; }
check missing_result
docker rm "$prefix-job" >/dev/null
admin_volume 'find /data -mindepth 1 -maxdepth 1 ! -name ssh -exec rm -rf {} +; tar -C /data -xf /baseline/data.tar'
# Lock overlap is independent of wall-clock seconds.
reset_hooks
admin_volume 'touch /hooks/wait-locked'
backup_job -d >/dev/null
wait_ready locked
rc=0
lock_output=$(docker run --rm --network none --user 1000:1000 --entrypoint bash -v "$vol":/data:ro -v "$bak":/backup \
  -v "$work":/work -v "$tools":/tools:ro -v "$HERE":/scripts:ro -e RECIPIENT_FILE=/backup/recipient "$IMAGE" /scripts/backup.sh 2>&1) || rc=$?
title='second run while first holds lock refuses at once'
lock_result() { assert_failed "$rc" && [[ "$lock_output" == *'holds the NAS lock'* ]]; }
check lock_result
release locked
rc=$(docker wait "$prefix-job")
# First run may be same-second stamp; either finishes or refuses monotonically.
docker rm "$prefix-job" >/dev/null
latest=$(admin_volume 'cat /backup/LATEST')
# Clock-back fixture makes the script itself read an older stamp.
reset_hooks
admin_volume 'mkdir /hooks/bin; printf "#!/bin/sh\nif [ \"\$*\" = \"-u +%%Y-%%m-%%dT%%H%%M%%SZ\" ]; then echo 2000-01-01T000000Z; else exec /bin/date \"\$@\"; fi\n" > /hooks/bin/date; chmod 755 /hooks/bin/date'
rc=0
clock_output=$(docker run --rm --network none --user 1000:1000 --entrypoint bash -v "$vol":/data:ro -v "$bak":/backup -v "$work":/work \
  -v "$hooks":/hooks -v "$tools":/tools:ro -v "$HERE":/scripts:ro -e RECIPIENT_FILE=/backup/recipient \
  -e PATH=/hooks/bin:/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$IMAGE" /scripts/backup.sh 2>&1) || rc=$?
title='clock set back refused before retention, LATEST unchanged'
clock_result() { assert_failed "$rc" && [[ "$clock_output" == *'clock not monotonic'* ]]; }
check clock_result
# Small tmpfs NAS is filled at the manifest handshake (before age writes it).
reset_hooks
admin_volume "touch /hooks/wait-nas-manifest; printf '%s\n' '$recipient' > /hooks/recipient"
docker run -d --name "$prefix-full" --network none --user 1000:1000 --entrypoint bash \
  --tmpfs /backup:rw,size=1m,uid=1000,gid=1000 -v "$vol":/data:ro -v "$work":/work -v "$hooks":/hooks \
  -v "$tools":/tools:ro -v "$HERE":/scripts:ro -e RECIPIENT_FILE=/hooks/recipient \
  -e GITEA_BACKUP_TEST_HOOK_DIR=/hooks -e HOME=/work -e TMPDIR=/work \
  -e PATH=/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$IMAGE" -euo pipefail -c \
  'printf "older\n" > /backup/LATEST; set +e; bash /scripts/backup.sh; rc=$?; [[ $rc != 0 && $(cat /backup/LATEST) == older ]] || exit 1; for s in /backup/*.partial/STATUS; do [[ ! -f $s || $(cat "$s") != OK ]] || exit 1; done; exit 0' >/dev/null
wait_ready nas-manifest
# ENOSPC is the intended fault; assert it occurred, then unblock age.
fill_rc=0
docker exec "$prefix-full" dd if=/dev/zero of=/backup/filler bs=4096 count=512 >/dev/null 2>&1 || fill_rc=$?
[[ $fill_rc != 0 ]] || { printf 'FAIL small tmpfs did not fill\n'; exit 1; }
release nas-manifest
rc=$(docker wait "$prefix-full")
title='full destination at manifest encryption: no OK and LATEST unchanged'
full_result() { [[ "$rc" == 0 ]] && docker logs "$prefix-full" 2>&1 | grep -q 'age encryption failed'; }
check full_result
docker rm "$prefix-full" >/dev/null
# Rewrite ciphertext checksums after truncation, so age authentication itself
# must reject it (rather than merely failing the outer ciphertext checksum).
admin_volume 'latest=$(cat /backup/LATEST); mkdir /backup/fault-trunc; cp /backup/$latest/* /backup/fault-trunc/; head -c 96 /backup/fault-trunc/data.tar.age > /tmp/truncated; cp /tmp/truncated /backup/fault-trunc/data.tar.age; cd /backup/fault-trunc; grep "^#" SHA256SUMS > /tmp/plain-sum; sha256sum data.tar.age MANIFEST.tsv.age > SHA256SUMS; cat /tmp/plain-sum >> SHA256SUMS'
rc=0
docker run --rm --network none --user 1000:1000 --entrypoint bash -v "$bak":/backup:ro -v "$keys":/keys:ro -v "$tools":/tools:ro \
  -v "$work":/work -v "$HERE":/scripts:ro -e TMPDIR=/work -e PATH=/tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  "$IMAGE" /scripts/restore.sh /backup/fault-trunc /keys/identity /work/truncated >/dev/null 2>&1 || rc=$?
title='truncated ciphertext rejected by restore.sh, LATEST unchanged'; check assert_failed "$rc"
exit "$failed"
